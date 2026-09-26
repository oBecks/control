import time

import broadlink
from broadlink.exceptions import BroadlinkException, ReadError, StorageError

from ..errors import DeviceUnreachable


class BroadlinkTransmitter:
    """Sends IR/RF Signals through a Broadlink RM, locally (UDP 80). Needs the device unlocked."""

    def __init__(self, ip: str, mac: str, devtype: int):
        self._ip = ip
        self._dev = broadlink.gendevice(devtype, (ip, 80), bytes.fromhex(mac.replace(":", "")))
        if not hasattr(self._dev, "send_data"):
            raise ValueError(f"Broadlink at {ip} can't send signals")
        try:
            self._dev.auth()
        except (OSError, BroadlinkException) as exc:
            raise DeviceUnreachable(f"Broadlink at {ip}: {exc}") from exc

    def send(self, signal: bytes) -> None:
        try:
            self._dev.send_data(signal)
        except (OSError, BroadlinkException) as exc:
            raise DeviceUnreachable(f"Broadlink at {self._ip}: {exc}") from exc

    def learn(self, timeout: float = 20) -> bytes | None:
        """Learning: wait for the user to press a button on their remote, pointed at the
        Broadlink (its LED lights up meanwhile). Returns the Signal, or None on timeout."""
        self._dev.enter_learning()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(0.5)
            try:
                return self._dev.check_data()
            except (ReadError, StorageError):
                continue  # nothing received yet
        return None
