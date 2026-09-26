import pytest

from control.api import app as api
from control.engine import connect, groups
from control.engine.errors import DeviceUnreachable
from control.engine.found_device import Category, FoundDevice, Readiness
from control.engine.light import LightFeatures, LightState
from control.engine.plug import PlugState
from control.engine.registry import Registry

from .test_api import FakeLight, client  # noqa: F401 (client is a fixture)
from .test_climate import FakeTransmitter

TOGGLE_TV = {"format": "buttons", "kind": "tv", "buttons": {"power": "AAAA"}}
ON_OFF_FAN = {"format": "buttons", "kind": "fan", "buttons": {"power_on": "AAAA", "power_off": "AAAB"}}


def light(on=False, color=True, lo=1700, hi=6500, **state):
    return {
        "control": "light",
        "features": {"color": color, "color_temp": bool(hi), "min_kelvin": lo, "max_kelvin": hi},
        "state": {"on": on, "brightness": 50, "mode": "white", "rgb": None, "kelvin": 4000} | state,
    }


def ac(on=False, modes=("cool", "heat"), fans=("low", "high"), lo=16, hi=30, **state):
    return {
        "control": "climate",
        "features": {"modes": list(modes), "fan_modes": list(fans), "swing_modes": [], "min_temp": lo,
                     "max_temp": hi, "step": 1},
        "state": {"on": on, "mode": "cool", "target_temp": 24, "fan": "low", "swing": None} | state,
        "assumed": True,
    }


# --- What a Group offers -------------------------------------------------------------


def test_control_is_light_or_climate_only_when_every_member_is_one():
    assert groups.control_of(["light", "light"]) == "light"
    assert groups.control_of(["climate"]) == "climate"
    assert groups.control_of(["light", "plug"]) == "power"
    assert groups.control_of(["remote", "climate"]) == "power"


def test_a_light_group_offers_only_what_every_light_has():
    merged = groups.merge("light", [light(lo=1700, hi=6500), light(color=False, lo=2700, hi=5000)])
    assert merged["features"] == {"color": False, "color_temp": True, "min_kelvin": 2700, "max_kelvin": 5000}
    # A light with no adjustable white takes it away from the whole Group.
    merged = groups.merge("light", [light(), light(lo=0, hi=0)])
    assert merged["features"]["color_temp"] is False


def test_on_while_any_member_is_on_and_the_first_one_on_leads():
    merged = groups.merge("light", [light(brightness=10), light(on=True, brightness=80, mode="color", rgb=(255, 0, 0))])
    assert merged["state"]["on"] is True
    assert (merged["state"]["brightness"], merged["state"]["rgb"]) == (80, (255, 0, 0))
    assert groups.merge("light", [light(), light()])["state"]["on"] is False


def test_an_ac_group_shares_modes_fans_and_temperatures():
    merged = groups.merge("climate", [ac(), ac(modes=("heat", "cool", "dry"), fans=(), lo=18, hi=28)])
    f = merged["features"]
    assert f["modes"] == ["cool", "heat"]
    assert f["fan_modes"] == ["low", "high"]  # an AC without fan speeds ignores them
    assert (f["min_temp"], f["max_temp"]) == (18, 28)
    assert merged["assumed"] is True


def test_acs_with_nothing_in_common_are_on_off_only():
    merged = groups.merge("climate", [ac(modes=("cool",)), ac(modes=("heat",), on=True)])
    assert merged == {"control": "power", "features": {}, "state": {"on": True}, "assumed": True}


def test_a_power_toggle_cant_join():
    assert groups.power_problem("remote", TOGGLE_TV["buttons"]).startswith("only has a Power Toggle")
    assert groups.power_problem("remote", {"mute": "x"}) == "has no On and Off buttons"
    assert groups.power_problem("remote", ON_OFF_FAN["buttons"]) is None
    assert groups.power_problem("plug") is None
    assert groups.power_problem(None) == "can't be controlled yet"


# --- Remembered ----------------------------------------------------------------------


