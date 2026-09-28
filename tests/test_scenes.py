import pytest

from control.engine import scenes
from control.engine.found_device import Category, FoundDevice, Readiness
from control.engine.registry import Registry

from .test_api import client  # noqa: F401 (client is a fixture)
from .test_groups import home, light, ac  # noqa: F401 (home is a fixture)
from .test_hotkeys import add as add_hotkey
from .test_hotkeys import hk  # noqa: F401 (a fixture)
from .test_hotkeys import run as run_hotkey


# --- What a part may say ---------------------------------------------------------------

LIGHT = {"on", "brightness", "rgb", "kelvin"}


def test_a_part_sets_only_what_its_device_takes():
    assert scenes.check_state({"on": True, "brightness": 20, "rgb": None}, LIGHT) == {"on": True, "brightness": 20}
    assert scenes.check_state({"rgb": (255, 0, 0)}, LIGHT) == {"rgb": [255, 0, 0]}
    for state, allowed, why in [
        ({}, LIGHT, "say what"),
        ({"brightness": 20}, {"on"}, "can't be set"),  # a plug
        ({"on": False, "brightness": 20}, LIGHT, "is off"),
        ({"rgb": [1, 2, 3], "kelvin": 2700}, LIGHT, "not both"),
        ({"press": "power"}, LIGHT, "can't set press"),
    ]:
        with pytest.raises(ValueError, match=why):
            scenes.check_state(state, allowed)
    with pytest.raises(ValueError, match="Power Toggle"):
        scenes.check_state({"on": True}, set())


def test_a_streamer_part_may_open_an_app():
    allowed = scenes.settable("streamer", {"on"})
    assert scenes.check_state({"app": "com.netflix.ninja"}, allowed) == {"app": "com.netflix.ninja"}
    assert scenes.desired({"app": "com.netflix.ninja"}, "https://www.netflix.com/title") == {
        "open_app": "https://www.netflix.com/title"
    }
    assert "app" not in scenes.settable("light", LIGHT)


# --- Active ----------------------------------------------------------------------------


def test_a_part_matches_only_what_it_sets():
    reading = light(on=True, brightness=21, mode="white", kelvin=2710)
    assert scenes.matches({"on": True}, reading)
    assert scenes.matches({"brightness": 20, "kelvin": 2700}, reading)  # a little slack for rounding
    assert not scenes.matches({"brightness": 40}, reading)
    assert not scenes.matches({"rgb": [255, 0, 0]}, reading)  # it's white
    assert not scenes.matches({"on": False}, reading)
    assert scenes.matches({"on": False}, light(on=False, brightness=90))  # off: nothing else counts
    assert not scenes.matches({"brightness": 50}, light(on=False, brightness=50))  # setting it turns it on


def test_an_assumed_state_counts_and_unknown_power_never_matches():
    assert scenes.matches({"mode": "cool", "target_temp": 24}, ac(on=True))
    assert not scenes.matches({"target_temp": 25}, ac(on=True))
    toggle = {"control": "remote", "features": {}, "state": {"on": None}, "assumed": True}
    assert not scenes.matches({"on": True}, toggle) and not scenes.matches({"on": False}, toggle)


def test_capture_keeps_what_is_on_now():
    assert scenes.capture(light(on=False), LIGHT) == {"on": False}
    assert scenes.capture(light(on=True, brightness=30, kelvin=3000), LIGHT) == {
        "on": True, "brightness": 30, "kelvin": 3000
    }
    colour = light(on=True, brightness=80, mode="color", rgb=(255, 0, 0), kelvin=None)
    assert scenes.capture(colour, LIGHT) == {"on": True, "brightness": 80, "rgb": [255, 0, 0]}
    assert scenes.capture(ac(on=True), {"on", "mode", "target_temp", "fan", "swing"}) == {
        "on": True, "mode": "cool", "target_temp": 24, "fan": "low"
    }
    box = {"control": "streamer", "features": {}, "state": {"on": True, "app": "com.netflix.ninja"}}
    shortcuts = [{"name": "Netflix", "app": "com.netflix.ninja"}]
    assert scenes.capture(box, {"on", "app"}, shortcuts) == {"on": True, "app": "com.netflix.ninja"}
    assert scenes.capture(box, {"on", "app"}, []) == {"on": True}  # an app it has no shortcut for
    with pytest.raises(ValueError, match="isn't known"):
        scenes.capture({"control": "remote", "features": {}, "state": {"on": None}}, {"on"})


