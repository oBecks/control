"""Phone access (ADR 0003): a second listener on this machine's LAN address, running only while the
user has Phone access turned on. The main listener always stays on 127.0.0.1, so Windows only asks
to allow Control on the network once the user opts in."""

import json
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

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
_CHECK_TTL = 15  # seconds; Settings polls often and the lookup takes a few seconds


def firewall_program() -> str:
    """The program Windows Firewall rules are about: Control.exe, or Python when run from source."""
    if getattr(sys, "frozen", False):
        return sys.executable
    # A venv's python.exe only launches the base interpreter, which is what opens the port.
    return getattr(sys, "_base_executable", sys.executable)


def firewall_warning(program: str) -> str:
    file = Path(program).name
    name = "Control" if getattr(sys, "frozen", False) else "Python"
    return (f"Windows Firewall is blocking {name}, so phones can't connect. In Windows Security → Firewall & "
            f"network protection → Allow an app through firewall, click Change settings, tick Private for "
            f"{name} ({file.lower()}), and click OK.")


@dataclass(frozen=True)
class NetworkCheck:
    category: str | None  # Windows' firewall profile: "Public", "Private", "DomainAuthenticated"; None if unknown
    blocked: bool  # a Windows Firewall rule blocks `program` from this network


_CHECK_SCRIPT = """
$c = "$((Get-NetIPAddress -IPAddress '{ip}' | Get-NetConnectionProfile).NetworkCategory)"
$p = if ($c -eq 'DomainAuthenticated') {{ 'Domain' }} else {{ $c }}
$b = @(Get-NetFirewallApplicationFilter -Program '{program}' -ErrorAction SilentlyContinue | Get-NetFirewallRule |
  Where-Object {{ $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Block' -and
                 ("$($_.Profile)" -eq 'Any' -or "$($_.Profile)" -match $p) }}).Count
@{{ category = $c; blocked = ($b -gt 0) }} | ConvertTo-Json -Compress
"""


def network_check(ip: str, program: str) -> NetworkCheck:
    """What Windows does to phones reaching `program` at `ip`. Nothing known on other systems.

    A missed or cancelled "Allow access?" prompt leaves Block rules behind, and Windows never asks
    again, not even after a reinstall; the user has to allow the program by hand."""
    if sys.platform != "win32":
        return NetworkCheck(None, False)
    script = _CHECK_SCRIPT.format(ip=ip, program=program.replace("'", "''"))
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout.strip()
        found = json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        return NetworkCheck(None, False)
    return NetworkCheck(found.get("category") or None, bool(found.get("blocked")))


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
        self._check: tuple[float, NetworkCheck] | None = None  # (checked at, result)
        self._checking = False

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
        # The check takes seconds, so it runs in the background and Settings gets the last result.
        if not self._checking and (self._check is None or time.monotonic() - self._check[0] > _CHECK_TTL):
            self._checking = True
            threading.Thread(target=self._run_check, args=(self.ip,), name="network-check", daemon=True).start()
        if self._check is None:
            return None
        check = self._check[1]
        if check.blocked:
            return firewall_warning(firewall_program())
        return PUBLIC_NETWORK_WARNING if check.category == "Public" else None

    def _run_check(self, ip: str) -> None:
        try:
            self._check = (time.monotonic(), network_check(ip, firewall_program()))
        finally:
            self._checking = False

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
            self._check = None
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
