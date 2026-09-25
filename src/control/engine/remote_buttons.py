"""Button Remote Devices (TVs, fans, anything else): Signals named after the remote's buttons.

Stored as {"format": "buttons", "kind": "tv"|"fan"|"other", "buttons": {name: base64}}.
They come from Learning or from a Signal Library Code Set converted to button names.
Power is either a Power Toggle ("power") or discrete "power_on"/"power_off"; only the
latter allows an Assumed State (see CONTEXT.md).
"""

import base64
from dataclasses import dataclass
from typing import Literal

from .climate import Transmitter
from .found_device import Category

Kind = Literal["tv", "fan", "other"]

CATEGORY: dict[str, Category] = {"tv": Category.MEDIA, "fan": Category.CLIMATE, "other": Category.UNKNOWN}

# Buttons offered when Learning, in the order they're asked. Each can be skipped.
SUGGESTED: dict[str, list[tuple[str, str]]] = {
    "tv": [
        ("power", "Power"), ("volume_up", "Volume +"), ("volume_down", "Volume −"), ("mute", "Mute"),
        ("channel_up", "Channel +"), ("channel_down", "Channel −"), ("input", "Input / Source"), ("home", "Home"),
        ("up", "Up"), ("down", "Down"), ("left", "Left"), ("right", "Right"), ("ok", "OK"), ("back", "Back"),
    ],
    "fan": [("power", "Power"), ("speed_up", "Speed +"), ("speed_down", "Speed −"), ("oscillate", "Oscillate"), ("timer", "Timer")],
    "other": [("power", "Power")],
}

_LABELS = {name: label for buttons in SUGGESTED.values() for name, label in buttons} | {
    "power_on": "On", "power_off": "Off",
}


def label(name: str) -> str:
    if name in _LABELS:
        return _LABELS[name]
    prefix, _, rest = name.partition(":")
    if rest:  # "input:HDMI 1", "speed:high"
        return rest if prefix == "input" else rest.replace("_", " ").capitalize()
    return name.replace("_", " ").capitalize()


def empty(kind: Kind) -> dict:
    return {"format": "buttons", "kind": kind, "buttons": {}}


def from_code_set(domain: str, data: dict) -> dict:
    """Convert a SmartIR media_player or fan Code Set into button names."""
    c = data["commands"]
    buttons: dict[str, str] = {}
    if domain == "media_player":
        names = {"on": "power_on", "off": "power_off", "volumeUp": "volume_up", "volumeDown": "volume_down",
                 "mute": "mute", "nextChannel": "channel_up", "previousChannel": "channel_down"}
        buttons = {names[k]: v for k, v in c.items() if k in names and isinstance(v, str)}
        for source, sig in (c.get("sources") or {}).items():
            buttons[f"input:{source}"] = sig
        return {"format": "buttons", "kind": "tv", "buttons": buttons}
    if domain == "fan":
        if isinstance(c.get("off"), str):
            buttons["power_off"] = c["off"]
        # Speeds are nested under a direction ("forward"/"default"); take the first one.
        speeds = next((v for k, v in c.items() if k != "off" and isinstance(v, dict)), {})
        for speed, sig in speeds.items():
            if isinstance(sig, str):
                buttons[f"speed:{speed}"] = sig
        if isinstance(c.get("oscillate"), str):
            buttons["oscillate"] = c["oscillate"]
        return {"format": "buttons", "kind": "fan", "buttons": buttons}
    raise ValueError(f"can't turn a '{domain}' code set into buttons")


@dataclass
class ButtonFeatures:
    kind: str
    buttons: list[dict]  # [{"name", "label"}]
    discrete_power: bool  # separate On/Off Signals, so on/off can be an Assumed State
    can_power: bool


class RemoteButtons:
    def __init__(self, signals: dict, transmitter: Transmitter, assumed_on: bool | None):
        self.signals = signals
        self._tx = transmitter
        names = list(signals["buttons"])
        self.features = ButtonFeatures(
            kind=signals.get("kind", "other"),
            buttons=[{"name": n, "label": label(n)} for n in names],
            discrete_power="power_on" in names and "power_off" in names,
            can_power=bool({"power", "power_on", "power_off"} & set(names)),
        )
        # With only a Power Toggle, power state is unknowable.
        self.on: bool | None = assumed_on if self.features.discrete_power else None

    def press(self, name: str) -> None:
        sig = self.signals["buttons"].get(name)
        if sig is None:
            raise ValueError(f"no '{label(name)}' button")
        self._tx.send(base64.b64decode(sig + "=" * (-len(sig) % 4)))
        if name == "power_on":
            self.on = True
        elif name == "power_off":
            self.on = False

    def set_power(self, on: bool | None) -> None:
        """on=None, or no discrete power: send the Power Toggle."""
        if self.features.discrete_power and on is not None:
            self.press("power_on" if on else "power_off")
        elif "power" in self.signals["buttons"]:
            self.press("power")
        elif self.features.discrete_power:
            # No toggle and no target: flip the assumed state.
            self.press("power_off" if self.on else "power_on")
        else:
            raise ValueError("this device has no power button yet")
