---
status: accepted
---

# Assistant: a local MCP server inside Control.exe, connected by writing Claude's config

The user's Assistant (e.g. Claude) reads and controls Devices through a local MCP server: the installed `Control.exe` started with `--mcp`, speaking MCP over stdio to the Claude app that launched it and HTTP to the Engine on `127.0.0.1:8321`. It is a Client like the Window: no device logic, and it never opens the Registry, for the same reason the `control` CLI isn't shipped ([ADR 0004](0004-desktop-app-per-user-installer-engine-inside.md)). Everything stays on the home network, and users need nothing beyond Control and Claude.

## Decisions

- **Read and control only.** The Assistant lists Devices (name, uid, Category, state) and changes state: on/off, brightness, colour, AC mode and temperature, pressing a remote's button. Scenes join once they exist. Setup stays in the UI: Scan, Links, Learning and Code Set probes need someone at the device, and approving phones and renaming are the user's decisions.
- **Devices by name or uid.** Tools accept either; an ambiguous name returns the matches instead of guessing.
- **Honest state.** Answers label Assumed State as assumed, say a Power Toggle's power is unknown, and say when a Device is Offline, so the Assistant never claims "the TV is off" when nobody knows.
- **Claude's approval is the confirmation.** Read tools are marked read-only so clients may allow them without asking; actions go through the client's normal approval. Control adds no second confirmation: the user asked the Assistant precisely to act.
- **Starts Control when needed.** If no Engine answers, `--mcp` starts `Control.exe --hidden` and waits for it, rather than telling the user to open Control.
- **`--mcp` is a quiet mode**: no Window, no tray, no single-instance mutex, so it runs alongside the Desktop App.
- **Connecting**: Settings → Assistant has a **Connect Claude** button that adds a `control` entry to Claude Desktop's `claude_desktop_config.json` (merged with what's there, after a backup) and says to restart Claude, and shows the `claude mcp add` command for Claude Code. **Disconnect** removes the entry, and uninstalling Control runs the same cleanup so Claude isn't left pointing at a missing program.
- **No on/off switch for the Assistant.** Any program on this PC can already call the Engine, which trusts 127.0.0.1 ([ADR 0003](0003-phone-access-approved-browsers-over-lan-http.md)); a switch refusing the MCP server would protect nothing.
- **No activity feed.** Home updates when state changes, whoever changed it.

## Considered options

- **Remote connector** (claude.ai, Claude on the phone): needs a public HTTPS address and a relay into every home, plus accounts. That ends "everything stays on your network"; it would need its own ADR.
- **Claude Desktop extension (`.mcpb`)**: Anthropic's directory no longer accepts them (only plugins can list a local server), nothing shows one can launch an already-installed exe, and a sideloaded bundle reportedly shows "not verified by Anthropic". A plain stdio entry is documented for both Claude Desktop and Claude Code.
- **Python or `uv` bundle**: the docs contradict each other on whether Claude supplies Python, and it would duplicate what Control.exe already contains.
- **A separate `control-mcp.exe`**: cleaner console stdio, but a second program to build and, later, sign. The fallback if the windowed `Control.exe` can't do stdio.
- **The Assistant doing setup too**: those flows need a person at the device or are security decisions.

## Consequences

- Control writes into another app's settings file. It must keep everything else in it intact, and find it for both the regular and the Microsoft Store install of Claude Desktop.
- `Control.exe` is a windowed program; stdin/stdout must work when Claude launches it. Verify this first, and fall back to a console `control-mcp.exe` if they don't.
- Other MCP clients can use the same command (`Control.exe --mcp`); the README documents it.
