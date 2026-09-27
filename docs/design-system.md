# Design system: decisions

Settled in the design grilling session (2026-09-25). Terms follow [CONTEXT.md](../CONTEXT.md).

## Feel
- **Calm & minimal** (Apple Home / Nothing OS territory): generous space, soft surfaces, restrained chrome. The devices' own colours are the main colour on screen.
- **Warm amber accent** for buttons, selection, and a Plug's "on" state. Chosen to stay distinct from the AC's cool-blue tint.
- **Rounded sans** typeface (Nunito / Manrope family). Big, readable numbers for temperatures and brightness.
- **Theme follows the system** (light + dark both first-class), with a manual override in Settings.
- **Motion: subtle & quick.** 150–250 ms fades and slides (Tile glow fading in, sheet/panel sliding). Respects reduce-motion.

## Layout
- **Phone and desktop are designed as equals**, not one squeezed into the other.
  - Phone: single column of sections, Tiles 2-up, Device Controls as a bottom sheet.
  - Desktop: left sidebar nav · Tile grid · right side panel for the selected Device's Controls (stays open while you click other Tiles).
- **Home**: one scroll. A Scene chip row on top, then sections per Category (Lights / Climate / Plugs…) with a Type ↔ Rooms switch once Rooms exist.
- **English now, RTL-ready**: logical properties (start/end) everywhere, so Hebrew can be added without re-layout.

## Tiles
- Tap/click **toggles**. A **›** chevron in the corner (and right-click on desktop) opens Device Controls.
- **On** = the device's real colour: a light's actual RGB or white temperature, AC cool-blue or warm-orange by mode, plugs in accent amber. **Off** = neutral.
- **Assumed State** (Remote Devices): a small ≈ mark on the Tile. Device Controls explain it ("last set by Control, may differ if the physical remote was used") and offer explicit On and Off buttons.
- **Offline**: dimmed in place with an "Offline" label, no toggle. Tapping offers "Find again" and tips.
- **New**: Devices first found by a Scan are announced by a banner on Home that leads to Add Devices. Home itself stays clean.

## Where things live
- **Groups**: a row at the top of Home. In Group Controls the pencil beside the name only renames it, as it does for a Device; an **Edit group** button under the Devices list opens the whole Group (name, members, Delete).
- **Scenes**: chip row at the top of Home. "+" creates one, long-press edits.
- **Add Devices**: separate screen for Scans, Links (Tuya QR), Setup hints, and adding Remote Devices (AC code-set finder).
- **Dashboards** ([ADR 0010](adr/0010-dashboards-free-placement-own-width.md)): a Dashboards entry in the sidebar and tab bar opens their list (open, new, rename, delete, reorder, "open this browser to it"). Each Dashboard is made for a phone, tablet or desktop (4 / 6 / 8 columns) and its items sit exactly at their cells; rows are half a Tile tall, so a Heading sits right on a Tile. Cells stretch to fill wider screens (up to 180px a column); a screen too narrow shows it in reading order, not arrangeable there. An Edit button (never a long-press) starts arranging a draft, with Undo, Redo, Cancel and Save in the header (leaving or cancelling with unsaved changes asks in a dialog): empty cells show, Tiles stop responding, each item gets a drag handle (top-end) and a × (top-start), and a tap selects it for the bar at the bottom: Width and Height steppers (any size the grid holds), Remove, and for a heading its text, alignment (left / center / right), text size (S–XL) and bold. A Tile one column wide takes the small look, four rows or more the large look. With nothing selected the bar offers Made for and Add item. Dropping onto other items pushes them down. Besides Tiles and Headings: Big Controls (a brightness bar that is itself the slider, filled in the light's colour with the bulb at its start as the on/off switch; a colour wheel with a strip of whites under it; an AC card with −/+, mode icons and On / Off), Remote Pads (compact: the essentials around the arrows; full from 10 rows: every button, learned extras in a row at the bottom), Single Buttons (an icon or label, flashing on press like a remote's Tile), Run Buttons (the same look with an Automation's name, lit and saying "Running…" while its Run goes on; right-click opens the Automation; added under Add item → Buttons → Automations) and a Clock (date from 3 columns wide). Each targeted item opens its Device Controls with its › or a right-click, and scales its contents to its cell rather than a fixed size. On a phone held sideways (landscape, at most 500px tall) a Dashboard goes full-screen: no tab bar, a short header with a ‹ back to the Dashboards list, centered, the notch kept clear only on its own side, and sheets no wider than a phone held upright.
- **Automations**: an Automations entry in the sidebar and tab bar lists them, each with an on/off switch, a Run button, and its next and last Run. The builder is one page: the name as its title, then When, Only if and Then as sections of sentence cards (the Engine words each part), each tapped to edit in a sheet and added with "+ Add a When / an Only if / a Then"; Then cards have drag handles. Edits are a draft with a sticky Save / Cancel bar and the leave-without-saving dialog; the history (a dot per outcome, expanding to each Action's result) and Run now sit under it, then its Hotkeys with Add Hotkey (on the computer running Control), as in a Device's controls. Automations' notifications show as cards at the top of every page (the latest three, then "Dismiss all"), dismissed for every browser at once.
- **Transmitters**: hidden from Home. Listed in Settings → Hubs & Bridges.

## Review process
- A **living style guide** at `/styleguide` in the real app comes first: tokens, type, and every Tile state (on/off/colour/offline/assumed/New) in light + dark, at phone + desktop widths. Nothing is thrown away.
