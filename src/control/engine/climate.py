"""The Climate Category (ACs), and Remote Climate: an AC driven by Signals through a Transmitter."""

import base64
from dataclasses import asdict, dataclass, replace
from typing import Protocol


@dataclass
class ClimateFeatures:
    modes: list[str]
    fan_modes: list[str]
    swing_modes: list[str]
    min_temp: float
    max_temp: float
    step: float


@dataclass
class ClimateState:
    on: bool
    mode: str
    target_temp: float
    fan: str
    swing: str | None = None


class Transmitter(Protocol):
    def send(self, signal: bytes) -> None: ...


def features_from_signals(signals: dict) -> ClimateFeatures:
    return ClimateFeatures(
        modes=list(signals["operationModes"]),
        fan_modes=list(signals.get("fanModes") or []),
        swing_modes=list(signals.get("swingModes") or []),
        min_temp=float(signals["minTemperature"]),
        max_temp=float(signals["maxTemperature"]),
        step=float(signals.get("precision") or 1),
    )


def default_state(features: ClimateFeatures) -> ClimateState:
    mode = "cool" if "cool" in features.modes else features.modes[0]
    fan = "auto" if "auto" in features.fan_modes else (features.fan_modes or [""])[0]
    return ClimateState(
        on=False,
        mode=mode,
        target_temp=min(max(24.0, features.min_temp), features.max_temp),
        fan=fan,
        swing=features.swing_modes[0] if features.swing_modes else None,
    )


def signals_for(signals: dict, state: ClimateState) -> list[str]:
    """The Base64 Signals to send to put the AC in `state`. SmartIR nests commands
    as mode -> fan -> [swing ->] temperature, each level present only if the AC has it."""
    commands = signals["commands"]
    if not state.on:
        return [commands["off"]]
    node = commands[state.mode]
    if signals.get("fanModes") and isinstance(node, dict) and state.fan in node:
        node = node[state.fan]
    if signals.get("swingModes") and isinstance(node, dict) and state.swing in node:
        node = node[state.swing]
    if isinstance(node, dict):  # temperature level; keys may be "24" or "24.0"
        key = next((k for k in node if float(k) == state.target_temp), None)
        if key is None:
            raise ValueError(f"no signal for {state.target_temp:g}° in {state.mode}")
        node = node[key]
    # A few code sets need a separate power-on Signal before the mode Signal.
    return ([commands["on"]] if "on" in commands else []) + [node]


def validate(features: ClimateFeatures, state: ClimateState) -> None:
    if state.mode not in features.modes:
        raise ValueError(f"mode must be one of {features.modes}")
    if features.fan_modes and state.fan not in features.fan_modes:
        raise ValueError(f"fan must be one of {features.fan_modes}")
    if features.swing_modes and state.swing not in features.swing_modes:
        raise ValueError(f"swing must be one of {features.swing_modes}")
    if not features.min_temp <= state.target_temp <= features.max_temp:
        raise ValueError(f"temperature must be {features.min_temp:g}-{features.max_temp:g}")


class RemoteClimate:
    """An AC with no network of its own. Its state is an Assumed State: whatever we last sent."""

    def __init__(self, signals: dict, transmitter: Transmitter, assumed: ClimateState | None):
        self.signals = signals
        self.features = features_from_signals(signals)
        self.state = assumed or default_state(self.features)
        self._transmitter = transmitter

    def apply(self, **changes) -> ClimateState:
        """Change any of on/mode/target_temp/fan/swing; unset fields keep their assumed value."""
        changes = {k: v for k, v in changes.items() if v is not None}
        # Like a real remote, changing any setting also turns the AC on.
        if "on" not in changes and changes:
            changes["on"] = True
        new = replace(self.state, **changes)
        validate(self.features, new)
        for b64 in signals_for(self.signals, new):
            # Some community code files drop the trailing "=" padding.
            self._transmitter.send(base64.b64decode(b64 + "=" * (-len(b64) % 4)))
        self.state = new
        return new

    def state_dict(self) -> dict:
        return asdict(self.state)
