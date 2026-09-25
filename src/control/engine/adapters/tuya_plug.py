import tinytuya

from ..errors import DeviceUnreachable
from ..plug import PlugState

# Tuya plugs expose their relay as data point 1 ("switch_1").
_SWITCH_DP = "1"


class TuyaPlug:
    """Local control over Tuya's LAN protocol (TCP 6668), encrypted with the device's Local Key."""

    def __init__(self, device_id: str, ip: str, local_key: str, version: str):
        self._dev = tinytuya.OutletDevice(device_id, address=ip, local_key=local_key, version=float(version))
        self._dev.set_socketTimeout(3)
        self._dev.set_socketRetryLimit(1)
        self._ip = ip
        self.get_state()  # fail fast, like the other adapters

    def _check(self, result: dict | None) -> dict:
        # tinytuya reports failures as {"Error": ..., "Err": code} instead of raising.
        if not result or "Error" in result:
            err = (result or {}).get("Error", "no response")
            raise DeviceUnreachable(f"Tuya at {self._ip}: {err}")
        return result

    def get_state(self) -> PlugState:
        dps = self._check(self._dev.status()).get("dps", {})
        return PlugState(on=bool(dps.get(_SWITCH_DP)))

    def turn_on(self) -> None:
        self._check(self._dev.turn_on(switch=int(_SWITCH_DP)))

    def turn_off(self) -> None:
        self._check(self._dev.turn_off(switch=int(_SWITCH_DP)))
