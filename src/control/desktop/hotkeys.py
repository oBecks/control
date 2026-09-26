"""The Desktop App's side of Hotkeys (ADR 0007): registers each Hotkey's keys with Windows
(`RegisterHotKey`, never a keyboard hook), calls the Engine's `/api/hotkeys/{uid}/run` when they're
pressed, and shows a small overlay near the tray saying what happened.

Two threads: one owns the registrations, the overlay and their message loop (Windows posts
WM_HOTKEY to the thread that registered); the other long-polls the Engine for changes. Actions run
on a small pool, so a Device that's slow to answer never holds up the keys.
"""

import ctypes
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes

from ..engine import hotkeys
from ..engine.hotkeys import MOD_NOREPEAT, Keys

REPEAT_EVERY = 0.3  # seconds between repeats while keys are held (bulbs rate-limit requests)
OVERLAY_SECONDS = 1.5
_CHECK_ID = 0xBFFF  # the id `can_register` tries keys under

WM_HOTKEY = 0x0312
WM_APP = 0x8000
WM_APPLY = WM_APP + 1  # thread message: new Hotkeys to register
WM_SHOW = WM_APP + 2  # overlay: new content
WM_HIDE = WM_APP + 3  # overlay: go now
WM_TIMER = 0x0113

if sys.platform == "win32":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    _user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    _user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.SetTimer.restype = ctypes.c_size_t
    _user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
    _user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]


def can_register(keys: Keys) -> bool | None:
    """Whether Windows would give Control these keys (False: another app has them). None off Windows."""
    if sys.platform != "win32":
        return None
    ok = _user32.RegisterHotKey(None, _CHECK_ID, keys.mod_flags | MOD_NOREPEAT, keys.key.vk)
    if ok:
        _user32.UnregisterHotKey(None, _CHECK_ID)
    return bool(ok)


# --- The Engine ----------------------------------------------------------------------


