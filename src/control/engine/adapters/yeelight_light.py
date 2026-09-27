import json
import socket
import threading
from collections.abc import Callable

import yeelight

from ..errors import DeviceUnreachable
from ..light import LightFeatures, LightState

# Yeelight's color_mode property: 1 = RGB, 2 = color temperature, 3 = HSV.
_COLOR_MODES = {"1", "3"}


class YeelightLight:
    """Local control over the bulb's LAN protocol (TCP 55443). Needs LAN Control enabled."""

    def __init__(self, ip: str):
        # A short effect makes changes feel smooth instead of snapping.
        self._bulb = yeelight.Bulb(ip, effect="smooth", duration=300)
        try:
            # Also teaches the library the bulb's type. Kept for the first get_state(): bulbs
            # rate-limit requests, so a status read shouldn't cost two.
            self._fresh: dict | None = self._bulb.get_properties()
        except (OSError, yeelight.BulbException) as exc:
            raise DeviceUnreachable(f"Yeelight at {ip}: {exc}") from exc
        specs = self._bulb.get_model_specs()
        kelvin = specs.get("color_temp", {})
        self.features = LightFeatures(
            color=self._bulb.bulb_type is yeelight.BulbType.Color,
            color_temp=bool(kelvin),
            min_kelvin=kelvin.get("min", 0),
            max_kelvin=kelvin.get("max", 0),
        )

    def get_state(self) -> LightState:
        props, self._fresh = self._fresh or self._bulb.get_properties(), None
        rgb = int(props.get("rgb") or 0)
        is_color = props.get("color_mode") in _COLOR_MODES
        return LightState(
            on=props.get("power") == "on",
            brightness=int(props.get("current_brightness") or props.get("bright") or 0),
            mode="color" if is_color else "white",
            rgb=((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF) if is_color else None,
            kelvin=None if is_color else int(props.get("ct") or 0),
        )

    def turn_on(self) -> None:
        self._fresh = None  # state is about to change
        self._bulb.turn_on()

    def turn_off(self) -> None:
        self._fresh = None  # state is about to change
        self._bulb.turn_off()

    def set_brightness(self, percent: int) -> None:
        self._fresh = None  # state is about to change
        self._bulb.set_brightness(max(1, min(100, percent)))

    def set_rgb(self, r: int, g: int, b: int) -> None:
        self._fresh = None  # state is about to change
        if not self.features.color:
            raise ValueError("this light has no color")
        self._bulb.set_rgb(r, g, b)

    def set_kelvin(self, kelvin: int) -> None:
        self._fresh = None  # state is about to change
        if not self.features.color_temp:
            raise ValueError("this light has no adjustable white")
        self._bulb.set_color_temp(max(self.features.min_kelvin, min(self.features.max_kelvin, kelvin)))


# --- Listening (ADR 0011) ---------------------------------------------------------------

PORT = 55443
RETRY_SECONDS = 5
# TCP keep-alive: probes after 10 s of quiet, every 3 s; Windows gives up after 10, so a bulb that
# lost power is noticed in about 40 s without spending any of its rate-limited requests.
KEEPALIVE_IDLE_MS, KEEPALIVE_EVERY_MS = 10_000, 3_000


def keep_alive(sock: socket.socket) -> None:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    if hasattr(socket, "SIO_KEEPALIVE_VALS"):  # Windows
        sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, KEEPALIVE_IDLE_MS, KEEPALIVE_EVERY_MS))
    elif hasattr(socket, "TCP_KEEPIDLE"):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, KEEPALIVE_IDLE_MS // 1000)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, KEEPALIVE_EVERY_MS // 1000)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 10)


class YeelightWatch:
    """Holds a connection to a bulb and reports its power as the bulb pushes changes ("props"
    notifications, sent on every open connection). Costs one request per (re)connection: the first
    reading. `report(uid, {"on": bool})` on each answer, `report(uid, None)` when the connection is lost.
    `address()` gives the bulb's IP, read again before each reconnection in case a Scan moved it."""

    def __init__(self, uid: str, address: Callable[[], str | None], report: Callable[[str, dict | None], None]):
        self._uid, self._address, self._report = uid, address, report
        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self._thread = threading.Thread(target=self._loop, name=f"listen-{uid}", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        sock = self._sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._listen()
            except (OSError, ValueError):
                pass
            finally:
                if self._sock is not None:
                    self._sock.close()
                    self._sock = None
            if self._stop.is_set():
                return
            self._report(self._uid, None)
            self._stop.wait(RETRY_SECONDS)

    def _listen(self) -> None:
        ip = self._address()
        if not ip:
            return
        self._sock = sock = socket.create_connection((ip, PORT), timeout=5)
        if self._stop.is_set():
            return
        keep_alive(sock)
        sock.sendall(json.dumps({"id": 1, "method": "get_prop", "params": ["power"]}).encode() + b"\r\n")
        sock.settimeout(None)  # quiet for hours is fine: keep-alive notices a dead bulb
        buffer = b""
        while not self._stop.is_set():
            data = sock.recv(4096)
            if not data:
                return  # the bulb closed it
            buffer += data
            *lines, buffer = buffer.split(b"\r\n")
            for line in lines:
                if power := _power(line):
                    self._report(self._uid, {"on": power == "on"})


def _power(line: bytes) -> str | None:
    """"on" or "off" from the answer to our get_prop or a props notification; None otherwise."""
    try:
        msg = json.loads(line)
    except ValueError:
        return None
    if msg.get("id") == 1 and isinstance(msg.get("result"), list) and msg["result"]:
        return msg["result"][0]
    if msg.get("method") == "props":
        return msg.get("params", {}).get("power")
    return None
