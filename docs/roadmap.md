# Roadmap & status

Last updated 2026-09-25.

## Supported devices

Yeelight lights (bulbs, strips), Tuya / Smart Life Wi-Fi plugs (after a Link), and Broadlink RM infrared hubs: ACs through the Signal Library's Code Sets, TVs, fans and anything else through Learning. Every user starts empty and builds their home by scanning their own network. Device data lives in `%LOCALAPPDATA%\Control`, never in the repo.

## Built

- Engine: Scan (Yeelight, Broadlink, Tuya), Registry (stable uid, IP moves, Offline, New flags, renames), adapters (Yeelight light, Tuya plug, Broadlink transmitter incl. Learning), Signal Library (SmartIR climate/media_player/fan), Code Set Finder, button Remote Devices (Power Toggle vs discrete on/off), FastAPI, CLI.
- Web UI: style guide, Home (Tiles, Device Controls as sheet/side panel, rename), Add devices (Scan, Tuya Link, hub card → AC finder / TV / fan / other with Learning), Settings (theme, Phone access).
- Phone access ([ADR 0003](adr/0003-phone-access-approved-browsers-over-lan-http.md)): the Engine serves the built UI; Settings → Phone access opens a second listener on the LAN address (`api/lan.py`); `api/access.py` gates every non-local request (Approved Browsers with a code, Host/Origin checks). PWA-lite: manifest + icons, no service worker. Tried on real phones: the iPhone Home Screen app opens full screen like a separate app; Android Chrome's home-screen shortcut opens a normal Chrome tab (expected without HTTPS).
- Tooling: `npm run check` (eslint, prettier, svelte-check, vitest) + 65 pytest tests; GitHub Action in `.github/workflows/check.yml` (passing on the public repo https://github.com/oBecks/control).

## Next steps (in the order suggested to the user)

1. **Desktop App** (designed, not built): `ControlSetup.exe` per-user installer, `Control.exe` = Engine + pywebview Window + tray icon, starts with Windows, releases v0.1.0+ on GitHub. All decisions in [ADR 0004](adr/0004-desktop-app-per-user-installer-engine-inside.md). Suggested order: Window + tray on this PC first, then packaging and the release Action.
2. **MCP server**: a thin Client of the Engine API (control + read state).
3. **Scenes**: chip row on top of Home.
4. Later: a proper Android install (needs HTTPS on the LAN: a local certificate authority, see ADR 0003), running the Engine on an always-on box (Raspberry Pi etc.) so phones work while the PC is off, Rooms, Hubs & Bridges in Settings, automations, Bluetooth, more brands, public release.

## Open items to raise with the user

- **Before any public release**: the Tuya Link borrows Home Assistant's app identity ([ADR 0002](adr/0002-tuya-link-borrows-home-assistant-identity.md)); ADR 0004 accepts shipping it in GitHub releases for now. Local Keys are sealed with Windows DPAPI (`engine/vault.py`); an always-on box (Linux) would need its own store, since `vault` passes text through there.
- Philips remotes (RC5/RC6) flip a toggle bit per press. If a learned Philips button only works every other time, that's the cause.