class _Engine:
    def __init__(self, port: int):
        self.base = f"http://127.0.0.1:{port}/api/hotkeys"

    def call(self, method: str, path: str, body: dict | None = None, timeout: float = 30):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"content-type": "application/json"} if data else {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        return json.loads(raw) if raw else None


def _detail(exc: urllib.error.HTTPError) -> str:
    try:
        detail = json.loads(exc.read()).get("detail")
    except (ValueError, OSError, AttributeError):
        detail = None
    return detail if isinstance(detail, str) else f"Control answered {exc.code}"


# --- Pressing keys a richer way ------------------------------------------------------


class Presses:
    """Keys that also have a double or a long press. Windows says only when they go down
    (registered without repeats), so each tick asks whether they're still held
    (`GetAsyncKeyState`, ADR 0007) and decides: a long press once they've been held LONG_AFTER, a
    double press when they go down again within DOUBLE_WITHIN of coming up, else a single press.
    Held past LONG_AFTER, a long press that repeats (or, with no long press, a single one that
    repeats) keeps going every REPEAT_EVERY until the keys come up. Pure logic: time and key state
    are handed in, and `fire` gets each Hotkey to run."""

    GIVE_UP = 30.0  # seconds: keys that never seem to come up

    def __init__(self, fire):
        self._fire = fire
        self._on: dict[int, dict] = {}  # registration id -> what's happening with those keys

    @property
    def active(self) -> bool:
        return bool(self._on)

    def clear(self) -> None:
        self._on = {}

    def pressed(self, reg_id: int, entry: dict, now: float) -> None:
        st = self._on.get(reg_id)
        if st and st["up"] is not None:  # down again while waiting for it
            del self._on[reg_id]
            if entry.get("double"):
                self._fire(entry["double"])
                return
        elif st:
            return  # still held: Windows shouldn't say so twice, but one press is one press
        self._on[reg_id] = {"entry": entry, "down": now, "up": None, "held": None, "last": 0.0}

    def tick(self, now: float, is_down) -> None:
        for reg_id, st in list(self._on.items()):
            entry = st["entry"]
            if st["up"] is not None:
                if now - st["up"] >= hotkeys.DOUBLE_WITHIN:
                    del self._on[reg_id]
                    if entry.get("once"):
                        self._fire(entry["once"])
                continue
            if now - st["down"] > self.GIVE_UP:
                del self._on[reg_id]
            elif is_down(entry["vk"]):
                self._held(st, now)
            elif st["held"]:
                del self._on[reg_id]  # the held press is done
            elif entry.get("double"):
                st["up"] = now  # wait for a second press
            else:
                del self._on[reg_id]
                if entry.get("once"):
                    self._fire(entry["once"])

    def _held(self, st: dict, now: float) -> None:
        if now - st["down"] < hotkeys.LONG_AFTER:
            return
        entry = st["entry"]
        once = entry.get("once")
        hk = entry.get("long") or (once if once and once["repeats"] else None)
        if hk is None:
            return
        if st["held"] is None or (hk["repeats"] and now - st["last"] >= REPEAT_EVERY):
            st["held"], st["last"] = hk, now
            self._fire(hk)


# --- The listener --------------------------------------------------------------------

_THEN_IDS = 0x1000  # a sequence's second keys register from here, while it waits for them
_ESCAPE_ID = 0x1FFF
_VK_ESCAPE = 0x1B
TICK_MS = 30


class HotkeyListener:
    def __init__(self, port: int):
        self._engine = _Engine(port)
        self._thread_id = 0
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._next: dict | None = None  # the latest watch answer, not registered yet
        self._registered: dict[int, dict] = {}  # registration id -> keys, with their Hotkeys
        self._busy: set[str] = set()  # Hotkeys whose action is still running
        self._last_run: dict[str, float] = {}
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="hotkey")
        self._presses = Presses(self._fire)
        self._sequence: dict | None = None  # a sequence waiting for its second keys
        self._ticking = 0  # the thread timer's id while one runs
        self.overlay: Overlay | None = None

    def start(self) -> None:
        threading.Thread(target=self._loop, name="hotkeys", daemon=True).start()
        threading.Thread(target=self._watch, name="hotkeys-watch", daemon=True).start()

    def _watch(self) -> None:
        self._ready.wait()
        revision, recording = 0, False
        while True:
            try:
                answer = self._engine.call(
                    "GET", f"/watch?revision={revision}&recording={str(recording).lower()}", timeout=60)
            except (OSError, ValueError):
                time.sleep(2)  # the Engine is starting, or stopped: keep the keys we have
                continue
            revision, recording = answer["revision"], answer["recording"]
            with self._lock:
                self._next = answer
            _user32.PostThreadMessageW(self._thread_id, WM_APPLY, 0, 0)

    def _loop(self) -> None:
        self._thread_id = _kernel32.GetCurrentThreadId()
        msg = wintypes.MSG()
        _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # PM_NOREMOVE: makes the message queue
        try:
            self.overlay = Overlay()
        except Exception as exc:  # noqa: BLE001 (no overlay is better than no Hotkeys)
            print(f"Hotkey overlay unavailable: {exc}", file=sys.stderr)
        self._ready.set()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if not msg.hWnd and msg.message == WM_HOTKEY:
                self._pressed(msg.wParam)
            elif not msg.hWnd and msg.message == WM_TIMER:
                self._tick()
            elif not msg.hWnd and msg.message == WM_APPLY:
                self._apply()
            else:
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))

    def _apply(self) -> None:
        with self._lock:
            answer, self._next = self._next, None
        if answer is None:
            return
        self._end_sequence(hide=True)
        self._presses.clear()
        for reg_id in self._registered:
            _user32.UnregisterHotKey(None, reg_id)
        self._registered = {}
        taken = []
        for reg_id, entry in enumerate(answer["keys"], start=1):
            # Windows repeats the notice for held keys only when they're simply pressed once and
            # their action repeats; for the rest, Presses watches the keys itself.
            mods = entry["mods"] | (0 if _simple(entry) and entry["once"]["repeats"] else MOD_NOREPEAT)
            if _user32.RegisterHotKey(None, reg_id, mods, entry["vk"]):
                self._registered[reg_id] = entry
            else:
                taken += [hk["uid"] for hk in _hotkeys_of(entry)]
        self._pool.submit(self._report, answer["revision"], taken)

    def _report(self, revision: int, taken: list[str]) -> None:
        try:
            self._engine.call("PUT", "/registered", {"revision": revision, "taken": taken})
        except (OSError, ValueError):
            pass  # the next watch registers again

    def _pressed(self, reg_id: int) -> None:
        if self._sequence and (reg_id == _ESCAPE_ID or reg_id in self._sequence["then"]):
            hk = self._sequence["then"].get(reg_id)
            self._end_sequence(hide=hk is None)
            if hk:
                self._fire(hk)
            return
        entry = self._registered.get(reg_id)
        if entry is None:
            return
        if entry["then"]:
            self._start_sequence(entry)
        elif not _simple(entry):
            self._presses.pressed(reg_id, entry, time.monotonic())
            self._tick_on()
        else:
            hk = entry["once"]
            if hk["repeats"] and time.monotonic() - self._last_run.get(hk["uid"], 0) < REPEAT_EVERY:
                return  # Windows repeats the notice while the keys are held: at most every so often
            self._fire(hk)

    def _fire(self, hk: dict) -> None:
        uid = hk["uid"]
        if uid in self._busy:
            return  # held keys: skip ahead rather than queue up presses
        self._busy.add(uid)
        self._last_run[uid] = time.monotonic()
        self._pool.submit(self._run, hk)

    # Sequences: the second keys are Control's only while it waits for them.

    def _start_sequence(self, entry: dict) -> None:
        self._end_sequence()
        then: dict[int, dict] = {}
        for i, second in enumerate(entry["then"]):
            if _user32.RegisterHotKey(None, _THEN_IDS + i, second["mods"] | MOD_NOREPEAT, second["vk"]):
                then[_THEN_IDS + i] = second["hotkey"]
        escape = _user32.RegisterHotKey(None, _ESCAPE_ID, MOD_NOREPEAT, _VK_ESCAPE)
        self._sequence = {"then": then, "escape": bool(escape),
                          "until": time.monotonic() + hotkeys.SEQUENCE_SECONDS}
        if self.overlay:
            rows = [(s["label"], f"{s['hotkey']['name']}: {s['hotkey']['does']}") for s in entry["then"]]
            self.overlay.choices(f"{entry['label']}, then…", rows, hotkeys.SEQUENCE_SECONDS)
        self._tick_on()

    def _end_sequence(self, hide: bool = False) -> None:
        if self._sequence is None:
            return
        for reg_id in self._sequence["then"]:
            _user32.UnregisterHotKey(None, reg_id)
        if self._sequence["escape"]:
            _user32.UnregisterHotKey(None, _ESCAPE_ID)
        self._sequence = None
        if hide and self.overlay:
            self.overlay.hide()

    # A thread timer ticks while keys are watched or a sequence waits.

    def _tick_on(self) -> None:
        if not self._ticking:
            self._ticking = _user32.SetTimer(None, 0, TICK_MS, None)

    def _tick(self) -> None:
        now = time.monotonic()
        if self._sequence and now >= self._sequence["until"]:
            self._end_sequence()  # the overlay hides on its own
        self._presses.tick(now, _is_down)
        if not (self._presses.active or self._sequence) and self._ticking:
            _user32.KillTimer(None, self._ticking)
            self._ticking = 0

    def _run(self, hk: dict) -> None:
        try:
            out = self._engine.call("POST", f"/{hk['uid']}/run")
            self._show(out["name"], out["text"], out.get("level"))
        except urllib.error.HTTPError as exc:
            self._show(hk.get("name", "Hotkey"), _detail(exc), error=True)
        except (OSError, ValueError):
            self._show(hk.get("name", "Hotkey"), "Control didn't answer", error=True)
        finally:
            self._busy.discard(hk["uid"])

    def _show(self, title: str, text: str, level: float | None = None, error: bool = False) -> None:
        if self.overlay:
            self.overlay.show(title, text, level, error)


