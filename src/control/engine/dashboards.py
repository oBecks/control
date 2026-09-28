"""Dashboards (ADR 0010): items placed freely on a grid of the Dashboard's own width.

Each item has a cell (x = column, y = row, from 0) and a size in cells (w, h) that the user picks.
Rows are half a Tile tall, so a Tile is at least two rows high and a Heading one.
"""

import secrets

COLUMNS = (4, 6, 8)  # a phone's, a tablet's, a desktop's

# Each item kind: the smallest and largest height in rows, the fewest columns, its default (w, h), and
# whether it points at a Device or Group (a Run Button: an Automation; a Scene Button: a Scene). A default width of 0 means the whole grid.
KINDS: dict[str, dict] = {
    "tile": {"rows": (2, 12), "cols": 1, "default": (2, 2), "targeted": True},
    "heading": {"rows": (1, 6), "cols": 1, "default": (0, 1), "targeted": False},
    # A Big Control: one of a light's, AC's or their Group's controls, right on the Dashboard.
    "big_control": {"rows": (1, 12), "cols": 1, "default": (4, 2), "targeted": True},
    # A Remote Pad: a TV's, fan's or Streamer's buttons laid out like its remote.
    "pad": {"rows": (4, 24), "cols": 2, "default": (2, 8), "targeted": True},
    # A Single Button: one remote button, or one Streamer App Shortcut.
    "button": {"rows": (1, 6), "cols": 1, "default": (1, 2), "targeted": True},
    "clock": {"rows": (1, 6), "cols": 1, "default": (2, 2), "targeted": False},
    # Who's home: each Person, home or away (ADR 0014).
    "people": {"rows": (1, 12), "cols": 1, "default": (2, 2), "targeted": False},
    # A Run Button: starts an Automation's Run, skipping its Conditions (ADR 0012).
    "run": {"rows": (1, 6), "cols": 1, "default": (2, 2), "targeted": True},
    # A Scene Button: sets a Scene, lit while it's active (ADR 0013).
    "scene": {"rows": (1, 6), "cols": 1, "default": (2, 2), "targeted": True},
}
# A Big Control's kinds, each with its own sizes in place of the "big_control" kind's.
CONTROLS: dict[str, dict] = {
    "brightness": {"rows": (1, 12), "cols": 2, "default": (4, 2)},
    "colour": {"rows": (4, 12), "cols": 2, "default": (2, 4)},  # a wheel and a white strip
    "climate": {"rows": (3, 12), "cols": 2, "default": (2, 4)},  # temperature, mode and power
}
MAX_NAME = 80
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


def check_items(items: list[dict], targets: set[str], columns: int, automations: set[str] = frozenset(),
                scenes: set[str] = frozenset()) -> list[dict]:
    """The items as stored: known kinds, sizes and cells inside the grid, not overlapping, targets
    that exist (Devices and Groups, `automations` for a Run Button, `scenes` for a Scene Button), one
    id each (new ones get one)."""
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

        if kind == "big_control":
            control = item.get("control")
            if control not in CONTROLS:
                raise ValueError(f"a big control is {', '.join(CONTROLS)}, not {control!r}")
            spec = spec | CONTROLS[control]

        x, y = _whole(item.get("x"), "column"), _whole(item.get("y"), "row")
        w = _whole(item.get("w", spec["default"][0] or columns), "width")
        h = _whole(item.get("h", spec["default"][1]), "height")
        lo, hi = spec["rows"]
        narrowest = spec["cols"]
        if not narrowest <= w <= columns:
            raise ValueError(f"a {kind} is {narrowest} to {columns} columns wide, not {w}")
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
            if kind == "run" and target not in automations:
                raise LookupError(f"no Automation '{target}'")
            if kind == "scene" and target not in scenes:
                raise LookupError(f"no Scene '{target}'")
            if kind not in ("run", "scene") and target not in targets:
                raise LookupError(f"no device or group '{target}'")
            kept["target"] = target
        if kind == "big_control":
            kept["control"] = item["control"]
        if kind == "button":
            given = [(k, item[k]) for k in ("button", "app") if isinstance(item.get(k), str) and item[k]]
            if len(given) != 1:
                raise ValueError("a button presses one remote button or opens one app")
            key, name = given[0]
            if len(name) > MAX_NAME:
                raise ValueError(f"a button's {key} is at most {MAX_NAME} characters")
            kept[key] = name
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
    size = item.get("size")
    if size == "full":
        return columns, 1
    if item.get("kind") == "heading":
        head = str(size).split("x")[0]
        return min(int(head), columns) if head.isdigit() and int(head) else columns, 1
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
