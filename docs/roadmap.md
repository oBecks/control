# Roadmap & status

Last updated 2026-09-26.

## Supported devices

Yeelight lights (bulbs, strips), Tuya / Smart Life Wi-Fi plugs (after a Link), and Broadlink RM infrared hubs: ACs through the Signal Library's Code Sets, TVs, fans and anything else through Learning. Every user starts empty and builds their home by scanning their own network. Device data lives in `%LOCALAPPDATA%\Control`, never in the repo.

## Built

- Engine: Scan (Yeelight, Broadlink, Tuya), Registry (stable uid, IP moves, Offline, New flags, renames), adapters (Yeelight light, Tuya plug, Broadlink transmitter incl. Learning), Signal Library (SmartIR climate/media_player/fan), Code Set Finder, button Remote Devices (Power Toggle vs discrete on/off), FastAPI, CLI.
- Web UI: style guide, Home (Tiles, Device Controls as sheet/side panel, rename), Add devices (Scan, Tuya Link, hub card → AC finder / TV / fan / other with Learning), Settings (theme, Phone access).
- Phone access ([ADR 0003](adr/0003-phone-access-approved-browsers-over-lan-http.md)): the Engine serves the built UI; Settings → Phone access opens a second listener on the LAN address (`api/lan.py`); `api/access.py` gates every non-local request (Approved Browsers with a code, Host/Origin checks). PWA-lite: manifest + icons, no service worker. Tried on real phones: the iPhone Home Screen app opens full screen like a separate app; Android Chrome's home-screen shortcut opens a normal Chrome tab (expected without HTTPS).
- Desktop App ([ADR 0004](adr/0004-desktop-app-per-user-installer-engine-inside.md)): `src/control/desktop/` runs the Engine in a thread, the Window (pywebview) and a tray icon (pystray); single instance via a named mutex, attaches to an Engine already on the port. Closing hides the Window (Windows signing out still closes it); the first close shows a one-time notification. Settings → Phone access warns when Windows Firewall has Block rules for Control (left by a missed or cancelled "Allow access?" prompt, which Windows never shows again, even after a reinstall). Settings → Desktop app: Start with Windows (HKCU Run key, `autostart.py`) and update notices (`updates.py` checks GitHub Releases at start and daily). `packaging/`: PyInstaller spec (one folder), Inno Setup script (per user, pre-ticked Start with Windows, `AppMutex`, uninstall asks about data), `build.py`. `.github/workflows/release.yml` builds and publishes on a `vX.Y.Z` tag. Released as v0.1.0 (https://github.com/oBecks/control/releases/tag/v0.1.0); v0.2.0 adds the Assistant; installer, uninstall and the release Action tested.
- Assistant ([ADR 0005](adr/0005-assistant-through-a-local-mcp-server.md)): `Control.exe --mcp` (`src/control/assistant/server.py`, `mcp` SDK) is a stdio MCP server and an Engine Client over HTTP. Tools: `list_devices` (optionally with state), `get_device` (read-only), `set_power`, `set_light`, `set_climate`, `press_button`; Devices by name (any case, or a unique part of it) or uid. If no Engine answers it starts `Control.exe --hidden`, detached. Settings → Assistant: Connect Claude / Disconnect (`assistant/claude.py` merges an `mcpServers.control` entry into Claude Desktop's config, regular and Store install, `.bak` first) and the `claude mcp add` command for Claude Code; the uninstaller runs `Control.exe --disconnect-claude`. Tested over real stdio against the real home, from source and as the packaged Control.exe, through a Node client as Claude launches it: reads, a light's colour, auto-start, and non-English text on the pipes. Control survives the session under Node's Job Object; under the Python SDK's client (kill-on-close, no breakaway) it stops with the session.
- Tooling: `npm run check` (eslint, prettier, svelte-check, vitest) + 99 pytest tests; GitHub Action in `.github/workflows/check.yml` (passing on the public repo https://github.com/oBecks/control).

## Next steps (in the order suggested to the user)

1. **Scenes**: chip row on top of Home. Then add them to the Assistant's tools (ADR 0005).
2. **Before promoting Control widely**: code signing (SmartScreen), and the Tuya Link's borrowed identity (ADR 0002).
3. Later: a proper Android install (needs HTTPS on the LAN: a local certificate authority, see ADR 0003), running the Engine on an always-on box (Raspberry Pi etc.) so phones work while the PC is off, Rooms, Hubs & Bridges in Settings, automations, Bluetooth, more brands, public release.

## Open items to raise with the user

- **Before any public release**: the Tuya Link borrows Home Assistant's app identity ([ADR 0002](adr/0002-tuya-link-borrows-home-assistant-identity.md)); ADR 0004 accepts shipping it in GitHub releases for now. Local Keys are sealed with Windows DPAPI (`engine/vault.py`); an always-on box (Linux) would need its own store, since `vault` passes text through there.
- Philips remotes (RC5/RC6) flip a toggle bit per press. If a learned Philips button only works every other time, that's the cause.
