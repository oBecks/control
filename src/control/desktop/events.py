"""The Desktop App's side of PC Triggers (ADR 0015): hears Windows say the PC woke, is going to sleep,
was locked or unlocked, or is shutting down, and tells the Engine's `/api/pc-events`, which starts the
Automations whose Trigger it is.

One thread owns a window that is never shown (a top-level one: Windows sends power and shutdown
messages only to those) and its message loop. It costs nothing while nothing happens. What each
message says:
- `WM_POWERBROADCAST`: `PBT_APMSUSPEND` (going to sleep), `PBT_APMRESUMEAUTOMATIC` (awake again; sent
  for every wake, whoever woke it).
- `WM_WTSSESSIONCHANGE` (once registered): lock, unlock, and signing in or coming back to this session.
- `WM_ENDSESSION`: Windows is shutting down or signing out (and not, if another app said no).

Going to sleep and shutting down give Actions only a moment, so the Engine holds its answer for the
Runs a few seconds and Windows waits for that: Actions that talk to a Device over the network may or
may not finish. Windows asks (`WM_QUERYENDSESSION`) before it ends the session, and the app's own
window may close and start stopping the Engine before `WM_ENDSESSION` reaches this thread, so `settle`
lets the app hold its exit until the shutdown has been told (or cancelled).
"""

import ctypes
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from ctypes import wintypes

WM_POWERBROADCAST = 0x0218
WM_WTSSESSION_CHANGE = 0x02B1
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
WM_CLOSE = 0x0010
PBT_APMSUSPEND = 0x0004
PBT_APMRESUMEAUTOMATIC = 0x0012
WTS_CONSOLE_CONNECT, WTS_SESSION_LOGON, WTS_SESSION_LOCK, WTS_SESSION_UNLOCK = 0x1, 0x5, 0x7, 0x8
NOTIFY_FOR_THIS_SESSION = 0

SESSION_EVENTS = {
    WTS_CONSOLE_CONNECT: "unlocks",  # the session is back on this screen (fast user switching)
    WTS_SESSION_LOGON: "unlocks",
    WTS_SESSION_LOCK: "locks",
    WTS_SESSION_UNLOCK: "unlocks",
}
# Windows can say the same thing twice (a lock screen waking, then the sign-in): once per this long.
SAME_EVENT_WITHIN = {"wakes": 30.0, "unlocks": 5.0, "locks": 5.0, "sleeps": 5.0}
WAIT = {"sleeps": 2.5, "shuts_down": 2.5}  # seconds a Run may hold Windows up

LRESULT = ctypes.c_ssize_t

if sys.platform == "win32":
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
    _user32.CreateWindowExW.restype = wintypes.HWND
    _user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                        wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    _user32.DefWindowProcW.restype = LRESULT
    _user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.DestroyWindow.argtypes = [wintypes.HWND]
    _user32.PostQuitMessage.argtypes = [ctypes.c_int]
    _kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    _wtsapi32.WTSRegisterSessionNotification.argtypes = [wintypes.HWND, wintypes.DWORD]
    _wtsapi32.WTSUnRegisterSessionNotification.argtypes = [wintypes.HWND]


class _WndClass(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON),
    ]


def event_of(msg: int, wparam: int, lparam: int) -> str | None:
    """Which PC event a Windows message is, or None."""
    if msg == WM_POWERBROADCAST:
        return {PBT_APMSUSPEND: "sleeps", PBT_APMRESUMEAUTOMATIC: "wakes"}.get(wparam)
    if msg == WM_WTSSESSION_CHANGE:
        return SESSION_EVENTS.get(wparam)
    if msg == WM_ENDSESSION and wparam:  # TRUE: it's really ending, no app said no
        return "shuts_down"
    return None


class PcEvents:
    def __init__(self, port: int):
        self._url = f"http://127.0.0.1:{port}/api/pc-events"
        self._last: dict[str, float] = {}
        self._hwnd = None
        self._thread: threading.Thread | None = None
        self._proc = None
        self._ending = threading.Event()  # Windows asked to end the session
        self._told = threading.Event()  # and it has been told to the Engine, or someone said no

    def start(self) -> None:
        if sys.platform != "win32":
            return
        self._thread = threading.Thread(target=self._run, name="pc-events", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._hwnd:
            _user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)

    def settle(self, timeout: float = 4) -> None:
        """Wait, if Windows is ending the session, until the Engine has been told (for the app's exit)."""
        if self._ending.is_set():
            self._told.wait(timeout)

    def _run(self) -> None:
        try:
            self._loop()
        except Exception as exc:  # PC Triggers stop working; nothing else may
            print(f"PC events: stopped listening: {exc!r}", file=sys.stderr)

    def _loop(self) -> None:
        u = _user32
        self._proc = WNDPROC(self._wndproc)  # kept: Windows calls it for as long as the window lives
        hinst = _kernel32.GetModuleHandleW(None)
        wc = _WndClass(cbSize=ctypes.sizeof(_WndClass), lpfnWndProc=ctypes.cast(self._proc, ctypes.c_void_p),
                       hInstance=hinst, lpszClassName="ControlPcEvents")
        if not u.RegisterClassExW(ctypes.byref(wc)):
            raise ctypes.WinError(ctypes.get_last_error())
        # A plain top-level window, never shown: message-only windows get no power broadcasts.
        hwnd = u.CreateWindowExW(0, "ControlPcEvents", "Control PC events", 0, 0, 0, 0, 0, None, None, hinst, None)
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self._hwnd = hwnd
        if not _wtsapi32.WTSRegisterSessionNotification(hwnd, NOTIFY_FOR_THIS_SESSION):
            print("PC events: Windows won't say when the PC is locked or unlocked", file=sys.stderr)
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u.TranslateMessage(ctypes.byref(msg))
            u.DispatchMessageW(ctypes.byref(msg))

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_QUERYENDSESSION:
            self._told.clear()
            self._ending.set()
            return 1  # never stand in the way
        if msg == WM_ENDSESSION and not wparam:  # another app said no
            self._ending.clear()
            return 0
        if event := event_of(msg, wparam, lparam):
            try:
                self.tell(event)
            finally:
                if event == "shuts_down":
                    self._told.set()
            return 1 if msg == WM_POWERBROADCAST else 0
        if msg == WM_CLOSE:
            _wtsapi32.WTSUnRegisterSessionNotification(hwnd)
            _user32.DestroyWindow(hwnd)
            return 0
        if msg == 0x0002:  # WM_DESTROY
            self._hwnd = None
            _user32.PostQuitMessage(0)
            return 0
        return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def tell(self, event: str) -> None:
        """Tell the Engine, unless it was just told the same. Going to sleep and shutting down wait
        a moment for the Runs (Windows is waiting for us); the rest is told from a thread, so the
        message loop stays free."""
        now = time.monotonic()
        within = SAME_EVENT_WITHIN.get(event, 0)
        if now - self._last.get(event, -within) < within:
            return
        self._last[event] = now
        wait = WAIT.get(event, 0)
        if wait:
            self._post(event, wait)
        else:
            threading.Thread(target=self._post, args=(event, 0), name=f"pc-event-{event}", daemon=True).start()

    def _post(self, event: str, wait: float) -> None:
        body = json.dumps({"event": event, "wait": wait}).encode()
        req = urllib.request.Request(self._url, data=body, method="POST",
                                     headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=wait + 1 if wait else 5):
                pass
        except (OSError, urllib.error.HTTPError) as exc:  # the Engine is starting or stopping
            print(f"PC events: couldn't tell the Engine the PC {event}: {exc!r}", file=sys.stderr)
