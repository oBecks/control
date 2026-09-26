---
status: accepted
---

# Hotkeys registered with Windows, never a keyboard hook

The Desktop App registers each Hotkey's keys with Windows (`RegisterHotKey`), and Windows tells it only when those keys are pressed. Control never sees any other key. That's why Control needs no keyboard hook, which antivirus tools and anti-cheat games distrust and which would put every keystroke in front of Control. Keys are registered by physical key, so Hotkeys keep working when the Hebrew layout is active. Media keys, F13–F24 and Bluetooth buttons that act as keyboards register like any other key. Hotkeys are stored in the Registry, so the UI and the Assistant can edit them. The Desktop App only receives the notices and sends each Hotkey's action to the Engine, the same way any Client does.

## How it's built

The Desktop App's listener (`desktop/hotkeys.py`) long-polls the Engine (`GET /api/hotkeys/watch`), registers what it gets on its own thread, and reports keys Windows refused, so the UI can mark them as taken by another app. While the Window records keys, the Engine tells the listener to let go of every Hotkey (`PUT /api/hotkeys/recording`), so pressing an existing Hotkey reaches the Window instead of firing. A press calls `POST /api/hotkeys/{uid}/run`, and a small overlay above the tray (a plain Win32 window: no focus, clicks pass through) shows the result. Held keys repeat steps and presses at most every 0.3 s, and a press is skipped while the previous one still runs, since bulbs rate-limit requests.

## How the richer presses work without a hook

- **Double press**: two notices for the same Hotkey within about 0.4 s.
- **Hold to dim**: Windows repeats the notice while the key is held. It stops when the key is released.
- **Long press**: after the first notice, Control checks that one key's up/down state (`GetAsyncKeyState`) until it's released.
- **Sequences** (Ctrl+Alt+L, then 1): after the first combination, Control registers the follow-up keys for about 2 seconds, then releases them. Typing is only affected during that window.

## Consequences

- **No "let through."** A registered key always goes only to Control, so a Hotkey on Volume Up stops Windows' own volume change. The Hotkeys screen steers users toward spare keys and dedicated combinations. If keys are already taken by another app, registration fails and the screen says so.
- Hotkeys work only while the Desktop App runs: not under a bare `control serve`, and not in `--mcp` mode.

## Considered options

- **A low-level keyboard hook** (`WH_KEYBOARD_LL`), which was this ADR's first version: it can let keys through, but Control would inspect every keystroke, antivirus and anti-cheat software flag it, it misses keys while an elevated window is in front, and Windows silently removes a hook that responds slowly.
- **Registration plus an opt-in hook** for let-through Hotkeys only: two mechanisms to maintain for one small feature.
- **Telling keyboards apart** (a spare numpad used only for Control, via Raw Input): not chosen.
