<div align="center">

<img src="web/static/icons/icon.svg" alt="" width="96" height="96" />

# Control

**Every smart device in your home, in one app.**

Control scans your Wi-Fi, finds your lights, plugs and remotes, and puts them on one screen.
Everything stays on your home network, and you can delete the app for each brand.

[![Check](https://github.com/oBecks/control/actions/workflows/check.yml/badge.svg)](https://github.com/oBecks/control/actions/workflows/check.yml)

</div>

## What it controls

| | |
|---|---|
| **Yeelight** | Bulbs and LED strips |
| **Tuya / Smart Life** | Wi-Fi plugs |
| **Broadlink RM** | Infrared hubs, and through them your AC, TV, fan or anything else with a remote |

Your AC doesn't need to be smart. With a Broadlink hub, Control finds the right remote codes for your AC by testing a few models at once. For a TV or fan, press each button on the old remote once and Control learns it.

## Try it

You need Windows, Python 3.11+ and Node.js 24.

```bash
git clone https://github.com/oBecks/control.git && cd control
python -m venv .venv && .venv/Scripts/pip install -e .
npm --prefix web install && npm --prefix web run build
.venv/Scripts/control serve
```

Open http://localhost:8321, go to **Add devices** and hit **Scan**. That's it.

## On your phone

Turn on **Settings → Phone access**, scan the QR code with your phone, and approve the code it shows. On iPhone, add it to the Home Screen first and it runs like a real app.

It works anywhere on your home Wi-Fi, as long as the PC is on.

## Coming next

- **Desktop app.** Starts with Windows, lives in the tray, one installer. *In progress.*
- **Scenes.** "Movie night" in one tap. *In progress.*
- **AI assistant.** Ask Claude to turn off the lights, through an MCP server. *In progress.*
- Rooms, more brands and Bluetooth. *Planned.*

## Good to know

The Tuya plug is the only device that needs a one-time sign-in, to fetch its key. Control is a personal project and isn't ready for a public release yet. The [roadmap](docs/roadmap.md) lists what's missing.

Want to dig in? Start with the [glossary](CONTEXT.md), the [design decisions](docs/adr/) and the [design system](docs/design-system.md).
