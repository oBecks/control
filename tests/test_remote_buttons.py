import base64

import pytest

from control.engine import remote_buttons
from control.engine.remote_buttons import RemoteButtons
from control.engine.signal_library import parse_index

from .test_climate import FakeTransmitter


def b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def test_tv_code_set_converts_to_named_buttons():
    data = {"commands": {"on": b64("ON"), "off": b64("OFF"), "volumeUp": b64("V+"), "nextChannel": b64("C+"),
                         "sources": {"HDMI 1": b64("H1")}}}
    signals = remote_buttons.from_code_set("media_player", data)
    assert signals["kind"] == "tv"
    assert set(signals["buttons"]) == {"power_on", "power_off", "volume_up", "channel_up", "input:HDMI 1"}


def test_fan_code_set_takes_first_direction_speeds():
    data = {"commands": {"off": b64("OFF"), "forward": {"low": b64("L"), "high": b64("H")}, "reverse": {"low": b64("RL")}}}
    buttons = remote_buttons.from_code_set("fan", data)["buttons"]
    assert buttons == {"power_off": b64("OFF"), "speed:low": b64("L"), "speed:high": b64("H")}


def test_power_toggle_never_claims_state():
    tx = FakeTransmitter()
    pad = RemoteButtons({"format": "buttons", "kind": "tv", "buttons": {"power": b64("P")}}, tx, assumed_on=True)
    assert pad.on is None and not pad.features.discrete_power
    pad.set_power(True)
    assert tx.sent == [b"P"] and pad.on is None


def test_discrete_power_tracks_assumed_state():
    tx = FakeTransmitter()
    pad = RemoteButtons({"format": "buttons", "kind": "tv", "buttons": {"power_on": b64("ON"), "power_off": b64("OFF")}}, tx, None)
    pad.set_power(True)
    assert pad.on is True
    pad.set_power(None)  # no target: flips
    assert tx.sent == [b"ON", b"OFF"] and pad.on is False


def test_unknown_button_sends_nothing():
    tx = FakeTransmitter()
    pad = RemoteButtons(remote_buttons.empty("fan"), tx, None)
    with pytest.raises(ValueError):
        pad.press("power")
    assert tx.sent == [] and not pad.features.can_power


def test_labels():
    assert remote_buttons.label("volume_up") == "Volume +"
    assert remote_buttons.label("input:HDMI 1") == "HDMI 1"
    assert remote_buttons.label("speed:medium_low") == "Medium low"


def test_parse_index_rows_without_outer_pipes():
    md = "#### Philips\n| Code | Models | Controller |\n[1001](../codes/media_player/1001.json)|42PFL3007H/60<br>37PF9641D/10|Broadlink\n"
    (s,) = parse_index(md)
    assert (s.code, s.manufacturer, s.models, s.controller) == (1001, "Philips", ["42PFL3007H/60", "37PF9641D/10"], "Broadlink")