def test_registry_keeps_groups_and_forgetting_a_device_leaves_them(tmp_path):
    r = Registry(tmp_path / "t.db")
    uid = r.add_group("Lights", ["a", "b", "a"])
    assert r.get_group(uid).members == ["a", "b"]
    with pytest.raises(ValueError, match="already exists"):
        r.add_group("lights", ["c"])
    r.update_group(uid, name="All lights", members=["b", "c"])
    assert (r.get_group(uid).name, r.get_group(uid).members) == ("All lights", ["b", "c"])
    r.forget("b")
    assert r.get_group(uid).members == ["c"]
    r.forget_remote("c")  # the last member: the Group goes too
    assert r.groups() == []
    r.close()


# --- Through the API -----------------------------------------------------------------


class FakePlug:
    def __init__(self, on=False, fail=False):
        self.on, self.fail = on, fail

    def get_state(self):
        if self.fail:
            raise DeviceUnreachable("no answer")
        return PlugState(on=self.on)

    def turn_on(self):
        self.on = True

    def turn_off(self):
        self.on = False


@pytest.fixture
def home(client, monkeypatch):  # noqa: F811
    """Two lights, a linked plug, the AC, a TV with only a Power Toggle and a fan with On and Off."""
    r = Registry()
    r.merge_scan([
        FoundDevice("Yeelight", "10.0.0.2", "yeelight:1", Category.LIGHT, Readiness.READY, model="color"),
        FoundDevice("Yeelight", "10.0.0.5", "yeelight:2", Category.LIGHT, Readiness.READY, model="strip"),
        FoundDevice("Tuya", "10.0.0.3", "tuya:abc", Category.UNKNOWN, Readiness.NEEDS_LINK),
        FoundDevice("Broadlink", "10.0.0.4", "broadlink:aa", Category.TRANSMITTER, Readiness.READY,
                    mac="aa", raw={"devtype": 1}),
    ])
    r.save_link("tuya:abc", "Outlet", Category.PLUG, {"local_key": "k"})
    tv = r.add_remote("TV", Category.MEDIA, "broadlink:aa", "learned", TOGGLE_TV)
    fan = r.add_remote("Fan", Category.CLIMATE, "broadlink:aa", "learned", ON_OFF_FAN)
    ac_uid = r.resolve_remote("AC").uid
    r.close()
    lights = {"yeelight:1": FakeLight(), "yeelight:2": FakeLight()}
    lights["yeelight:2"].features = LightFeatures(color=False, color_temp=True, min_kelvin=2700, max_kelvin=6500)
    plug, tx = FakePlug(), FakeTransmitter()
    monkeypatch.setattr(api, "connect_light", lambda r, uid: (None, lights[uid]))
    monkeypatch.setattr(api, "connect_plug", lambda r, uid: (None, plug))
    monkeypatch.setattr(connect, "connect_transmitter", lambda r, uid: (None, tx))
    return {"client": client, "lights": lights, "plug": plug, "tx": tx, "tv": tv, "fan": fan, "ac": ac_uid}


def make(c, name, *members):
    resp = c.post("/api/groups", json={"name": name, "members": list(members)})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_devices_say_whether_they_can_join_a_group(home):
    devices = {d["uid"]: d for d in home["client"].get("/api/devices").json()}
    assert devices["yeelight:1"]["group_problem"] is None
    assert devices[home["fan"]]["group_problem"] is None
    assert "Power Toggle" in devices[home["tv"]]["group_problem"]


def test_a_light_group_turns_every_light_on_and_merges_them(home):
    c, lights = home["client"], home["lights"]
    g = make(c, "Living room", "yeelight:1", "yeelight:2")
    assert (g["control"], g["category"], g["made_by"]) == ("light", "light", "user")

    body = c.post(f"/api/groups/{g['uid']}/state", json={"brightness": 30}).json()
    assert all(l.calls == ["on", ("brightness", 30)] for l in lights.values())
    assert body["state"]["on"] and body["state"]["brightness"] == 30
    assert body["features"]["color"] is False  # the strip has no colour
    assert (body["on_count"], body["total"]) == (2, 2)
    assert set(body["members"]) == {"yeelight:1", "yeelight:2"}  # each member's own reading, for its Tile


