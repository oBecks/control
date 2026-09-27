import select
import socket
import threading
import time
from collections.abc import Callable

import tinytuya

from ..errors import DeviceUnreachable
from ..plug import PlugState

# Tuya plugs expose their relay as data point 1 ("switch_1").
_SWITCH_DP = "1"
SOCKET_TIMEOUT = 3  # seconds per try; tinytuya tries twice
CONNECT_SECONDS = 2 * SOCKET_TIMEOUT + 2  # the longest a connection attempt takes, with a margin


class TuyaPlug:
    """Local control over Tuya's LAN protocol (TCP 6668), encrypted with the device's Local Key.

    A plug takes one local connection at a time, so while it's listened to (TuyaWatch) its commands go
    over the listening connection, and its state is the one the plug last pushed: no request at all."""

    def __init__(self, device_id: str, ip: str, local_key: str, version: str):
        self._ip = ip
        self._watch = _watches.get(device_id)
        if self._watch is not None and self._watch.wait_connected():
            return
        self._watch = None
        self._dev = _device(device_id, ip, local_key, version)
        self.get_state()  # fail fast, like the other adapters

    def _check(self, result: dict | None) -> dict:
        return _checked(result, self._ip)

    def get_state(self) -> PlugState:
        if self._watch is not None:
            return PlugState(on=bool(self._watch.on))
        dps = self._check(self._dev.status()).get("dps", {})
        return PlugState(on=bool(dps.get(_SWITCH_DP)))

    def turn_on(self) -> None:
        if self._watch is not None:
            self._watch.switch(True)
            return
        self._check(self._dev.turn_on(switch=int(_SWITCH_DP)))

    def turn_off(self) -> None:
        if self._watch is not None:
            self._watch.switch(False)
            return
        self._check(self._dev.turn_off(switch=int(_SWITCH_DP)))


def _device(device_id: str, ip: str, local_key: str, version: str) -> tinytuya.OutletDevice:
    dev = tinytuya.OutletDevice(device_id, address=ip, local_key=local_key, version=float(version))
    dev.set_socketTimeout(SOCKET_TIMEOUT)
    dev.set_socketRetryLimit(1)
    return dev


def _checked(result: dict | None, ip: str) -> dict:
    # tinytuya reports failures as {"Error": ..., "Err": code} instead of raising.
    if not result or "Error" in result:
        err = (result or {}).get("Error", "no response")
        raise DeviceUnreachable(f"Tuya at {ip}: {err}")
    return result


# --- Listening (ADR 0011) ---------------------------------------------------------------

HEARTBEAT_SECONDS = 15  # the plug closes a quiet connection after ~30 s
SILENT_SECONDS = 35  # nothing heard for this long (heartbeats go unanswered): the connection is lost
RETRY_SECONDS = 5

_watches: dict[str, "TuyaWatch"] = {}  # device id -> its watch


class TuyaWatch:
    """Holds the plug's one local connection: the plug pushes its status when the relay changes (a
    press on the plug, the Smart Life app), and answers a heartbeat every HEARTBEAT_SECONDS.
    `report(uid, {"on": bool})` on each answer, `report(uid, None)` when the connection is lost.
    `address()` gives the plug's IP, read again before each reconnection."""

    def __init__(self, uid: str, local_key: str, version: str, address: Callable[[], str | None],
                 report: Callable[[str, dict | None], None]):
        self._uid, self._key, self._version = uid, local_key, version
        self._address, self._report = address, report
        self._id = uid.removeprefix("tuya:")
        self._lock = threading.Lock()  # one message at a time on the connection
        self._stop = threading.Event()
        self._dev: tinytuya.OutletDevice | None = None
        self.connected = False
        self._connecting = threading.Event()  # set while it's opening the plug's one connection
        self._ready = threading.Event()  # set while connected
        self.on: bool | None = None
        _watches[self._id] = self
        self._connecting.set()  # from the start, so a command right away waits for it
        self._thread = threading.Thread(target=self._loop, name=f"listen-{uid}", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if _watches.get(self._id) is self:
            del _watches[self._id]
        with self._lock:  # frees the plug's one connection now, not at the next heartbeat
            self.connected = False
            if self._dev is not None:
                self._dev.close()

    def wait_connected(self) -> bool:
        """Whether commands can go over this connection. While it's being opened, wait until that
        attempt ends (it's bounded by the socket's timeout and one retry) rather than open a second
        connection, which the plug would refuse."""
        deadline = time.monotonic() + CONNECT_SECONDS
        while self._connecting.is_set() and not self._ready.wait(0.1) and time.monotonic() < deadline:
            pass
        return self.connected

    def switch(self, on: bool) -> None:
        """A command from Control, over the listening connection."""
        with self._lock:
            dev = self._dev
            if dev is None or not self.connected:
                raise DeviceUnreachable(f"Tuya {self._id}: not connected")
            result = _checked(dev.turn_on(switch=int(_SWITCH_DP)) if on else dev.turn_off(switch=int(_SWITCH_DP)),
                              dev.address)
        self._heard(result)

    def _heard(self, result: dict | None) -> None:
        dps = (result or {}).get("dps") or {}
        if _SWITCH_DP in dps:
            self.on = bool(dps[_SWITCH_DP])
        if self.on is not None:
            self._report(self._uid, {"on": self.on})

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._listen()
            except (OSError, ValueError, DeviceUnreachable):
                pass
            finally:
                self.connected = False
                self._ready.clear()
                self._connecting.clear()
                with self._lock:
                    if self._dev is not None:
                        self._dev.close()
                        self._dev = None
            if self._stop.is_set():
                return
            self._report(self._uid, None)
            self._stop.wait(RETRY_SECONDS)

    @staticmethod
    def _read(dev: tinytuya.OutletDevice) -> dict | None | bool:
        """What arrived, None for an empty message (a heartbeat's answer), False when the plug
        closed the connection."""
        sock = dev.socket
        if sock is None or not select.select([sock], [], [], 0)[0]:
            return None  # a command read it meanwhile
        if not sock.recv(1, socket.MSG_PEEK):
            return False
        dev.retry = False  # an empty message is the whole answer: don't wait for another
        try:
            return dev.receive()
        finally:
            dev.retry = True

    def _listen(self) -> None:
        ip = self._address()
        if not ip:
            return
        self._connecting.set()
        with self._lock:
            self._dev = dev = _device(self._id, ip, self._key, self._version)
            dev.set_socketPersistent(True)
            status = _checked(dev.status(), ip)
        self.connected = True
        self._ready.set()
        self._connecting.clear()
        self._heard(status)
        heard = beat = time.monotonic()
        while not self._stop.is_set():
            sock = dev.socket
            if sock is None:
                return
            readable, _, _ = select.select([sock], [], [], max(0.0, beat + HEARTBEAT_SECONDS - time.monotonic()))
            if readable:
                with self._lock:
                    msg = self._read(dev)
                if msg is False or (isinstance(msg, dict) and "Error" in msg):
                    return
                heard = time.monotonic()
                if msg:
                    self._heard(msg)
            now = time.monotonic()
            if now - heard > SILENT_SECONDS:
                return
            if now - beat >= HEARTBEAT_SECONDS:
                with self._lock:
                    dev.heartbeat(nowait=True)
                beat = now
