"""Dashboards (ADR 0009): an ordered list of sized items that the UI packs into a grid.

A size is "WxH" in grid cells, or "full" for the whole width. The grid has 4, 6 or 8 columns
depending on the screen, and an item wider than the screen takes the full width.
"""

import secrets

# Each item kind, the sizes it comes in (the first is its default), and whether it points at a
# Device or Group.
KINDS: dict[str, tuple[tuple[str, ...], bool]] = {
    "tile": (("2x1", "1x1"), True),
    "heading": (("full",), False),
    "spacer": (("1x1", "2x1", "4x1"), False),
}
MAX_ITEMS = 200
MAX_TEXT = 60


def check_items(items: list[dict], targets: set[str]) -> list[dict]:
    """The items as stored: known kinds and sizes, targets that exist, one id each (new ones get one)."""
    if len(items) > MAX_ITEMS:
        raise ValueError(f"a dashboard holds at most {MAX_ITEMS} items")
    out, ids = [], set()
    for item in items:
        kind = item.get("kind")
        if kind not in KINDS:
            raise ValueError(f"unknown dashboard item '{kind}'")
        sizes, targeted = KINDS[kind]
        size = item.get("size") or sizes[0]
        if size not in sizes:
            raise ValueError(f"a {kind} comes in {', '.join(sizes)}, not {size}")
        item_id = item.get("id") or secrets.token_hex(4)
        if item_id in ids:
            raise ValueError(f"two dashboard items share the id '{item_id}'")
        ids.add(item_id)
        kept = {"id": item_id, "kind": kind, "size": size}
        if targeted:
            target = item.get("target")
            if target not in targets:
                raise LookupError(f"no device or group '{target}'")
            kept["target"] = target
        if kind == "heading":
            kept["text"] = str(item.get("text") or "").strip()[:MAX_TEXT]
        out.append(kept)
    return out
