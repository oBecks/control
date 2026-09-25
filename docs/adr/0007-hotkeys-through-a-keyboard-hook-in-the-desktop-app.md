---
status: accepted
---

# Hotkeys through a low-level keyboard hook in the Desktop App

Hotkeys need more than Windows' `RegisterHotKey` can give: double and long presses, a held key that keeps dimming, sequences (Ctrl+Alt+L, then 1), keys that are optionally let through to the app in front, media keys, and Bluetooth buttons that act as keyboards. That takes key-down and key-up timing and the choice to swallow each key, so the Desktop App installs a low-level keyboard hook (`WH_KEYBOARD_LL`). Keys are matched by physical key, not by the character typed, so Hotkeys keep working when the Hebrew layout is active. Hotkeys are stored in the Registry like everything else, so the UI and the Assistant can edit them. The Desktop App only listens for keys and sends the Hotkey's action to the Engine, the same way any Client does.

## Consequences

- Hotkeys work only while the Desktop App runs: not under a bare `control serve`, and not in `--mcp` mode.
- Windows doesn't show a non-elevated hook the keys of an elevated window (Task Manager, installers), so Hotkeys don't fire while one is in front. We accept this: running Control as administrator would be a far bigger risk.
- The hook callback must return quickly. Windows silently removes a hook that takes longer than its timeout, so matching happens in the hook and actions run on another thread.
- Some antivirus tools and anti-cheat games distrust keyboard hooks. Code signing (roadmap) helps with the former.
- The hook doesn't record keys: it only tests each key against the Hotkeys you've set and forgets it.

## Considered options

- **`RegisterHotKey` only**: simple and hook-free, but combinations only. It can't do double, long or held presses, sequences, or letting keys through.
- **Telling keyboards apart** (a spare numpad used only for Control, via Raw Input): not chosen; any keyboard's keys can be a Hotkey.
