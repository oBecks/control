"""The Desktop App (ADR 0004): one program that runs the Engine, shows the Window and keeps a tray
icon, so phones keep working after the Window is closed. `python -m control.desktop` runs it from
source; `packaging/` turns it into Control.exe and ControlSetup.exe.

Only `app` needs pywebview and pystray (the `desktop` extra); the rest runs anywhere."""
