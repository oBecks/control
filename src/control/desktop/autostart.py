"""Start with Windows (ADR 0004): a value under the user's Run key, the same one the installer's
pre-ticked checkbox writes. Per user, so no admin prompt."""

import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
# Where Task Manager's Startup apps tab records that the user disabled an entry.
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
VALUE = "Control"


def command() -> str:
    """What Windows runs at sign-in: the app, hidden in the tray."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --hidden'
    # From source: pythonw, so no console window opens at sign-in.
    return f'"{Path(sys.executable).with_name("pythonw.exe")}" -m control.desktop --hidden'


def is_on() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE)
    except FileNotFoundError:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY) as key:
            flags, _ = winreg.QueryValueEx(key, VALUE)
    except FileNotFoundError:
        return True
    return not (isinstance(flags, bytes) and flags[:1] == b"\x03")  # 3 = disabled in Task Manager


def set_on(on: bool) -> None:
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if on:
            winreg.SetValueEx(key, VALUE, 0, winreg.REG_SZ, command())
        else:
            _delete(key)
    # Turning it on here overrides an earlier "Disabled" in Task Manager.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY, 0, winreg.KEY_SET_VALUE) as key:
            _delete(key)
    except FileNotFoundError:
        pass


def _delete(key) -> None:
    import winreg

    try:
        winreg.DeleteValue(key, VALUE)
    except FileNotFoundError:
        pass
