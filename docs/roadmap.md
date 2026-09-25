# Roadmap & status

Last updated 2026-09-25.

## Supported devices

Yeelight lights (bulbs, strips), Tuya / Smart Life Wi-Fi plugs (after a Link), and Broadlink RM infrared hubs: ACs through the Signal Library's Code Sets, TVs, fans and anything else through Learning. Every user starts empty and builds their home by scanning their own network. Device data lives in `%LOCALAPPDATA%\Control`, never in the repo.

## Built

- Engine: Scan (Yeelight, Broadlink, Tuya), Registry (stable uid, IP moves, Offline, New flags, renames), adapters (Yeelight light, Tuya plug, Broadlink transmitter incl. Learning), Signal Library (SmartIR climate/media_player/fan), Code Set Finder, button Remote Devices (Power Toggle vs discrete on/off), FastAPI, CLI.
- Web UI: style guide, Home (Tiles, Device Controls as sheet/side panel, rename), Add devices (Scan, Tuya Link, hub card → AC finder / TV / fan / other with Learning), Settings (theme).
- Tooling: `npm run check` (eslint, prettier, svelte-check, vitest) + 42 pytest tests; GitHub Action in `.github/workflows/check.yml`.

## Next steps (in the order suggested to the user)

1. **Phone access**: the Engine serves the built UI (`web` builds to static), binds to the LAN, and adds Approved Browsers (a new browser shows a code; the user approves it once in the desktop app).
2. **Desktop app**: one Python program: Engine + pywebview window + tray icon, starts with Windows (see design decisions in CONTEXT.md / ADR 0001).
3. **Scenes**: chip row on top of Home.
4. **MCP server**: a thin Client of the Engine API (control + read state).
5. Later: Rooms, Hubs & Bridges in Settings, automations, Bluetooth, more brands, public release.

## Open items to raise with the user

- Public repo: https://github.com/oBecks/control. Check that the first `Check` Action run passed (`gh run list`); fix anything that only fails on Linux CI.
- **Before any public release**: the Tuya Link borrows Home Assistant's app identity ([ADR 0002](adr/0002-tuya-link-borrows-home-assistant-identity.md)), and Local Keys are stored unencrypted (TODO in `registry.py`: move to Windows DPAPI/keyring).
- Philips remotes (RC5/RC6) flip a toggle bit per press. If a learned Philips button only works every other time, that's the cause.
