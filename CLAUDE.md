# Control

Windows app that scans the home wifi for smart devices and controls them from one auto-sorted UI (desktop window, phone browser, later an MCP server). Python **Engine** + SvelteKit **web UI**.

- **[CONTEXT.md](CONTEXT.md)**: the glossary. Name code, UI copy and messages with its terms (Device, Hub, Transmitter, Remote Device, Signal, Code Set, Learning, Power Toggle, Link, Tile…).
- **[docs/roadmap.md](docs/roadmap.md)**: what's built and next steps. Read it first when continuing the work.
- **`docs/*.local.md`** (git-ignored, personal): a developer's own notes, e.g. the devices they test with. Read any that exist along with the roadmap.
- **[docs/design-system.md](docs/design-system.md)**: read before any UI change.
- **[docs/adr/](docs/adr/)**: read before changing Engine architecture or the Tuya Link.

## Layout

- `src/control/engine/`: adapters per brand, `registry.py` (SQLite at `%LOCALAPPDATA%\Control\control.db`), scanners, Signal Library, Code Set Finder, button remotes.
- `src/control/api/app.py`: FastAPI; every Client goes through it. `src/control/__main__.py`: the `control` CLI.
- `web/src/lib/`: UI components, `home.svelte.ts` (live store), `api.ts` (client). Routes in `web/src/routes/(app)/`, style guide at `/styleguide`.

## Running

- Engine: `.venv/Scripts/control serve` (127.0.0.1:8321, run in background). It has no auto-reload: restart it after every Python change.
- UI: `preview_start` with name `web` (`.claude/launch.json`) → http://localhost:5173, which proxies `/api` to the Engine.
- **Done** means both are green: `npm run check` in `web/` and `.venv/Scripts/python -m pytest -q`.

## Gotchas

- Run `npm`/`npx` through the PowerShell tool; from Git Bash they fail with `'"node"' is not recognized`.
- After adding an npm dependency the first page load can be blank while Vite re-optimizes: reload.
- In `.ts` modules that tests import, import Lucide icons per file (`@lucide/svelte/icons/tv`); the barrel import makes Vitest take ~60 s instead of ~2 s.
- Links and `goto()` go through `resolve()` from `$app/paths` (lint rule). Pass extra navigation data through the `home` store, since the rule rejects query strings built around `resolve()`.
- Colour mixing uses `color-mix(in oklab, …)`: OKLCH mixing shifts device colours to the wrong hue.
- Yeelight bulbs rate-limit requests: keep a status read to one request. Scans can miss a bulb's reply, so a direct answer marks a device online again.

## Real devices

Everything the Engine sends reaches the user's real home. Read state freely. Ask first before switching the plug (it cuts power), sending IR to the AC/TV/fan, or running a Code Set probe, and have the user confirm what the device did, since only they can see it.