def test_describe():
    assert scenes.describe({"on": False}) == "Off"
    assert scenes.describe({"on": True, "brightness": 20, "kelvin": 2700}) == "On · 20% · 2700 K"
    assert scenes.describe({"mode": "cool", "target_temp": 24}) == "On · Cool · 24°"
    assert scenes.describe({"app": "com.netflix.ninja"}) == "Netflix"


# --- Remembered ------------------------------------------------------------------------


def test_forgetting_a_device_drops_its_part_and_an_empty_scene_needs_attention(tmp_path):
    r = Registry(tmp_path / "t.db")
    r.merge_scan([FoundDevice("Yeelight", f"10.0.0.{i}", uid, Category.LIGHT, Readiness.READY)
                  for i, uid in enumerate("ab")])
    uid = r.add_scene("Movie night", [{"target": "a", "state": {"on": False}}, {"target": "b", "state": {"on": True}}])
    with pytest.raises(ValueError, match="already exists"):
        r.add_scene("movie NIGHT", [])
    r.forget("a")
    assert [p["target"] for p in r.get_scene(uid).parts] == ["b"]
    assert r.get_scene(uid).attention is None
    r.forget("b")
    sc = r.get_scene(uid)
    assert sc.parts == [] and "Nothing is left" in sc.attention
    r.update_scene(uid, name="Movies")
    assert r.get_scene(uid).attention is None  # looked at since
    other = r.add_scene("Night", [])
    r.order_scenes([other])
    assert [s.name for s in r.scenes()] == ["Night", "Movies"]
    r.close()


# --- Through the API -------------------------------------------------------------------


def make(c, name, *parts, **extra):
    resp = c.post("/api/scenes", json={"name": name, "parts": [{"target": t, "state": s} for t, s in parts]} | extra)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_setting_a_scene_sends_every_part_and_it_turns_active(home):
    c, lights, plug = home["client"], home["lights"], home["plug"]
    sc = make(c, "Movie night",
              ("yeelight:1", {"on": True, "brightness": 20, "kelvin": 2700}),
              ("tuya:abc", {"on": False}),
              (home["ac"], {"mode": "cool", "target_temp": 24}),
              (home["fan"], {"on": True}))
    assert [p["label"] for p in sc["parts"]] == ["On · 20% · 2700 K", "Off", "On · Cool · 24°", "On"]
    assert [p["target_name"] for p in sc["parts"]] == ["Yeelight color", "Outlet", "AC", "Fan"]
    assert c.get("/api/scenes/state").json()[sc["uid"]]["active"] is False
    plug.on = True

    body = c.post(f"/api/scenes/{sc['uid']}/set").json()
    assert body["failed"] == []
    assert lights["yeelight:1"].calls == ["on", ("brightness", 20), ("kelvin", 2700)]
    assert plug.on is False and len(home["tx"].sent) == 2  # the AC and the fan, over infrared
    assert set(body["readings"]) == {"yeelight:1", "tuya:abc", home["ac"], home["fan"]}

    lights["yeelight:1"].state.kelvin = 2700  # the fake doesn't keep what it's sent
    state = c.get("/api/scenes/state").json()[sc["uid"]]
    assert state == {"active": True, "parts": [True, True, True, True]}
    lights["yeelight:1"].state.brightness = 90  # changed by hand
    assert c.get("/api/scenes/state").json()[sc["uid"]]["parts"] == [False, True, True, True]


