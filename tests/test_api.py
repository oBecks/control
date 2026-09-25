import pytest
from fastapi.testclient import TestClient

from control.api import app as api
from control.engine import connect
from control.engine.found_device import Category, FoundDevice, Readiness
from control.engine.light import LightFeatures, LightState
from control.engine.registry import Registry

from .test_climate import SIGNALS, FakeTransmitter


class FakeLight:
    features = LightFeatures(color=True, color_temp=True, min_kelvin=1700, max_kelvin=6500)

    def __init__(self):
        self.state = LightState(on=False, brightness=50, mode="white", kelvin=4000)
        self.calls = []

    def get_state(self):
        return self.state

    def turn_on(self):
        self.calls.append("on")
        self.state.on = True

    def turn_off(self):
        self.calls.append("off")
        self.state.on = False

    def set_brightness(self, p):
        self.calls.append(("brightness", p))
        self.state.brightness = p

    def set_rgb(self, *rgb):
        self.calls.append(("rgb", rgb))

    def set_kelvin(self, k):
        self.calls.append(("kelvin", k))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROL_DATA_DIR", str(tmp_path))
    r = Registry()
    r.merge_scan([
        FoundDevice("Yeelight", "10.0.0.2", "yeelight:1", Category.LIGHT, Readiness.READY, model="color"),
        FoundDevice("Tuya", "10.0.0.3", "tuya:abc", Category.UNKNOWN, Readiness.NEEDS_LINK),
        FoundDevice("Broadlink", "10.0.0.4", "broadlink:aa", Category.TRANSMITTER, Readiness.READY,
                    mac="aa", raw={"devtype": 1}),
    ])
    r.add_remote("AC", Category.CLIMATE, "broadlink:aa", "smartir:climate:1", SIGNALS)
    r.close()
    return TestClient(api.app, base_url="http://localhost", client=("127.0.0.1", 50000))  # the PC itself


def by_uid(devices):
    return {d["uid"]: d for d in devices}


def test_list_devices_marks_what_is_controllable(client):
    devices = client.get("/api/devices").json()
    d = by_uid(devices)
    assert d["yeelight:1"]["control"] == "light"
    assert d["tuya:abc"]["control"] is None  # not linked yet
    assert d["broadlink:aa"]["control"] is None
    ac = next(x for x in devices if x["kind"] == "remote")
    assert (ac["name"], ac["control"]) == ("AC", "climate")


def test_link_makes_plug_controllable(client):
    r = Registry()
    r.save_link("tuya:abc", "Outlet", Category.PLUG, {"local_key": "k"})
    r.close()
    d = client.get("/api/devices/tuya:abc").json()
    assert (d["name"], d["control"]) == ("Outlet", "plug")


def test_rename_and_seen(client):
    d = client.patch("/api/devices/yeelight:1", json={"name": "Desk", "seen": True}).json()
    assert (d["name"], d["is_new"]) == ("Desk", False)


def test_errors_map_to_status_codes(client):
    assert client.get("/api/devices/nope").status_code == 404
    ac_uid = next(d["uid"] for d in client.get("/api/devices").json() if d["kind"] == "remote")
    r = Registry()
    r.add_remote("Bedroom AC", Category.CLIMATE, "broadlink:aa", "x", SIGNALS)
    r.close()
    assert client.patch(f"/api/devices/{ac_uid}", json={"name": "bedroom ac"}).status_code == 422


def test_set_light_state_turns_on_when_changing_a_setting(client, monkeypatch):
    light = FakeLight()
    monkeypatch.setattr(api, "connect_light", lambda r, uid: (None, light))
    body = client.post("/api/devices/yeelight:1/state", json={"brightness": 70}).json()
    assert light.calls == ["on", ("brightness", 70)]
    assert body["state"]["on"] and body["state"]["brightness"] == 70


