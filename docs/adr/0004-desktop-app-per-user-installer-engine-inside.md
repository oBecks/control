---
status: accepted
---

# Desktop App: one per-user installer with the Engine inside, living in the tray

Control reaches users as a normal Windows download: `ControlSetup.exe`, a per-user Inno Setup installer (no admin prompt) into `%LOCALAPPDATA%\Programs\Control`, with a Start-menu entry and an uninstaller. It installs one windowed `Control.exe` (PyInstaller) that runs the Engine, shows the Window (pywebview, i.e. Edge WebView2, loading the Engine's own UI at `http://127.0.0.1:8321`) and keeps a tray icon. Phones only work while the Engine runs, so closing the Window hides it to the tray, and the app starts with Windows by default (hidden in the tray). One program the user never has to think about beats a separate background service plus a front end.

## Decisions

- **Single instance, attach if an Engine exists.** A second launch brings the running Window forward. If an Engine already answers on port 8321 (e.g. `control serve` during development), the app becomes just a Window on it and leaves it running on quit.
- **Tray**: left-click opens the Window. The menu holds Open Control, a status line (the phone URL or "Phone access off"), "Update available" when there is one, and Quit Control, the only thing that stops the Engine. The first close shows a one-time "Control is still running here" notification.
- **Start with Windows**: a pre-ticked installer checkbox, and an on/off switch in Settings.
- **Releases**: pushing a `vX.Y.Z` tag makes a GitHub Action on `windows-latest` build the installer and attach it to a release on the public repo. The first is v0.1.0.
- **Updates**: notify only. The app checks GitHub Releases at start and daily, and Settings and the tray link to the new installer. No auto-update: an unsigned self-updater is too easy a target.
- **Unsigned** for now. Users see SmartScreen's "Windows protected your PC" and click More info → Run anyway; the README says so. Revisit (Azure Trusted Signing, SignPath) before promoting it widely.
- **Uninstall** asks "Also delete your devices and settings?" with No preselected, so a reinstall brings everything back. Data stays in `%LOCALAPPDATA%\Control`, separate from the program.
- **Firewall**: a per-user installer can't add a Windows Firewall rule, so Windows asks "Allow access?" when the user turns on Phone access. Settings explains it beforehand.
- **The `control` CLI is not shipped.** It talks to the Registry and devices directly instead of through the Engine, so it would fight a running Desktop App. It stays a developer tool; scripting and AI control come through the Engine API (the MCP server).

## Considered options

- **Edge `--app` window instead of pywebview**: no dependency, but a browser process we can't hide to the tray or observe closing.
- **Machine-wide installer**: could add the firewall rule, but needs an admin prompt on every install and update.
- **Portable zip**: no uninstaller, no Start-menu entry, nowhere obvious for autostart to point.
- **Quit on close**: simpler, but phones stop working the moment the Window closes.

## Consequences

- Publishing releases ships the Tuya Link that borrows Home Assistant's app identity ([ADR 0002](0002-tuya-link-borrows-home-assistant-identity.md)), which the roadmap listed as a blocker before any public release. Accepted for now: the worst case is Tuya revoking it and Linking breaking. Revisit before promoting Control widely.
- Nothing may assume the repo layout at runtime: the UI folder and data folder come from settings or environment (`CONTROL_UI_DIR`, `CONTROL_DATA_DIR`), so the same code runs from the repo and from the installed app.
- Local Keys sealed with DPAPI keep working, since DPAPI is tied to the Windows user, not to the program.
- An unsigned PyInstaller exe that opens a network port can trigger antivirus false positives.
