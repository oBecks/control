"""Dashboards (ADR 0010): items placed freely on a grid of the Dashboard's own width.

Each item has a cell (x = column, y = row, from 0) and a size in cells (w, h) that the user picks.
Rows are half a Tile tall, so a Tile is at least two rows high and a Heading one.
"""

import secrets

COLUMNS = (4, 6, 8)  # a phone's, a tablet's, a desktop's

# Each item kind: the smallest and largest height in rows, its default (w, h), and whether it points
# at a Device or Group. A default width of 0 means the whole grid.
KINDS: dict[str, dict] = {
    "tile": {"rows": (2, 12), "default": (2, 2), "targeted": True},
    "heading": {"rows": (1, 6), "default": (0, 1), "targeted": False},
}
ALIGNS = ("start", "center", "end")
TEXT_SIZES = ("s", "m", "l", "xl")
MAX_ITEMS = 200
MAX_ROWS = 1000
MAX_TEXT = 60

# Sizes from before the user picked cells: "WxH" in Tile units, or "full".
_OLD_SIZES = {"2x1": (2, 2), "1x1": (1, 2), "2x2": (2, 4)}


def check_columns(columns: int) -> int:
    if columns not in COLUMNS:
        raise ValueError(f"a dashboard is {', '.join(map(str, COLUMNS))} columns wide, not {columns}")
    return columns


def _whole(value, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"a dashboard item's {what} must be a whole number, not {value!r}")
    return value


def check_items(items: list[dict], targets: set[str], columns: int) -> list[dict]:
    """The items as stored: known kinds, sizes and cells inside the grid, not overlapping, targets
    that exist, one id each (new ones get one)."""
    if len(items) > MAX_ITEMS:
        raise ValueError(f"a dashboard holds at most {MAX_ITEMS} items")
    out, ids, taken = [], set(), set()
    for item in items:
        kind = item.get("kind")
        if kind not in KINDS:
            raise ValueError(f"unknown dashboard item '{kind}'")
        spec = KINDS[kind]
        item_id = item.get("id") or secrets.token_hex(4)
        if item_id in ids:
            raise ValueError(f"two dashboard items share the id '{item_id}'")
        ids.add(item_id)

        x, y = _whole(item.get("x"), "column"), _whole(item.get("y"), "row")
        w = _whole(item.get("w", spec["default"][0] or columns), "width")
        h = _whole(item.get("h", spec["default"][1]), "height")
        lo, hi = spec["rows"]
        if not 1 <= w <= columns:
            raise ValueError(f"a {kind} is 1 to {columns} columns wide, not {w}")
        if not lo <= h <= hi:
            raise ValueError(f"a {kind} is {lo} to {hi} rows high, not {h}")
        if x < 0 or y < 0 or y + h > MAX_ROWS:
            raise ValueError(f"a dashboard item needs a cell inside the grid, not ({x}, {y})")
        if x + w > columns:
            raise ValueError(f"an item {w} wide can't start at column {x + 1} of {columns}")
        area = {(cx, cy) for cx in range(x, x + w) for cy in range(y, y + h)}
        if area & taken:
            raise ValueError("two dashboard items overlap")
        taken |= area

        kept = {"id": item_id, "kind": kind, "x": x, "y": y, "w": w, "h": h}
        if spec["targeted"]:
            target = item.get("target")
            if target not in targets:
                raise LookupError(f"no device or group '{target}'")
            kept["target"] = target
        if kind == "heading":
            kept["text"] = str(item.get("text") or "").strip()[:MAX_TEXT]
            kept["align"] = item.get("align") or "start"
            kept["text_size"] = item.get("text_size") or "m"
            kept["bold"] = bool(item.get("bold", True))
            if kept["align"] not in ALIGNS:
                raise ValueError(f"a heading aligns {', '.join(ALIGNS)}, not {kept['align']}")
            if kept["text_size"] not in TEXT_SIZES:
                raise ValueError(f"a heading's text is {', '.join(TEXT_SIZES)}, not {kept['text_size']}")
        out.append(kept)
    return out


def _old_cells(item: dict, columns: int) -> tuple[int, int]:
    size = item.get("size", "1x1")
    if size == "full":
        return columns, 1
    if item.get("kind") == "heading":
        return min(int(size.split("x")[0]), columns), 1
    w, h = _OLD_SIZES.get(size, (1, 2))
    return min(w, columns), h


HEADING_STYLE = {"align": "start", "text_size": "m", "bold": True}


def upgrade(items: list[dict], columns: int) -> list[dict]:
    """Items saved by earlier versions, as stored now. Before free placement (ADR 0009) they kept
    only an order: placed row by row, as the flow showed them, a Spacer leaving its gap. Before
    cells they had a named size, and headings no style."""
    items = [HEADING_STYLE | i if i.get("kind") == "heading" else i for i in items]
    if all("x" in i and "w" in i for i in items):
        return items
    placed = all("x" in i for i in items)
    out, x, y, row_h = [], 0, 0, 0
    for item in items:
        w, h = _old_cells(item, columns)
        rest = {k: v for k, v in item.items() if k != "size"}
        if placed:
            out.append({**rest, "w": w, "h": h})
            continue
        if x + w > columns:
            x, y, row_h = 0, y + row_h, 0
        if item.get("kind") in KINDS:
            out.append({**rest, "x": x, "y": y, "w": w, "h": h})
        x, row_h = x + w, max(row_h, h)
    return out
