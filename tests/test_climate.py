import base64

import pytest

from control.engine.climate import ClimateState, RemoteClimate, signals_for
from control.engine.found_device import Category
from control.engine.registry import Registry
from control.engine.signal_library import parse_index


def b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


SIGNALS = {
    "minTemperature": 16.0,
    "maxTemperature": 30.0,
    "precision": 1.0,
    "operationModes": ["cool", "heat"],
    "fanModes": ["auto", "low"],
    "commands": {
        "off": b64("OFF"),
        "cool": {"auto": {"24": b64("C-A-24"), "25": b64("C-A-25")}, "low": {"24": b64("C-L-24")}},
        "heat": {"auto": {"24.0": b64("H-A-24")}},
    },
}

SWING_SIGNALS = {
    **SIGNALS,
    "swingModes": ["static", "swing"],
    "commands": {"off": b64("OFF"), "cool": {"auto": {"swing": {"24": b64("C-A-S-24")}}}},
}


class FakeTransmitter:
    def __init__(self):
        self.sent: list[bytes] = []

    def send(self, signal: bytes) -> None:
        self.sent.append(signal)


def test_signal_lookup_walks_mode_fan_temp():
    state = ClimateState(on=True, mode="cool", target_temp=25, fan="auto")
    assert signals_for(SIGNALS, state) == [b64("C-A-25")]


def test_signal_lookup_handles_float_keys_and_swing():
    assert signals_for(SIGNALS, ClimateState(True, "heat", 24, "auto")) == [b64("H-A-24")]
    assert signals_for(SWING_SIGNALS, ClimateState(True, "cool", 24, "auto", "swing")) == [b64("C-A-S-24")]


def test_off_ignores_other_settings():
    assert signals_for(SIGNALS, ClimateState(False, "heat", 99, "nope")) == [b64("OFF")]


def test_changing_a_setting_turns_it_on_and_keeps_the_rest():
    tx = FakeTransmitter()
    ac = RemoteClimate(SIGNALS, tx, None)
    assert not ac.state.on
    ac.apply(fan="low")
    assert tx.sent == [b"C-L-24"]
    assert (ac.state.on, ac.state.mode, ac.state.target_temp, ac.state.fan) == (True, "cool", 24, "low")
    ac.apply(on=False)
    assert tx.sent[-1] == b"OFF" and ac.state.fan == "low"


def test_unpadded_signal_is_accepted():
    tx = FakeTransmitter()
    signals = {**SIGNALS, "commands": {**SIGNALS["commands"], "off": b64("OFF!").rstrip("=")}}
    RemoteClimate(signals, tx, None).apply(on=False)
    assert tx.sent == [b"OFF!"]


def test_invalid_state_sends_nothing():
    tx = FakeTransmitter()
    ac = RemoteClimate(SIGNALS, tx, None)
    with pytest.raises(ValueError):
        ac.apply(target_temp=40)
    with pytest.raises(ValueError):
        ac.apply(mode="dry")
    assert tx.sent == [] and not ac.state.on


def test_parse_index():
    md = """#### Electra
| Code | Supported Models | Controller |
| ---- | ---------------- | ---------- |
| [1942](../codes/climate/1942.json) | Electra Classic  | Broadlink  |
| [1944](../codes/climate/1944.json) | A<br>B <b>(Swing)</b>| Broadlink  |
#### Other
| [5000](../codes/climate/5000.json) | X | Xiaomi |
"""
    sets = parse_index(md)
    assert [(s.code, s.manufacturer, s.controller) for s in sets] == [
        (1942, "Electra", "Broadlink"),
        (1944, "Electra", "Broadlink"),
        (5000, "Other", "Xiaomi"),
    ]
    assert sets[1].models == ["A", "B (Swing)"]


def test_remote_device_round_trip(tmp_path):
    r = Registry(tmp_path / "t.db")
    uid = r.add_remote("Living room AC", Category.CLIMATE, "broadlink:aa", "smartir:climate:1942", SIGNALS)
    with pytest.raises(ValueError):
        r.add_remote("living room ac", Category.CLIMATE, "broadlink:aa", "x", SIGNALS)
    r.set_assumed_state(uid, {"on": True, "mode": "cool", "target_temp": 24, "fan": "auto", "swing": None})
    remote = r.resolve_remote("LIVING ROOM AC")
    assert remote.assumed_state["on"] and remote.signals == SIGNALS
    r.set_remote_signals(uid, "smartir:climate:1944", SWING_SIGNALS)
    assert r.resolve_remote(uid).assumed_state is None
    r.close()