def _simple(entry: dict) -> bool:
    """Keys pressed only once, the way the first Hotkeys worked: Windows handles held keys."""
    return not (entry.get("double") or entry.get("long") or entry["then"])


def _hotkeys_of(entry: dict) -> list[dict]:
    return [entry[p] for p in hotkeys.PRESSES if entry.get(p)] + [s["hotkey"] for s in entry["then"]]


def _is_down(vk: int) -> bool:
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)


# --- The overlay ---------------------------------------------------------------------

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM) \
    if sys.platform == "win32" else None


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON),
    ]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", wintypes.HDC), ("fErase", wintypes.BOOL), ("rcPaint", wintypes.RECT),
        ("fRestore", wintypes.BOOL), ("fIncUpdate", wintypes.BOOL), ("rgbReserved", ctypes.c_byte * 32),
    ]


def _rgb(hex_: str) -> int:
    r, g, b = (int(hex_[i : i + 2], 16) for i in (1, 3, 5))
    return r | g << 8 | b << 16  # COLORREF


# The UI's tokens (tokens.css), close enough for a few seconds on screen.
_DARK = {"bg": "#26221F", "text": "#F4F1EC", "text2": "#A9A29A", "track": "#3A3531", "accent": "#EDB13A", "error": "#F08A7A"}
_LIGHT = {"bg": "#FFFFFF", "text": "#2A2521", "text2": "#6F6860", "track": "#ECE8E3", "accent": "#D9982A", "error": "#B3402E"}


