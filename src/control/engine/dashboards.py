"""Dashboards (ADR 0010): items placed freely on a grid of the Dashboard's own width.

Each item has a cell (x = column, y = row, from 0) and a size. A size is "WxH" in Tile units, or
"full" for the whole width. Rows are half a Tile tall, so a Tile is two rows high and a Heading one.
"""

import secrets

COLUMNS = (4, 6, 8)  # a phone's, a tablet's, a desktop's

# Each item kind, the sizes it comes in (the first is its default), and whether it points at a
# Device or Group.
KINDS: dict[str, tuple[tuple[str, ...], bool]] = {
    "tile": (("2x1", "1x1", "2x2"), True),
    "heading": (("full", "4x1", "2x1", "1x1"), False),
}
MAX_ITEMS = 200
MAX_ROWS = 1000
MAX_TEXT = 60


def cells(kind: str, size: str, columns: int) -> tuple[int, int]:
    """The (width, height) an item takes, in grid cells."""
    if size == "full":
        return columns, 1
    w, h = (int(n) for n in size.split("x"))
    return min(w, columns), h * 2 if kind == "tile" else 1


def check_columns(columns: int) -> int:
    if columns not in COLUMNS:
        raise ValueError(f"a dashboard is {', '.join(map(str, COLUMNS))} columns wide, not {columns}")
    return columns


def check_items(items: list[dict], targets: set[str], columns: int) -> list[dict]:
    """The items as stored: known kinds and sizes, inside the grid, not overlapping, targets that
    exist, one id each (new ones get one)."""
    if len(items) > MAX_ITEMS:
        raise ValueError(f"a dashboard holds at most {MAX_ITEMS} items")
    out, ids, taken = [], set(), set()
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
        x, y = item.get("x"), item.get("y")
        if not isinstance(x, int) or not isinstance(y, int) or x < 0 or y < 0 or y >= MAX_ROWS:
            raise ValueError(f"a dashboard item needs a cell inside the grid, not ({x}, {y})")
        w, h = cells(kind, size, columns)
        if x + w > columns:
            raise ValueError(f"an item {w} wide can't start at column {x + 1} of {columns}")
        area = {(cx, cy) for cx in range(x, x + w) for cy in range(y, y + h)}
        if area & taken:
            raise ValueError("two dashboard items overlap")
        taken |= area
        kept = {"id": item_id, "kind": kind, "size": size, "x": x, "y": y}
        if targeted:
            target = item.get("target")
            if target not in targets:
                raise LookupError(f"no device or group '{target}'")
            kept["target"] = target
        if kind == "heading":
            kept["text"] = str(item.get("text") or "").strip()[:MAX_TEXT]
        out.append(kept)
    return out


def from_flow(items: list[dict], columns: int) -> list[dict]:
    """Dashboards from before free placement (ADR 0009) kept only an order: place their items row
    by row, as the flow showed them. A Spacer leaves its gap and goes."""
    out, x, y, row_h = [], 0, 0, 0
    for item in items:
        kind, size = item.get("kind"), item.get("size", "1x1")
        w, h = cells(kind if kind in KINDS else "tile", size, columns)
        if x + w > columns:
            x, y, row_h = 0, y + row_h, 0
        if kind in KINDS:
            out.append({**item, "x": x, "y": y})
        x, row_h = x + w, max(row_h, h)
    return out