def test_set_climate_state_persists_assumed_state(client, monkeypatch):
    tx = FakeTransmitter()
    monkeypatch.setattr(connect, "connect_transmitter", lambda r, uid: (None, tx))
    ac_uid = next(d["uid"] for d in client.get("/api/devices").json() if d["kind"] == "remote")

    body = client.post(f"/api/devices/{ac_uid}/state", json={"target_temp": 25}).json()
    assert body["assumed"] and body["state"]["on"] and body["state"]["target_temp"] == 25
    assert tx.sent == [b"C-A-25"]
    # The Assumed State is remembered for the next read.
    assert client.get(f"/api/devices/{ac_uid}/state").json()["state"]["target_temp"] == 25
    assert client.post(f"/api/devices/{ac_uid}/state", json={"target_temp": 99}).status_code == 422


def test_probe_then_add_with_assumed_state(client, monkeypatch):
    tx = FakeTransmitter()
    monkeypatch.setattr(api, "connect_transmitter", lambda r, uid: (None, tx))
    monkeypatch.setattr(connect, "connect_transmitter", lambda r, uid: (None, tx))
    monkeypatch.setattr(api.signal_library, "load_climate", lambda code: SIGNALS)
    monkeypatch.setattr(api.code_set_finder.time, "sleep", lambda s: None)

    resp = client.post("/api/remote-devices/probe", json={"code_sets": [7, 8]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    temps = body["assignment"]
    assert set(temps) == {"7", "8"} and len(set(temps.values())) == 2 and len(tx.sent) == 2

    ac = client.post("/api/remote-devices", json={"name": "Den AC", "code_set": 8, "probe_temp": temps["8"]}).json()
    state = client.get(f"/api/devices/{ac['uid']}/state").json()["state"]
    assert state["on"] and state["target_temp"] == temps["8"]
    assert client.post("/api/remote-devices", json={"name": " ", "code_set": 8}).status_code == 422


def test_mark_all_seen(client):
    assert any(d["is_new"] for d in client.get("/api/devices").json())
    client.post("/api/devices/seen")
    assert not any(d["is_new"] for d in client.get("/api/devices").json())


class FakeLearner(FakeTransmitter):
    def learn(self, timeout):
        return b"LEARNED"


def test_learn_save_and_press_a_tv_button(client, monkeypatch):
    tx = FakeLearner()
    monkeypatch.setattr(api, "connect_transmitter", lambda r, uid: (None, tx))
    monkeypatch.setattr(connect, "connect_transmitter", lambda r, uid: (None, tx))

    tv = client.post("/api/remote-devices/buttons", json={"name": "TV", "kind": "tv"}).json()
    assert (tv["category"], tv["control"], tv["via"]) == ("media", None, "broadlink:aa")  # nothing to press yet

    signal = client.post("/api/hubs/broadlink:aa/learn").json()["signal"]
    client.post("/api/hubs/broadlink:aa/send", json={"signal": signal})
    assert tx.sent == [b"LEARNED"]
    tv = client.put(f"/api/remote-devices/{tv['uid']}/buttons/power", json={"signal": signal}).json()
    assert tv["control"] == "remote"

    body = client.post(f"/api/devices/{tv['uid']}/state", json={"on": True}).json()
    assert body["state"]["on"] is None  # Power Toggle: never claims on/off
    assert [b["name"] for b in body["features"]["buttons"]] == ["power"]
    assert client.post(f"/api/devices/{tv['uid']}/state", json={"press": "mute"}).status_code == 422
    assert tx.sent == [b"LEARNED", b"LEARNED"]


def test_fan_goes_under_climate(client):
    fan = client.post("/api/remote-devices/buttons", json={"name": "Fan", "kind": "fan"}).json()
    assert fan["category"] == "climate"


def test_try_library_button_prefers_tv_off(client, monkeypatch):
    tx = FakeTransmitter()
    monkeypatch.setattr(api, "connect_transmitter", lambda r, uid: (None, tx))
    tv_set = {"commands": {"on": "T04=", "off": "T0ZG", "mute": "TVU="}}
    monkeypatch.setattr(api.signal_library, "load", lambda domain, code: tv_set)
    body = client.post("/api/signal-library/try-button", json={"domain": "media_player", "code_set": 1}).json()
    assert (body["button"], body["label"]) == ("power_off", "Off") and tx.sent == [b"OFF"]
