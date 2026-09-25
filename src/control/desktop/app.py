"""Control.exe (ADR 0004): runs the Engine, shows the Window (pywebview, i.e. Edge WebView2, on the
Engine's own UI) and keeps a tray icon. Closing the Window hides it; only Quit Control in the tray
stops the Engine, so phones keep working meanwhile.

One instance per user: a second launch brings the running Window forward. If an Engine already
answers on the port (e.g. `control serve` while developing), the app is only a Window on it and
leaves it running on quit."""

import argparse
import ctypes
import json
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from ctypes import wintypes
from pathlib import Path

from .. import __version__
from ..engine.registry import Registry, default_db_path
from . import updates

PORT = 8321
ICON = Path(__file__).with_name("control.ico")
MUTEX = "ControlDesktopApp"  # also the installer's AppMutex: it won't install over a running app
SHOW_EVENT = "ControlDesktopShow"  # a second launch sets it to bring the Window forward
CLOSE_HINT_SHOWN = "desktop_close_hint_shown"  # setting: bool
# The UI listens for it and checks whether to show the "still running" note.
SHOWN_EVENT = "window.dispatchEvent(new Event('control:window-shown'))"
STATUS_EVERY = 5  # seconds between tray status refreshes

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True) if sys.platform == "win32" else None
_user32 = ctypes.WinDLL("user32", use_last_error=True) if sys.platform == "win32" else None


# --- Single instance -----------------------------------------------------------


class SingleInstance:
    """A named mutex says whether the app already runs; a named event asks it to show its Window."""

    ERROR_ALREADY_EXISTS = 183
    EVENT_MODIFY_STATE = 0x0002
    INFINITE = 0xFFFFFFFF

    def __init__(self):
        k = _kernel32
        k.CreateMutexW.restype = k.CreateEventW.restype = k.OpenEventW.restype = wintypes.HANDLE
        k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        k.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        k.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        k.SetEvent.argtypes = [wintypes.HANDLE]
        k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        # Kept open for the whole run: Windows closes it when the process ends, however it ends.
        self._mutex = k.CreateMutexW(None, False, MUTEX)
        self.first = ctypes.get_last_error() != self.ERROR_ALREADY_EXISTS

    def ask_first_to_show(self) -> None:
        event = _kernel32.OpenEventW(self.EVENT_MODIFY_STATE, False, SHOW_EVENT)
        if event:
            _user32.AllowSetForegroundWindow(wintypes.DWORD(0xFFFFFFFF))  # ASFW_ANY: let it come to the front
            _kernel32.SetEvent(event)

    def on_show_request(self, callback) -> None:
        event = _kernel32.CreateEventW(None, False, False, SHOW_EVENT)

        def wait():
            while _kernel32.WaitForSingleObject(event, self.INFINITE) == 0:
                callback()

        threading.Thread(target=wait, name="show-requests", daemon=True).start()


# --- The Engine ------------------------------------------------------------------


def engine_answers(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/access/me", timeout=1) as resp:
            return "access" in json.load(resp)
    except (OSError, ValueError):
        return False


class Engine:
    """The Engine's main listener on 127.0.0.1, in a thread: pywebview needs the main thread."""

    def __init__(self, port: int):
        import uvicorn

        from ..api import serve
        from ..api.app import app

        serve.prepare(port)
        self._server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port))
        self._thread = threading.Thread(target=self._server.run, name="engine", daemon=True)

    def start(self, timeout: float = 20) -> bool:
        self._thread.start()
        deadline = time.monotonic() + timeout
        while self._thread.is_alive() and not self._server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        return self._server.started

    def stop(self) -> None:
        from ..api import lan

        lan.listener.stop()
        self._server.should_exit = True
        self._thread.join(timeout=5)


def phone_status(port: int, owned: bool) -> str:
    """The tray's status line."""
    if owned:
        from ..api import lan

        url, error = lan.listener.url, lan.listener.error
    else:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/access/phone", timeout=2) as resp:
                phone = json.load(resp)
            url, error = phone["url"], phone["error"]
        except (OSError, ValueError, KeyError):
            return "Engine not reachable"
    if url:
        return f"Phones: {url}"
    return "Phone access failed" if error else "Phone access off"


# --- The app -----------------------------------------------------------------------