def test_a_part_that_fails_doesnt_stop_the_others(home):
    c, plug = home["client"], home["plug"]
    sc = make(c, "Evening", ("yeelight:1", {"on": True}), ("tuya:abc", {"on": True}))
    plug.fail = True
    body = c.post(f"/api/scenes/{sc['uid']}/set").json()
    assert body["failed"] == [{"target": "tuya:abc", "reason": "Outlet: no answer", "unreachable": True}]
    assert home["lights"]["yeelight:1"].state.on
    assert c.get("/api/scenes/state").json()[sc["uid"]]["active"] is False  # a Device that doesn't answer


def test_a_group_in_a_scene(home):
    c, lights = home["client"], home["lights"]
    g = c.post("/api/groups", json={"name": "Lights", "members": ["yeelight:1", "yeelight:2"]}).json()
    sc = make(c, "Bright", (g["uid"], {"brightness": 100}))
    c.post(f"/api/scenes/{sc['uid']}/set")
    assert all(l.state.brightness == 100 and l.state.on for l in lights.values())
    assert c.get("/api/scenes/state").json()[sc["uid"]]["active"] is True
    lights["yeelight:2"].state.on = False  # every member must match
    assert c.get("/api/scenes/state").json()[sc["uid"]]["active"] is False
    resp = c.post("/api/scenes", json={"name": "Both", "parts": [
        {"target": g["uid"], "state": {"on": True}}, {"target": "yeelight:1", "state": {"on": False}}]})
    assert resp.status_code == 422 and "is also in 'Lights'" in resp.json()["detail"]


def test_what_a_scene_refuses(home):
    c = home["client"]

    def refused(parts, name="Nope"):
        resp = c.post("/api/scenes", json={"name": name, "parts": [{"target": t, "state": s} for t, s in parts]})
        return resp.status_code, resp.json()["detail"]

    assert refused([(home["tv"], {"on": True})])[1].startswith("'TV' has nothing a Scene can set: it needs separate On and Off")
    assert "can't be set: brightness" in refused([("tuya:abc", {"brightness": 20})])[1]
    assert "is off" in refused([("yeelight:1", {"on": False, "brightness": 20})])[1]
    assert "once" in refused([("yeelight:1", {"on": True}), ("yeelight:1", {"on": False})])[1]
    assert refused([])[0] == 422
    assert refused([("yeelight:9", {"on": True})])[0] == 404
    assert refused([("broadlink:aa", {"on": True})])[0] == 422
    assert "mode" in refused([(home["ac"], {"mode": "turbo"})])[1]
    assert refused([("yeelight:1", {"on": True})], name=" ")[0] == 422
    make(c, "Night", ("yeelight:1", {"on": False}))
    assert "already exists" in refused([("yeelight:1", {"on": True})], name="NIGHT")[1]


def test_capture_reads_how_things_are_now(home):
    c, lights = home["client"], home["lights"]
    lights["yeelight:1"].state.on = True
    body = c.post("/api/scenes/capture", json={"targets": ["yeelight:1", "tuya:abc", home["tv"], "yeelight:9"]}).json()
    assert body["parts"] == [
        {"target": "yeelight:1", "state": {"on": True, "brightness": 50, "kelvin": 4000}},
        {"target": "tuya:abc", "state": {"on": False}},
    ]
    assert list(body["failed"]) == [home["tv"], "yeelight:9"]  # an unknown one fails alone too
    assert c.get("/api/scenes").json() == []  # nothing saved