def _light_theme() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return bool(winreg.QueryValueEx(key, "SystemUsesLightTheme")[0])
    except OSError:
        return False


def _is_rtl(text: str) -> bool:
    return any("֐" <= c <= "ࣿ" for c in text)


class Overlay:
    """A small window above the tray: no focus, clicks pass through, gone after 1.5 s. It shows
    what a Hotkey did, or a sequence's choices while it waits for the second keys."""

    WIDTH, HEIGHT, BAR_HEIGHT = 300, 66, 14  # at 96 DPI; the bar adds its height
    CHOICES_WIDTH, ROW_HEIGHT, MAX_ROWS = 340, 26, 8

    def __init__(self):
        u = _user32
        u.CreateWindowExW.restype = wintypes.HWND
        u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                      ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                      wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        u.DefWindowProcW.restype = LRESULT
        u.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, wintypes.UINT]
        u.BeginPaint.restype = wintypes.HDC
        u.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
        u.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
        u.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
        u.DrawTextW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.RECT), wintypes.UINT]
        u.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
        if hasattr(u, "GetDpiForWindow"):  # Windows 10 and later
            u.GetDpiForWindow.argtypes = [wintypes.HWND]
        u.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
        u.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u.InvalidateRect.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]
        u.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD]
        g = _gdi32
        g.CreateSolidBrush.restype = wintypes.HBRUSH
        g.CreateSolidBrush.argtypes = [wintypes.COLORREF]
        g.CreateFontW.restype = wintypes.HFONT
        g.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wintypes.DWORD] * 8 + [wintypes.LPCWSTR]
        g.SelectObject.restype = wintypes.HGDIOBJ
        g.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        g.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        g.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
        g.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
        g.CreateRoundRectRgn.restype = wintypes.HRGN
        g.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
        _kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        self._lock = threading.Lock()
        self._content: dict = {"title": "", "text": "", "level": None, "error": False, "seconds": OVERLAY_SECONDS}
        self._proc = WNDPROC(self._wndproc)  # kept: Windows calls it for as long as the window lives
        hinst = _kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW(cbSize=ctypes.sizeof(WNDCLASSEXW), lpfnWndProc=ctypes.cast(self._proc, ctypes.c_void_p),
                         hInstance=hinst, lpszClassName="ControlHotkeyOverlay")
        if not u.RegisterClassExW(ctypes.byref(wc)):
            raise ctypes.WinError(ctypes.get_last_error())
        ex = 0x00000008 | 0x00000080 | 0x08000000 | 0x00080000 | 0x00000020  # TOPMOST TOOLWINDOW NOACTIVATE LAYERED TRANSPARENT
        self.hwnd = u.CreateWindowExW(ex, "ControlHotkeyOverlay", "Control", 0x80000000,  # WS_POPUP
                                      0, 0, self.WIDTH, self.HEIGHT, None, None, hinst, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        u.SetLayeredWindowAttributes(self.hwnd, 0, 245, 0x2)  # LWA_ALPHA

    def show(self, title: str, text: str, level: float | None = None, error: bool = False) -> None:
        """From any thread."""
        self._set({"title": title, "text": text, "level": level, "error": error, "seconds": OVERLAY_SECONDS})

    def choices(self, title: str, rows: list[tuple[str, str]], seconds: float) -> None:
        """A sequence's second keys and what each does."""
        self._set({"title": title, "rows": rows, "seconds": seconds})

    def hide(self) -> None:
        _user32.PostMessageW(self.hwnd, WM_HIDE, 0, 0)

    def _set(self, content: dict) -> None:
        with self._lock:
            self._content = content
        _user32.PostMessageW(self.hwnd, WM_SHOW, 0, 0)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        u = _user32
        if msg == WM_SHOW:
            self._place()
            u.InvalidateRect(hwnd, None, False)
            u.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
            with self._lock:
                seconds = self._content["seconds"]
            u.SetTimer(hwnd, 1, int(seconds * 1000), None)
            return 0
        if msg == WM_TIMER or msg == WM_HIDE:
            u.KillTimer(hwnd, 1)
            u.ShowWindow(hwnd, 0)  # SW_HIDE
            return 0
        if msg == 0x000F:  # WM_PAINT
            self._paint(hwnd)
            return 0
        if msg == 0x0014:  # WM_ERASEBKGND: the paint covers it all
            return 1
        if msg == 0x0021:  # WM_MOUSEACTIVATE
            return 3  # MA_NOACTIVATE
        return u.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _scale(self) -> float:
        dpi_for = getattr(_user32, "GetDpiForWindow", None)  # before Windows 10: unscaled
        return (dpi_for(self.hwnd) or 96) / 96 if dpi_for else 1.0

    def _place(self) -> None:
        s = self._scale()
        with self._lock:
            content = self._content
        if "rows" in content:
            w = round(self.CHOICES_WIDTH * s)
            h = round((42 + self.ROW_HEIGHT * min(len(content["rows"]), self.MAX_ROWS) + 10) * s)
        else:
            w = round(self.WIDTH * s)
            h = round((self.HEIGHT + (self.BAR_HEIGHT if content["level"] is not None else 0)) * s)
        area = wintypes.RECT()
        _user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0)  # SPI_GETWORKAREA: above the taskbar
        margin = round(12 * s)
        _user32.SetWindowPos(self.hwnd, wintypes.HWND(-1), area.right - w - margin, area.bottom - h - margin,
                             w, h, 0x0010)  # HWND_TOPMOST, SWP_NOACTIVATE
        radius = round(16 * s)
        _user32.SetWindowRgn(self.hwnd, _gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, radius, radius), True)

    def _paint(self, hwnd) -> None:
        u, g = _user32, _gdi32
        with self._lock:
            content = self._content
        colors = {k: _rgb(v) for k, v in (_LIGHT if _light_theme() else _DARK).items()}
        s = self._scale()
        ps = PAINTSTRUCT()
        hdc = u.BeginPaint(hwnd, ctypes.byref(ps))
        try:
            rect = wintypes.RECT()
            u.GetClientRect(hwnd, ctypes.byref(rect))
            self._fill(hdc, rect, colors["bg"])
            g.SetBkMode(hdc, 1)  # TRANSPARENT
            pad = round(18 * s)
            align = 0x20 | 0x8000 | 0x800  # SINGLELINE END_ELLIPSIS NOPREFIX

            def line(value: str, top: int, height: int, size: int, weight: int, color: int,
                     left: int = 0, width: int | None = None) -> None:
                font = g.CreateFontW(-round(size * s), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")
                old = g.SelectObject(hdc, font)
                g.SetTextColor(hdc, color)
                x = pad + round(left * s)
                right = x + round(width * s) if width else rect.right - pad
                box = wintypes.RECT(x, round(top * s), right, round((top + height) * s))
                flags = align | (0x2 | 0x20000 if _is_rtl(value) else 0)  # DT_RIGHT | DT_RTLREADING
                u.DrawTextW(hdc, value, -1, ctypes.byref(box), flags)
                g.SelectObject(hdc, old)
                g.DeleteObject(font)

            line(content["title"], 11, 20, 13, 600, colors["text2"])
            if "rows" in content:
                rows = content["rows"]
                if len(rows) > self.MAX_ROWS:
                    rows = [*rows[: self.MAX_ROWS - 1], ("", f"and {len(rows) - self.MAX_ROWS + 1} more")]
                for i, (keys, does) in enumerate(rows):
                    top = 38 + i * self.ROW_HEIGHT
                    line(keys, top, self.ROW_HEIGHT, 15, 700, colors["text"], width=64)
                    line(does, top + 1, self.ROW_HEIGHT, 14, 400, colors["text"], left=72)
                return
            text, level, error = content["text"], content["level"], content["error"]
            if error:  # errors are longer: smaller, and starting with a capital like a sentence
                line(text[:1].upper() + text[1:], 33, 24, 14, 600, colors["error"])
            else:
                line(text, 31, 28, 19, 700, colors["text"])
            if level is not None:
                top, height = round(66 * s), max(2, round(5 * s))
                track = wintypes.RECT(pad, top, rect.right - pad, top + height)
                self._fill(hdc, track, colors["track"])
                filled = track.left + round((track.right - track.left) * min(1.0, max(0.0, level)))
                if filled > track.left:
                    self._fill(hdc, wintypes.RECT(track.left, top, filled, top + height), colors["accent"])
        finally:
            u.EndPaint(hwnd, ctypes.byref(ps))

    @staticmethod
    def _fill(hdc, rect: wintypes.RECT, color: int) -> None:
        brush = _gdi32.CreateSolidBrush(color)
        _user32.FillRect(hdc, ctypes.byref(rect), brush)
        _gdi32.DeleteObject(brush)
