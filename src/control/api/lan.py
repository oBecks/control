"""Phone access (ADR 0003): a second listener on this machine's LAN address, running only while the
user has Phone access turned on. The main listener always stays on 127.0.0.1, so Windows only asks
to allow Control on the network once the user opts in."""

import socket
import subprocess
import sys
import threading
import time

import uvicorn


def lan_ip() -> str | None:
    """The address other devices on the home network reach this machine at."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))  # UDP connect sends nothing; it only picks the outgoing interface
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return None if ip.startswith("127.") else ip


PUBLIC_NETWORK_WARNING = (
    "Windows treats this network as Public, which blocks phones. In Windows Settings → Network & internet, "
    "open this network's properties and choose Private network."
)
_CATEGORY_TTL = 15  # seconds; Settings polls often and the lookup takes ~0.6 s


def network_category(ip: str) -> str | None:
    """Windows' firewall profile for the network `ip` is on: "Public", "Private", "DomainAuthenticated",
    or None if unknown (and on other systems)."""
    if sys.platform != "win32":
        return None
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-NetIPAddress -IPAddress '{ip}' | Get-NetConnectionProfile).NetworkCategory"],
            capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out or None


class LanListener:
    def __init__(self):
        # Set by `control serve`. None means there is no real server to open (e.g. tests), so start()
        # and stop() only have the setting to follow.
        self.port: int | None = None
        self.ip: str | None = None
        self.error: str | None = None
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._category: tuple[float, str | None] | None = None  # (checked at, category)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self._server and self._server.started)

    @property
    def url(self) -> str | None:
        return f"http://{self.ip}:{self.port}" if self.running else None

    @property
    def warning(self) -> str | None:
        """Why phones may fail to connect although the listener runs."""
        if not (self.running and self.ip):
            return None
        if self._category is None or time.monotonic() - self._category[0] > _CATEGORY_TTL:
            self._category = (time.monotonic(), network_category(self.ip))
        return PUBLIC_NETWORK_WARNING if self._category[1] == "Public" else None

    def start(self) -> None:
        with self._lock:
            if self.port is None or self.running:
                return
            if self._thread and self._thread.is_alive():
                # A listener that was told to stop is still shutting down; a second one would clash with it.
                self.error = "Phone access is still stopping. Try again in a moment."
                return
            self.error = None
            ip = lan_ip()
            if ip is None:
                self.error = "This computer isn't connected to a network."
                return
            from .app import app  # the same app as on 127.0.0.1

            # No log settings of its own: uvicorn's loggers are shared, and the main listener configures them.
            config = uvicorn.Config(app, host=ip, port=self.port, lifespan="off", log_config=None, log_level=None)
            server = uvicorn.Server(config)
            # Its own thread and event loop: uvicorn only installs signal handlers on the main thread,
            # so Ctrl+C still stops the main listener, and this daemon thread goes with it.
            thread = threading.Thread(target=server.run, name="lan-listener", daemon=True)
            thread.start()
            deadline = time.monotonic() + 5
            while thread.is_alive() and not server.started and time.monotonic() < deadline:
                time.sleep(0.05)
            self.ip, self._server, self._thread = ip, server, thread
            self._category = None
            if not server.started:
                self.error = f"Couldn't open {ip}:{self.port}. Is another program using that port?"
                self._shut_down()

    def stop(self) -> None:
        with self._lock:
            self.error = None
            self._shut_down()

    def _shut_down(self) -> None:
        """Ask the listener to exit. Its references are kept until the thread has really ended, so a
        slow shutdown (or a slow start that came up late) can't leave an untracked server behind."""
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                return
        self._server = self._thread = None


listener = LanListener()