def test_edit_order_delete_and_forgetting(home):
    c = home["client"]
    a = make(c, "A", ("yeelight:1", {"on": True}), by_assistant=True)
    b = make(c, "B", ("yeelight:2", {"on": True}), icon="moon")
    assert (a["made_by"], a["icon"], b["icon"]) == ("assistant", "sparkles", "moon")
    assert c.patch(f"/api/scenes/{a['uid']}", json={"icon": "rocket"}).status_code == 422
    a = c.patch(f"/api/scenes/{a['uid']}", json={"name": "Lamp on", "parts": [
        {"target": "yeelight:1", "state": {"brightness": 5}}]}).json()
    assert (a["name"], a["parts"][0]["label"]) == ("Lamp on", "On · 5%")
    assert c.put("/api/scenes/order", json={"uids": [b["uid"]]}).status_code == 204
    assert [s["name"] for s in c.get("/api/scenes").json()] == ["B", "Lamp on"]

    c.delete("/api/devices/yeelight:2")
    b = c.get(f"/api/scenes/{b['uid']}").json()
    assert b["parts"] == [] and "Nothing is left" in b["attention"]
    assert c.post(f"/api/scenes/{b['uid']}/set").status_code == 422
    assert c.delete(f"/api/scenes/{b['uid']}").status_code == 204
    assert c.get(f"/api/scenes/{b['uid']}").status_code == 404


# --- Set from a Hotkey or a Dashboard Scene Button -------------------------------------


def test_a_hotkey_sets_a_scene(hk):  # noqa: F811
    c, lights, plug = hk["client"], hk["lights"], hk["plug"]
    sc = make(c, "Evening", ("yeelight:1", {"on": True, "brightness": 20}), ("tuya:abc", {"on": True}))
    h = add_hotkey(c, "F13", sc["uid"], {"do": "set_scene"})
    assert (h["target_name"], h["action_label"], h["repeats"]) == ("Evening", "Set", False)
    assert run_hotkey(c, h) == {"name": "Evening", "text": "Set", "level": None}
    assert lights["yeelight:1"].state.brightness == 20 and plug.on
    plug.fail = True
    assert run_hotkey(c, h)["text"] == "Set, but not Outlet"


def test_only_a_scene_is_set_and_its_only_set(hk):  # noqa: F811
    c = hk["client"]
    sc = make(c, "Evening", ("yeelight:1", {"on": True}))
    assert "only a Scene is set" in add_hotkey(c, "F13", sc["uid"], {"do": "toggle"}, 422)["detail"]
    assert "only a Scene is set" in add_hotkey(c, "F13", "yeelight:1", {"do": "set_scene"}, 422)["detail"]
    assert add_hotkey(c, "F13", "scene:nope", {"do": "set_scene"}, 404)


def test_deleting_a_scene_deletes_its_hotkeys_and_scene_buttons(hk):  # noqa: F811
    c = hk["client"]
    a = make(c, "Evening", ("yeelight:1", {"on": True}))
    b = make(c, "Morning", ("yeelight:2", {"on": True}))
    add_hotkey(c, "F13", a["uid"], {"do": "set_scene"})
    add_hotkey(c, "F14", b["uid"], {"do": "set_scene"})
    items = [{"kind": "scene", "target": a["uid"], "x": 0, "y": 0},
             {"kind": "scene", "target": b["uid"], "x": 2, "y": 0, "w": 1, "h": 2}]
    d = c.post("/api/dashboards", json={"name": "A", "items": items}).json()
    assert [(i["w"], i["h"]) for i in d["items"]] == [(2, 2), (1, 2)]

    c.delete(f"/api/scenes/{a['uid']}")
    assert [h["keys"] for h in c.get("/api/hotkeys").json()["hotkeys"]] == ["F14"]
    assert [i["target"] for i in c.get(f"/api/dashboards/{d['uid']}").json()["items"]] == [b["uid"]]
    # Forgetting a Device a Scene holds keeps its Scene Buttons: they point at the Scene.
    c.delete("/api/devices/yeelight:2")
    assert len(c.get(f"/api/dashboards/{d['uid']}").json()["items"]) == 1


def test_a_scene_button_points_at_a_scene_and_a_tile_doesnt(home):
    c = home["client"]
    sc = make(c, "Evening", ("yeelight:1", {"on": True}))
    for item in ({"kind": "scene", "target": "yeelight:1", "x": 0, "y": 0},
                 {"kind": "tile", "target": sc["uid"], "x": 0, "y": 0}):
        assert c.post("/api/dashboards", json={"name": "A", "items": [item]}).status_code == 404
