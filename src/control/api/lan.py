"""Phone access (ADR 0003): a second listener on this machine's LAN addresses, running only while the
user has Phone access turned on. The main listener always stays on 127.0.0.1, so Windows only asks
to allow Control on the network once the user opts in."""

import ipaddress
import json
import logging
import socket
import subprocess
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import psutil
import uvicorn

log = logging.getLogger(__name__)

_PRIVATE = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
# Adapters phones can't reach this machine through: VMs, WSL, containers, VPNs. Told apart by name
# only, so it's best effort.
_VIRTUAL = ("vethernet", "virtualbox", "vmware", "hyper-v", "wsl", "docker", "loopback", "vpn", "tap-",
            "tailscale", "zerotier", "bluetooth")
_PHYSICAL = ("wi-fi", "wifi", "wireless", "wlan", "ethernet")
WATCH_EVERY = 30  # seconds between checks for changed addresses


def _default_route_ip() -> str | None:
    """The address of the interface Windows sends outside traffic through."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))  # UDP connect sends nothing; it only picks the outgoing interface
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def lan_ips() -> list[str]:
    """The addresses other devices on the home network may reach this machine at, most likely first:
    every private IPv4 address of a connected adapter that isn't a known virtual one. Wi-Fi and
    Ethernet adapters come first, then the default route's."""
    stats = psutil.net_if_stats()
    default = _default_route_ip()
    found = []  # (not Wi-Fi/Ethernet, not the default route's, ip)
    for name, addrs in psutil.net_if_addrs().items():
        # Windows may put direction marks in adapter names (e.g. "‏‏Ethernet" on a Hebrew system).
        plain = "".join(c for c in name if unicodedata.category(c) != "Cf").lower()
        if not (name in stats and stats[name].isup) or any(v in plain for v in _VIRTUAL):
            continue
        for a in addrs:
            if a.family == socket.AF_INET and any(ipaddress.ip_address(a.address) in n for n in _PRIVATE):
                found.append((not any(p in plain for p in _PHYSICAL), a.address != default, a.address))
    return list(dict.fromkeys(ip for *_, ip in sorted(found)))


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
    """Listens on every address from lan_ips() while Phone access is on, and follows them when they
    change (a new DHCP lease, another network)."""

    def __init__(self):
        # Set by `control serve`. None means there is no real server to open (e.g. tests), so start()
        # and stop() only have the setting to follow.
        self.port: int | None = None
        self.ip: str | None = None  # what Settings shows phones: the most likely of `ips`
        self.ips: list[str] = []  # every address listened on
        self._asked: list[str] = []  # what lan_ips() said when it opened; some may not have opened
        self.moved_from: str | None = None  # what phones opened before the address changed
        self.error: str | None = None
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._check: tuple[float, NetworkCheck] | None = None  # (checked at, result)
        self._checking = False
        self._wanted = threading.Event()  # Phone access is on
        self._watcher: threading.Thread | None = None

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
            if self.port is None:
                return
            self._wanted.set()
            if not self.running:
                self.moved_from = None
                self._open(lan_ips())
            if not (self._watcher and self._watcher.is_alive()):
                self._watcher = threading.Thread(target=self._watch, name="lan-watch", daemon=True)
                self._watcher.start()

    def stop(self) -> None:
        with self._lock:
            self._wanted.clear()
            self.error = self.moved_from = None
            self._shut_down()

    def refresh(self) -> None:
        """Follow this machine's addresses: reopen on the new ones, or open once it's on a network again."""
        with self._lock:
            if not self._wanted.is_set():
                return
            ips = lan_ips()
            if self.running and ips == self._asked:
                return
            before = self.url
            self._shut_down()
            if self._thread:  # the old listener hasn't ended yet; the next check tries again
                return
            self._open(ips)
            if before and self.url and self.url != before:
                self.moved_from = before

    def _watch(self) -> None:
        while self._wanted.is_set():
            time.sleep(WATCH_EVERY)
            try:
                self.refresh()
            except Exception:
                log.exception("Checking this computer's network addresses failed")

    def _open(self, ips: list[str]) -> None:
        """Listen on whichever of `ips` can be opened. Call with the lock held."""
        if self._thread and self._thread.is_alive():
            # A listener that was told to stop is still shutting down; a second one would clash with it.
            self.error = "Phone access is still stopping. Try again in a moment."
            return
        self.error = None
        if not ips:
            self.error = "This computer isn't connected to a network."
            return
        sockets = []
        for ip in ips:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.bind((ip, self.port))
            except OSError:
                sock.close()
                continue
            sockets.append(sock)
        if not sockets:
            self.error = f"Couldn't open {ips[0]}:{self.port}. Is another program using that port?"
            return
        from .app import app  # the same app as on 127.0.0.1

        # No log settings of its own: uvicorn's loggers are shared, and the main listener configures them.
        config = uvicorn.Config(app, port=self.port, lifespan="off", log_config=None, log_level=None)
        server = uvicorn.Server(config)
        # Its own thread and event loop: uvicorn only installs signal handlers on the main thread,
        # so Ctrl+C still stops the main listener, and this daemon thread goes with it.
        thread = threading.Thread(target=server.run, kwargs={"sockets": sockets}, name="lan-listener", daemon=True)
        thread.start()
        deadline = time.monotonic() + 5
        while thread.is_alive() and not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        self._asked, self.ips = ips, [s.getsockname()[0] for s in sockets]
        self.ip, self._server, self._thread = self.ips[0], server, thread
        self._check = None
        if not server.started:
            self.error = f"Couldn't open {self.ip}:{self.port}."
            self._shut_down()
            for s in sockets:
                s.close()

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
