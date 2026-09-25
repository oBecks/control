<div align="center">

<img src="web/static/icons/icon.svg" alt="" width="96" height="96" />

# Control

**Every smart device in your home, in one app.**

Control scans your Wi-Fi, finds your lights, plugs and remotes, and puts them on one screen.
Everything stays on your home network, and you can delete the app for each brand.

[![Check](https://github.com/oBecks/control/actions/workflows/check.yml/badge.svg)](https://github.com/oBecks/control/actions/workflows/check.yml)

</div>

<p align="center">
  <img src="docs/screenshots/home-desktop-dark.png" alt="Home on the desktop: lights, climate, media and plugs as Tiles, with the AC's controls open in the side panel" width="68%" />
  &nbsp;
  <img src="docs/screenshots/home-phone.png" alt="Home on a phone" width="26%" />
</p>
<p align="center">
  <img src="docs/screenshots/home-desktop-light.png" alt="The light theme, with a bulb's brightness and white temperature" width="68%" />
  &nbsp;
  <img src="docs/screenshots/controls-phone.png" alt="The AC's controls as a bottom sheet on a phone" width="26%" />
</p>

Tiles take on each device's real colour when it's on. Tap one to switch it, or open its controls. An AC or TV behind an infrared hub shows ≈, because Control only knows what it last sent.

## What it controls

| | |
|---|---|
| **Yeelight** | Bulbs and LED strips |
| **Tuya / Smart Life** | Wi-Fi plugs |
| **Broadlink RM** | Infrared hubs, and through them your AC, TV, fan or anything else with a remote |

Your AC doesn't need to be smart. With a Broadlink hub, Control finds the right remote codes for your AC by testing a few models at once. For a TV or fan, press each button on the old remote once and Control learns it.

## Install

Download `ControlSetup.exe` from the [latest release](https://github.com/oBecks/control/releases/latest) and run it. No admin rights needed.

Control isn't signed yet, so Windows may say "Windows protected your PC". Click **More info**, then **Run anyway**.

Control opens in its own window and keeps running in the tray when you close it, so your phone keeps working. It starts with Windows (switch that off in Settings). To quit, right-click the tray icon and choose **Quit Control**.

Go to **Add devices** and hit **Scan**. That's it.

## Run from source

You need Windows, Python 3.11+ and Node.js 24.

```bash
git clone https://github.com/oBecks/control.git && cd control
python -m venv .venv && .venv/Scripts/pip install -e ".[desktop]"
npm --prefix web install && npm --prefix web run build
.venv/Scripts/python -m control.desktop
```

Or run just the Engine with `.venv/Scripts/control serve` and open http://localhost:8321.

## On your phone

Turn on **Settings → Phone access**, scan the QR code with your phone, and approve the code it shows. On iPhone, add it to the Home Screen first and it runs like a real app.

It works anywhere on your home Wi-Fi, as long as the PC is on.

## Ask Claude

Open **Settings → Assistant** and click **Connect Claude**, then quit and reopen Claude Desktop. Now you can ask it to "dim the living room lights" or "set the AC to 23". Claude asks before it changes anything. It sees and controls your devices, but setting them up stays in Control.

Claude Code in the Claude app uses the same connection. Any other MCP client can start the same local server: `Control.exe --mcp` (stdio). If Control isn't running, the server starts it in the tray. Nothing leaves your home network.

It works in Claude on the PC running Control, not on claude.ai, the Claude phone app or cloud sessions: those can't reach your home network.

## Coming next

- **Scenes.** "Movie night" in one tap. *In progress.*
- Rooms, more brands and Bluetooth. *Planned.*

## Good to know

The Tuya plug is the only device that needs a one-time sign-in, to fetch its key. Control is a personal project in its early days. The [roadmap](docs/roadmap.md) lists what's missing.

Want to dig in? Start with the [glossary](CONTEXT.md), the [design decisions](docs/adr/) and the [design system](docs/design-system.md).
