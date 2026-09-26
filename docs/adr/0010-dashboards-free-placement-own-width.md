---
status: accepted
---

# Dashboards: free placement on a grid of the Dashboard's own width

Supersedes [ADR 0009](0009-dashboards-ordered-flow-with-spacers.md). The ordered flow couldn't put a heading directly over one Tile with free space beside both: it only fills row by row. Trying it on the real home (2026-09-27), the user wanted to put things exactly where they drop them, so each item now has a cell (column, row) and a size in cells (width, height) that the user picks, and nothing moves by itself: an empty cell is a gap, and Spacers are gone.

Each Dashboard has its own column count, picked by the user: 4 for a phone, 6 for a tablet, 8 for desktop, changeable later. Cells stretch to fill a wider screen, so a phone Dashboard looks as arranged on any phone. Rows are half a Tile tall: a Tile is at least two rows (room for its icon and name), a Heading one or more, so a Heading sits right on top of the Tile below it. A Tile one column wide takes the small look, four rows or more the large look. Dropping an item where others are pushes them down just enough to make room, and whatever is under them moves along.

## Considered options

- **Keep the flow** (ADR 0009): reflows everywhere, but can't stack a heading over one Tile.
- **One 8-column arrangement, reading order on narrower screens**: simple, but a phone never looks as arranged.
- **A separate phone arrangement per Dashboard**: exact on both, twice the arranging.
- **Swap or refuse on a collision** instead of pushing down.

## Consequences

- On a screen too narrow for its columns (an 8-column Dashboard on a phone), a Dashboard falls back to reading order (row by row, left to right) and can't be arranged there.
- Changing a Dashboard's columns to fewer moves items that no longer fit left, pushing down what they land on.