def test_a_mixed_group_is_on_off_only(home):
    c, plug = home["client"], home["plug"]
    g = make(c, "Evening", "yeelight:1", "tuya:abc", home["fan"])
    assert (g["control"], g["category"]) == ("power", "mixed")

    body = c.post(f"/api/groups/{g['uid']}/state", json={"on": True}).json()
    assert plug.on and home["lights"]["yeelight:1"].state.on and len(home["tx"].sent) == 1
    assert body["state"] == {"on": True} and body["assumed"] is True  # the fan's power is assumed
    resp = c.post(f"/api/groups/{g['uid']}/state", json={"brightness": 20})
    assert resp.status_code == 422 and "can't all take brightness" in resp.json()["detail"]


def test_an_ac_group(home):
    c = home["client"]
    g = make(c, "ACs", home["ac"])
    body = c.post(f"/api/groups/{g['uid']}/state", json={"target_temp": 25}).json()
    assert body["control"] == "climate" and body["state"]["target_temp"] == 25 and body["assumed"]


def test_a_member_that_doesnt_answer_doesnt_stop_the_others(home):
    c, plug = home["client"], home["plug"]
    g = make(c, "Evening", "yeelight:1", "tuya:abc")
    plug.fail = True
    body = c.get(f"/api/groups/{g['uid']}/state").json()
    assert body["failed"] == {"tuya:abc": {"reason": "Outlet: no answer", "unreachable": True}}
    assert list(body["members"]) == ["yeelight:1"]
    # Nobody answering is the same 503 a single Device gives.
    g = make(c, "Just the plug", "tuya:abc")
    assert c.get(f"/api/groups/{g['uid']}/state").status_code == 503


def test_what_a_group_refuses(home):
    c = home["client"]
    assert c.post("/api/groups", json={"name": "TVs", "members": [home["tv"]]}).status_code == 422
    assert c.post("/api/groups", json={"name": "Hub", "members": ["broadlink:aa"]}).status_code == 422
    assert c.post("/api/groups", json={"name": "Nothing", "members": []}).status_code == 422
    assert c.post("/api/groups", json={"name": "Ghost", "members": ["yeelight:9"]}).status_code == 404
    resp = c.post("/api/groups", json={"name": "outlet", "members": ["yeelight:1"]})
    assert resp.status_code == 422 and "a device is already called" in resp.json()["detail"]
    make(c, "Lights", "yeelight:1")
    assert c.post("/api/groups", json={"name": "LIGHTS", "members": ["yeelight:2"]}).status_code == 422


def test_edit_and_delete(home):
    c = home["client"]
    g = make(c, "Lights", "yeelight:1")
    g = c.patch(f"/api/groups/{g['uid']}", json={"name": "Both lights", "members": ["yeelight:1", "yeelight:2"]}).json()
    assert (g["name"], g["members"]) == ("Both lights", ["yeelight:1", "yeelight:2"])
    assert c.patch(f"/api/groups/{g['uid']}", json={"members": [home["tv"]]}).status_code == 422
    assert c.delete(f"/api/groups/{g['uid']}").status_code == 204
    assert c.get("/api/groups").json() == []
    assert c.get(f"/api/groups/{g['uid']}").status_code == 404


def test_forgetting_a_device_takes_it_out_of_its_groups(home):
    c = home["client"]
    g = make(c, "Lights", "yeelight:1", "yeelight:2")
    c.delete("/api/devices/yeelight:2")
    assert c.get(f"/api/groups/{g['uid']}").json()["members"] == ["yeelight:1"]


def test_made_by_the_assistant(home):
    c = home["client"]
    resp = c.post("/api/groups", json={"name": "Lights", "members": ["yeelight:1"], "by_assistant": True})
    assert resp.json()["made_by"] == "assistant"


def test_light_state_passes_through_unchanged(home):
    # The merged state keeps the light's own fields, so the UI can use the light's controls as is.
    c = home["client"]
    home["lights"]["yeelight:1"].state = LightState(on=True, brightness=70, mode="white", kelvin=3000)
    g = make(c, "Lights", "yeelight:1", "yeelight:2")
    state = c.get(f"/api/groups/{g['uid']}/state").json()["state"]
    assert state == {"on": True, "brightness": 70, "mode": "white", "rgb": None, "kelvin": 3000}

