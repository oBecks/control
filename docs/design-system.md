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
- **Scenes**: chip row at the top of Home. "+" creates one, long-press edits.
- **Add Devices**: separate screen for Scans, Links (Tuya QR), Setup hints, and adding Remote Devices (AC code-set finder).
- **Transmitters**: hidden from Home. Listed in Settings → Hubs & Bridges.

## Review process
- A **living style guide** at `/styleguide` in the real app comes first: tokens, type, and every Tile state (on/off/colour/offline/assumed/New) in light + dark, at phone + desktop widths. Nothing is thrown away.
