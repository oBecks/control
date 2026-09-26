---
status: accepted
---

# Dashboards are an ordered flow with Spacers, not free placement

A Dashboard is stored as an ordered list of items, each with a size in grid cells (a normal Tile is 2×1, a small Tile 1×1, a Heading always full width). The grid packs them in order into as many columns as fit: 4 on a phone, 6 on a tablet, 8 on desktop. Dragging changes an item's place in the order, not its coordinates. The user wanted to put things wherever they like, deliberate gaps included, and a **Spacer** (an empty item, visible only while arranging) provides those gaps. This keeps the glossary's promise that a Dashboard is one layout that reflows on narrow screens.

## Considered options

- **Free placement** (each item at an exact column and row, like phone widgets): exact on the screen it was arranged on, but a desktop layout squeezed into 4 columns has to be re-packed by rules, so the phone no longer looks as arranged. Items stored with coordinates also can't simply be reordered into a flow later.
- **Free placement with a separate phone arrangement**: exact on both, but two layouts per Dashboard to keep in sync, which the glossary rules out.

## Consequences

- An item wider than the screen's columns (e.g. an 8×1 slider on a phone) takes the full width.
- Gaps move with their neighbours when the column count changes. Nothing sits at an absolute position.