class DesktopApp:
    def __init__(self, port: int, owned: bool, hidden: bool):
        self.port, self.owned = port, owned
        self.quitting = False
        self.update: updates.Update | None = None
        self._status = ""
        self._minimized = False
        self.window = self._create_window(hidden)
        self.tray = self._create_tray()

    # The Window

    def _create_window(self, hidden: bool):
        import webview

        window = webview.create_window(
            "Control", f"http://127.0.0.1:{self.port}", width=1200, height=800, min_size=(380, 560),
            hidden=hidden, background_color=_page_background(),
        )
        window.events.before_show += self._hook_close
        window.events.minimized += lambda: setattr(self, "_minimized", True)
        window.events.restored += lambda: setattr(self, "_minimized", False)
        window.events.maximized += lambda: setattr(self, "_minimized", False)
        return window

    def _hook_close(self, window) -> None:
        # Hooked on the form itself rather than pywebview's `closing` event, which doesn't say why the
        # Window is closing: closing it hides it, but Windows signing out must be let through.
        from System.Windows.Forms import CloseReason  # type: ignore[import-not-found]  # pythonnet

        let_through = (CloseReason.WindowsShutDown, CloseReason.TaskManagerClosing, CloseReason.ApplicationExitCall)

        def closing(form, args):
            if self.quitting or args.CloseReason in let_through:
                return
            args.Cancel = True
            form.Hide()
            self._tell_still_running()

        window.native.FormClosing += closing

    def show(self) -> None:
        self.window.show()
        if self._minimized:
            self.window.restore()
        self.window.run_js(SHOWN_EVENT)

    def _tell_still_running(self) -> None:
        """Once, on the first close: a notification from the tray icon, or, with Windows notifications
        off, a note in the Window the next time it opens."""
        from ..api.desktop import CLOSE_NOTE

        r = Registry()
        try:
            if r.setting(CLOSE_HINT_SHOWN, False):
                return
            r.set_setting(CLOSE_HINT_SHOWN, True)
            if not _notifications_on():
                r.set_setting(CLOSE_NOTE, True)
                return
        finally:
            r.close()
        self.tray.notify("Phones keep working. Quit from this icon to stop it.", "Control is still running here")

    # The tray

    def _create_tray(self):
        import pystray
        from PIL import Image

        item = pystray.MenuItem
        menu = pystray.Menu(
            item("Open Control", lambda: self.show(), default=True),  # also the left click
            item(lambda _: self._status, None, enabled=False),
            item(lambda _: f"Update available: Control {self.update.version}", lambda: self._open_update(),
                 visible=lambda _: self.update is not None),
            pystray.Menu.SEPARATOR,
            item("Quit Control", lambda: self.quit()),
        )
        return pystray.Icon("Control", Image.open(ICON), "Control", menu)

    def _open_update(self) -> None:
        if self.update:
            webbrowser.open(self.update.url)

    def _refresh_status(self) -> None:
        while not self.quitting:
            status = phone_status(self.port, self.owned)
            if status != self._status:
                self._status = status
                self.tray.update_menu()
            time.sleep(STATUS_EVERY)

    def _check_updates(self) -> None:
        from ..api import desktop

        while not self.quitting:
            found = updates.check()
            if found:
                self.update = desktop.state.update = found
                self.tray.update_menu()
            time.sleep(updates.CHECK_EVERY)

    # Running

    def run(self) -> None:
        import webview

        self._status = phone_status(self.port, self.owned)
        self.tray.run_detached()
        threading.Thread(target=self._refresh_status, name="tray-status", daemon=True).start()
        threading.Thread(target=self._check_updates, name="update-check", daemon=True).start()
        data = default_db_path().parent
        # Not private: the UI keeps its theme choice in localStorage.
        webview.start(private_mode=False, storage_path=str(data / "webview"), icon=str(ICON))
        # The Window closed for good: Quit Control, or Windows signing out.
        self.quitting = True
        self.tray.stop()

    def quit(self) -> None:
        self.quitting = True
        self.window.destroy()


def _notifications_on() -> bool:
    """Windows Settings → System → Notifications."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\PushNotifications") as key:
            return winreg.QueryValueEx(key, "ToastEnabled")[0] != 0
    except OSError:
        return True  # never switched off


def _page_background() -> str:
    """The UI's background (--bg in tokens.css) for the system theme, so the Window doesn't flash
    white before the page paints."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            light = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
    except OSError:
        light = 1
    return "#F8F6F3" if light else "#100E0C"


def _log_to_file() -> None:
    """A windowed exe has no console: keep the Engine's output in the data folder instead. That
    includes Control.exe started by the MCP server, whose output goes nowhere."""
    if not getattr(sys, "frozen", False) and sys.stdout is not None and sys.stderr is not None:
        return
    path = default_db_path().parent / "control.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 1_000_000:
        path.replace(path.with_suffix(".old.log"))
    sys.stdout = sys.stderr = open(path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 (lives as long as the app)
    print(f"--- Control {__version__} started {time.strftime('%Y-%m-%d %H:%M:%S')}")


def _message(text: str) -> None:
    _user32.MessageBoxW(None, text, "Control", 0x10)  # MB_ICONERROR


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="Control")
    parser.add_argument("--hidden", action="store_true", help="start in the tray (as at sign-in)")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--mcp", action="store_true", help="be the Assistant's MCP server on stdin/stdout (ADR 0005)")
    parser.add_argument("--disconnect-claude", action="store_true", help="remove Control from Claude's config")
    args = parser.parse_args(argv)

    # Quiet modes: no Window, no tray, no single-instance mutex, so they run alongside the app.
    if args.mcp:
        from ..assistant import server

        server.run(args.port)
        return
    if args.disconnect_claude:  # the uninstaller
        from ..assistant import claude

        claude.disconnect()
        return

    if getattr(sys, "frozen", False):
        # PyInstaller unpacks the built UI next to the program.
        os.environ.setdefault("CONTROL_UI_DIR", str(Path(sys._MEIPASS) / "web"))  # type: ignore[attr-defined]
    _log_to_file()
    # Group the Window under Control's own taskbar icon, not Python's.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Control.Desktop")

    instance = SingleInstance()
    if not instance.first:
        if not args.hidden:  # at sign-in, a second copy just leaves
            instance.ask_first_to_show()
        return

    owned = not engine_answers(args.port)
    engine = None
    if owned:
        from ..api import desktop

        desktop.state.running = True
        engine = Engine(args.port)
        if not engine.start():
            _message(f"Control couldn't start: another program is using port {args.port}.")
            return
    else:
        print(f"An Engine already runs on port {args.port}; showing a Window on it", file=sys.stderr)

    app = DesktopApp(args.port, owned, args.hidden)
    instance.on_show_request(app.show)
    try:
        app.run()
    finally:
        if engine:
            engine.stop()
