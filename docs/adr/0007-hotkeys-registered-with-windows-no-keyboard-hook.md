---
status: accepted
---

# Hotkeys registered with Windows, never a keyboard hook

The Desktop App registers each Hotkey's keys with Windows (`RegisterHotKey`), and Windows tells it only when those keys are pressed. Control never sees any other key. That's why Control needs no keyboard hook, which antivirus tools and anti-cheat games distrust and which would put every keystroke in front of Control. Keys are registered by physical key, so Hotkeys keep working when the Hebrew layout is active. Media keys, F13–F24 and Bluetooth buttons that act as keyboards register like any other key. Hotkeys are stored in the Registry, so the UI and the Assistant can edit them. The Desktop App only receives the notices and sends each Hotkey's action to the Engine, the same way any Client does.

## How it's built

The Desktop App's listener (`desktop/hotkeys.py`) long-polls the Engine (`GET /api/hotkeys/watch`), registers what it gets on its own thread, and reports keys Windows refused, so the UI can mark them as taken by another app. While the Window records keys, the Engine tells the listener to let go of every Hotkey (`PUT /api/hotkeys/recording`), so pressing an existing Hotkey reaches the Window instead of firing. A press calls `POST /api/hotkeys/{uid}/run`, and a small overlay above the tray (a plain Win32 window: no focus, clicks pass through) shows the result. Held keys repeat steps and presses at most every 0.3 s, and a press is skipped while the previous one still runs, since bulbs rate-limit requests.

## How the richer presses work without a hook

A Hotkey's keys are stored as text that says how they're pressed: `Ctrl+Alt+L`, `Ctrl+Alt+L (double)`, `Ctrl+Alt+L (long)`, or `Ctrl+Alt+L, then 1`. The listener gets one entry per keys from `/watch`, with the Hotkey for each way of pressing them.

- **Hold to dim**: keys pressed only once are registered with Windows' repeat, which repeats the notice while the key is held and stops when it's released.
- **Double and long press**: keys that also have one are registered without repeat. After the notice, Control checks that one key's up/down state (`GetAsyncKeyState`) every 30 ms until it's released (`Presses` in `desktop/hotkeys.py`). Held 0.5 s is a long press, fired while still held; down again within 0.4 s of coming up is a double press; otherwise it's a single press, which then waits those 0.4 s only when the keys also have a double press. Held keys repeat a long press that steps or presses, or with no long press a single press that does. So a long press can't share keys with a single press that repeats.
- **Sequences** (Ctrl+Alt+L, then 1): after the first keys, Control registers each second key, and Esc, for 2 seconds, then releases them, and the overlay lists the choices. Typing is only affected during that window, so the second key may be a plain letter or digit. The first keys then start only sequences: they can't be a Hotkey of their own, and a second key can't be another Hotkey's keys.

## Consequences

- **No "let through."** A registered key always goes only to Control, so a Hotkey on Volume Up stops Windows' own volume change. The Hotkeys screen steers users toward spare keys and dedicated combinations. If keys are already taken by another app, registration fails and the screen says so.
- Hotkeys work only while the Desktop App runs: not under a bare `control serve`, and not in `--mcp` mode.

## Considered options

- **A low-level keyboard hook** (`WH_KEYBOARD_LL`), which was this ADR's first version: it can let keys through, but Control would inspect every keystroke, antivirus and anti-cheat software flag it, it misses keys while an elevated window is in front, and Windows silently removes a hook that responds slowly.
- **Registration plus an opt-in hook** for let-through Hotkeys only: two mechanisms to maintain for one small feature.
- **Telling keyboards apart** (a spare numpad used only for Control, via Raw Input): not chosen.
