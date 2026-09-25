# Roadmap & status

Last updated 2026-09-25.

## Supported devices

Yeelight lights (bulbs, strips), Tuya / Smart Life Wi-Fi plugs (after a Link), and Broadlink RM infrared hubs: ACs through the Signal Library's Code Sets, TVs, fans and anything else through Learning. Every user starts empty and builds their home by scanning their own network. Device data lives in `%LOCALAPPDATA%\Control`, never in the repo.

## Built

- Engine: Scan (Yeelight, Broadlink, Tuya), Registry (stable uid, IP moves, Offline, New flags, renames), adapters (Yeelight light, Tuya plug, Broadlink transmitter incl. Learning), Signal Library (SmartIR climate/media_player/fan), Code Set Finder, button Remote Devices (Power Toggle vs discrete on/off), FastAPI, CLI.
- Web UI: style guide, Home (Tiles, Device Controls as sheet/side panel, rename), Add devices (Scan, Tuya Link, hub card → AC finder / TV / fan / other with Learning), Settings (theme, Phone access).
- Phone access ([ADR 0003](adr/0003-phone-access-approved-browsers-over-lan-http.md)): the Engine serves the built UI; Settings → Phone access opens a second listener on the LAN address (`api/lan.py`); `api/access.py` gates every non-local request (Approved Browsers with a code, Host/Origin checks). PWA-lite: manifest + icons, no service worker. Tested end to end from the PC's own LAN address; **not yet tried on a real iPhone/Android**.
- Tooling: `npm run check` (eslint, prettier, svelte-check, vitest) + 55 pytest tests; GitHub Action in `.github/workflows/check.yml` (passing on the public repo https://github.com/oBecks/control).

## Next steps (in the order suggested to the user)

1. **Try Phone access on real phones** (iPhone Home Screen app + Android Chrome) and fix what comes up.
2. **Desktop app**: one Python program: Engine + pywebview window + tray icon, starts with Windows (see design decisions in CONTEXT.md / ADR 0001).
3. **Scenes**: chip row on top of Home.
4. **MCP server**: a thin Client of the Engine API (control + read state).
5. Later: running the Engine on an always-on box (Raspberry Pi etc.) so phones work while the PC is off, Rooms, Hubs & Bridges in Settings, automations, Bluetooth, more brands, public release.

## Open items to raise with the user

- **Before any public release**: the Tuya Link borrows Home Assistant's app identity ([ADR 0002](adr/0002-tuya-link-borrows-home-assistant-identity.md)), and Local Keys are stored unencrypted (TODO in `registry.py`: move to Windows DPAPI/keyring).
- Philips remotes (RC5/RC6) flip a toggle bit per press. If a learned Philips button only works every other time, that's the cause.
