import threading
import time

import pytest

from control.api import app as api
from control.api import hotkeys as hotkeys_api
from control.desktop import hotkeys as desktop_hotkeys
from control.engine import hotkeys
from control.engine.registry import Registry

from .test_access import approve, phone, turn_on
from .test_api import client  # noqa: F401 (a fixture)
from .test_groups import home  # noqa: F401 (a fixture)
from .test_groups import make

# --- Keys ----------------------------------------------------------------------------


def test_keys_are_written_one_way_whatever_way_they_come_in():
    assert hotkeys.parse("ctrl + alt + KeyL").label == "Ctrl+Alt+L"
    assert hotkeys.parse("Alt+Ctrl+l").label == "Ctrl+Alt+L"  # modifiers in a fixed order
    assert hotkeys.parse("F13").label == "F13"
    assert hotkeys.parse("AudioVolumeUp").label == "Volume Up"
    assert hotkeys.parse("win+shift+Num Plus").label == "Shift+Win+Num Plus"
    keys = hotkeys.parse("Ctrl+Alt+L")
    assert (keys.key.vk, keys.mod_flags) == (0x4C, 0x0003)
    assert hotkeys.parse("F24").key.vk == 0x87 and hotkeys.parse("F1").key.vk == 0x70


@pytest.mark.parametrize("text, message", [
    ("", "isn't a key"),
    ("Ctrl+Alt", "add a key after"),
    ("Hyper+L", "isn't Ctrl, Alt, Shift or Win"),
    ("Ctrl+Nope", "doesn't know the key"),
    ("Ctrl++", "isn't a key"),
])
def test_keys_that_arent_keys(text, message):
    with pytest.raises(ValueError, match=message):
        hotkeys.parse(text)


def test_typing_keys_need_ctrl_alt_or_win():
    assert "used for typing" in hotkeys.problem(hotkeys.parse("L"))
    assert "used for typing" in hotkeys.problem(hotkeys.parse("Shift+L"))
    assert hotkeys.problem(hotkeys.parse("Ctrl+L")) is None
    assert hotkeys.problem(hotkeys.parse("F13")) is None
    assert hotkeys.problem(hotkeys.parse("Play/Pause")) is None


def test_a_media_key_alone_warns_it_stops_working_elsewhere():
    assert "only for Control" in hotkeys.warning(hotkeys.parse("Volume Up"))
    assert hotkeys.warning(hotkeys.parse("F13")) is None
    assert hotkeys.warning(hotkeys.parse("Ctrl+Volume Up")) is None


# --- Actions -------------------------------------------------------------------------

LIGHT = {"on", "brightness", "rgb", "kelvin"}


def test_actions_are_checked_against_what_the_target_can_do():
    check = hotkeys.check_action
    assert check({"do": "toggle"}, "light", LIGHT, {}, [], False) == {"do": "toggle"}
    assert check({"do": "step", "field": "brightness"}, "light", LIGHT, {}, [], False)["by"] == 10
    with pytest.raises(ValueError, match="small amount"):
        check({"do": "step", "field": "brightness", "by": 0.4}, "light", LIGHT, {}, [], False)
    with pytest.raises(ValueError, match="only an AC steps its temperature"):
        check({"do": "step", "field": "target_temp", "by": 1}, "light", LIGHT, {}, [], False)
    with pytest.raises(ValueError, match="can't be set: mode"):
        check({"do": "set", "state": {"mode": "cool"}}, "light", LIGHT, {}, [], False)
    with pytest.raises(ValueError, match="no 'mute' button"):
        check({"do": "press", "button": "mute"}, "remote", set(), {"power": "Power"}, [], False)
    with pytest.raises(ValueError, match="Group has no buttons"):
        check({"do": "press", "button": "power"}, "power", {"on"}, {}, [], True)
    with pytest.raises(ValueError, match="only a Streamer"):
        check({"do": "open_app", "app": "x"}, "light", LIGHT, {}, [], False)
    # A Power Toggle can be toggled: that's pressing it.
    assert check({"do": "toggle"}, "remote", set(), {"power": "Power"}, [], False) == {"do": "toggle"}


def test_actions_say_what_they_do():
    d = hotkeys.describe
    assert d({"do": "toggle"}, {}, {}) == "Toggle"
    assert d({"do": "set", "state": {"on": False}}, {}, {}) == "Turn off"
    assert d({"do": "set", "state": {"brightness": 30}}, {}, {}) == "Set brightness 30%"
    assert d({"do": "step", "field": "brightness", "by": -10}, {}, {}) == "Brightness down 10%"
    assert d({"do": "step", "field": "target_temp", "by": 1}, {}, {}) == "Temperature up 1°"
    assert d({"do": "press", "button": "volume_up"}, {"volume_up": "Volume +"}, {}) == "Press Volume +"
    assert d({"do": "open_app", "app": "com.netflix.ninja"}, {}, {"com.netflix.ninja": "Netflix"}) == "Open Netflix"


# --- Remembered ----------------------------------------------------------------------


def test_forgetting_a_target_deletes_its_hotkeys(tmp_path):
    r = Registry(tmp_path / "t.db")
    r.add_hotkey("Ctrl+Alt+L", "yeelight:1", {"do": "toggle"})
    r.add_hotkey("F13", "remote:tv", {"do": "toggle"})
    group = r.add_group("Lights", ["yeelight:2"])
    r.add_hotkey("F14", group, {"do": "toggle"})
    with pytest.raises(ValueError, match="already uses"):
        r.add_hotkey("ctrl+alt+l", "yeelight:2", {"do": "toggle"})
    r.forget("yeelight:1")
    r.forget_remote("remote:tv")
    assert [h.keys for h in r.hotkeys()] == ["F14"]
    r.forget("yeelight:2")  # the Group's last member: the Group goes, and its Hotkey with it
    assert r.hotkeys() == []
    r.close()


# --- Through the API -----------------------------------------------------------------


@pytest.fixture
def hk(home, monkeypatch):  # noqa: F811
    monkeypatch.setattr(hotkeys_api, "listener", hotkeys_api.Listener())
    monkeypatch.setattr(hotkeys_api, "_levels", {})
    monkeypatch.setattr(desktop_hotkeys, "can_register", lambda keys: True)
    return home


def add(c, keys, target, action, status=201):
    resp = c.post("/api/hotkeys", json={"keys": keys, "target": target, "action": action})
    assert resp.status_code == status, resp.text
    return resp.json()


def run(c, hotkey):
    resp = c.post(f"/api/hotkeys/{hotkey['uid']}/run")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_a_toggle_hotkey(hk):
    c, light = hk["client"], hk["lights"]["yeelight:1"]
    h = add(c, "ctrl+alt+KeyL", "yeelight:1", {"do": "toggle"})
    assert (h["keys"], h["target_name"], h["action_label"], h["repeats"]) == ("Ctrl+Alt+L", "Yeelight color", "Toggle", False)
    assert h["status"] == "off"  # no Desktop App listening
    assert run(c, h) == {"name": "Yeelight color", "text": "Brightness 50%", "level": 0.5}
    assert light.state.on
    assert run(c, h)["text"] == "Off"


def test_the_same_keys_twice_are_refused(hk):
    c = hk["client"]
    add(c, "F13", "yeelight:1", {"do": "toggle"})
    resp = add(c, "f13", "yeelight:2", {"do": "toggle"}, status=422)
    assert "already the Hotkey for Yeelight color (Toggle)" in resp["detail"]
    check = c.post("/api/hotkeys/check", json={"keys": "F13"}).json()
    assert check["problem"].startswith("F13 is already the Hotkey")
    # Editing that Hotkey may keep its own keys.
    uid = c.get("/api/hotkeys").json()["hotkeys"][0]["uid"]
    assert c.post("/api/hotkeys/check", json={"keys": "F13", "uid": uid}).json()["problem"] is None


def test_keys_another_app_has_are_refused(hk, monkeypatch):
    c = hk["client"]
    monkeypatch.setattr(desktop_hotkeys, "can_register", lambda keys: False)
    assert c.post("/api/hotkeys/check", json={"keys": "Ctrl+Alt+Delete"}).json()["problem"] == "Another app uses Ctrl+Alt+Delete"
    assert "used for typing" in c.post("/api/hotkeys/check", json={"keys": "Q"}).json()["problem"]
    assert "only for Control" in c.post("/api/hotkeys/check", json={"keys": "Mute"}).json()["warning"]


def test_an_action_the_target_cant_do_is_refused(hk):
    c = hk["client"]
    assert "can't be set: mode" in add(c, "F13", "yeelight:1", {"do": "set", "state": {"mode": "cool"}}, 422)["detail"]
    assert "brightness" in add(c, "F13", "yeelight:1", {"do": "set", "state": {"brightness": 400}}, 422)["detail"]
    assert "mode must be one of" in add(c, "F13", hk["ac"], {"do": "set", "state": {"mode": "dry"}}, 422)["detail"]
    assert add(c, "F13", "nothing:here", {"do": "toggle"}, 404)


def test_stepping_brightness_reads_the_light_once(hk):
    c, light = hk["client"], hk["lights"]["yeelight:1"]
    light.state.on = True
    reads = []
    get_state = light.get_state
    light.get_state = lambda: reads.append(1) or get_state()
    h = add(c, "Ctrl+Alt+Up", "yeelight:1", {"do": "step", "field": "brightness", "by": 30})
    assert h["repeats"] and h["action_label"] == "Brightness up 30%"
    assert run(c, h) == {"name": "Yeelight color", "text": "Brightness 80%", "level": 0.8}
    assert run(c, h)["text"] == "Brightness 100%"  # no further than full
    assert len(reads) == 1 and light.calls == [("brightness", 80), ("brightness", 100)]


def test_stepping_down_leaves_an_off_light_off_and_up_turns_it_on(hk):
    c, light = hk["client"], hk["lights"]["yeelight:1"]
    down = add(c, "Ctrl+Alt+Down", "yeelight:1", {"do": "step", "field": "brightness", "by": -10})
    assert run(c, down)["text"] == "Off" and light.calls == []
    up = add(c, "Ctrl+Alt+Up", "yeelight:1", {"do": "step", "field": "brightness", "by": 10})
    assert run(c, up)["text"] == "Brightness 10%" and light.calls == ["on", ("brightness", 10)]


def test_stepping_an_acs_temperature(hk):
    c = hk["client"]
    h = add(c, "Ctrl+Alt+PageUp", hk["ac"], {"do": "step", "field": "target_temp", "by": 1})
    out = run(c, h)
    assert out["text"].endswith("°") and out["level"] is not None
    assert len(hk["tx"].sent) == 1


def test_a_power_toggle_is_toggled_by_pressing_it(hk):
    c, tx = hk["client"], hk["tx"]
    h = add(c, "F13", hk["tv"], {"do": "toggle"})
    assert run(c, h)["text"] == "Power pressed" and len(tx.sent) == 1
    press = add(c, "F14", hk["tv"], {"do": "press", "button": "power"})
    assert press["action_label"] == "Press Power" and press["repeats"]
    assert run(c, press)["text"] == "Power" and len(tx.sent) == 2


def test_a_group_hotkey(hk):
    c, lights = hk["client"], hk["lights"]
    g = make(c, "Lights", "yeelight:1", "yeelight:2")
    h = add(c, "Ctrl+Alt+G", g["uid"], {"do": "set", "state": {"brightness": 20}})
    assert h["action_label"] == "Set brightness 20%"
    assert run(c, h)["text"] == "Brightness 20%"
    assert all(l.state.brightness == 20 for l in lights.values())
    assert add(c, "F15", g["uid"], {"do": "press", "button": "power"}, 422)
    # Deleting the Group deletes its Hotkeys.
    c.delete(f"/api/groups/{g['uid']}")
    assert c.get("/api/hotkeys").json()["hotkeys"] == []


def test_a_hotkey_whose_button_was_deleted_says_so(hk):
    c = hk["client"]
    h = add(c, "F13", hk["tv"], {"do": "press", "button": "power"})
    r = Registry()
    r.set_remote_button(hk["tv"], "mute", "AAAB")
    r.set_remote_button(hk["tv"], "power", None)
    r.close()
    resp = c.post(f"/api/hotkeys/{h['uid']}/run")
    assert resp.status_code == 422 and "no 'power' button" in resp.json()["detail"]


def test_edit_and_delete(hk):
    c = hk["client"]
    h = add(c, "F13", "yeelight:1", {"do": "toggle"})
    h = c.patch(f"/api/hotkeys/{h['uid']}", json={"keys": "F14", "action": {"do": "set", "state": {"on": False}}}).json()
    assert (h["keys"], h["action_label"]) == ("F14", "Turn off")
    # A new target must be able to do the action it has.
    resp = c.patch(f"/api/hotkeys/{h['uid']}", json={"target": hk["tv"]})
    assert resp.status_code == 422 and "TV" in resp.json()["detail"]
    assert c.delete(f"/api/hotkeys/{h['uid']}").status_code == 204
    assert c.get("/api/hotkeys").json()["hotkeys"] == []


def test_phones_can_see_but_not_set_up_hotkeys(hk):
    c = hk["client"]
    turn_on(c)
    p = phone()
    approve(c, p)
    body = p.get("/api/hotkeys").json()
    assert body["can_change"] is False
    resp = p.post("/api/hotkeys", json={"keys": "F13", "target": "yeelight:1", "action": {"do": "toggle"}})
    assert resp.status_code == 403
    assert p.get("/api/hotkeys/watch").status_code == 403


# --- The Desktop App's listener, through the API -------------------------------------


def test_the_listener_registers_and_reports_what_windows_refused(hk, monkeypatch):
    c = hk["client"]
    monkeypatch.setattr(hotkeys_api, "WATCH_SECONDS", 0.1)
    first = c.get("/api/hotkeys/watch?revision=0").json()
    assert first["hotkeys"] == [] and not first["recording"]

    # A Hotkey added while the listener watches: the watch answers with it, and the add waits for
    # the listener to say it registered.
    def listener():
        answer = c.get(f"/api/hotkeys/watch?revision={first['revision']}").json()
        taken = [h["uid"] for h in answer["hotkeys"]]
        c.put("/api/hotkeys/registered", json={"revision": answer["revision"], "taken": taken})

    monkeypatch.setattr(hotkeys_api, "WATCH_SECONDS", 5)
    t = threading.Thread(target=listener)
    t.start()
    while not hotkeys_api.listener.watching:
        pass
    h = add(c, "Ctrl+Alt+L", "yeelight:1", {"do": "toggle"})
    t.join()
    assert h["status"] == "taken"
    body = c.get("/api/hotkeys").json()
    assert body["listening"] and body["hotkeys"][0]["status"] == "taken"


def test_while_recording_the_listener_lets_go_of_every_hotkey(hk, monkeypatch):
    c = hk["client"]
    monkeypatch.setattr(hotkeys_api, "WATCH_SECONDS", 0.1)
    add(c, "F13", "yeelight:1", {"do": "toggle"})
    answer = c.get("/api/hotkeys/watch?revision=0").json()
    assert [h["name"] for h in answer["hotkeys"]] == ["Yeelight color"]
    assert c.put("/api/hotkeys/recording", json={"on": True}).status_code == 204
    answer = c.get(f"/api/hotkeys/watch?revision={answer['revision']}").json()
    assert answer["recording"] and answer["hotkeys"] == []
    assert c.get("/api/hotkeys").json()["recording"]
    c.put("/api/hotkeys/recording", json={"on": False})
    answer = c.get(f"/api/hotkeys/watch?revision={answer['revision']}&recording=true").json()
    assert not answer["recording"] and len(answer["hotkeys"]) == 1


def test_a_stopping_engine_answers_the_listener_at_once(hk):
    listener = hotkeys_api.listener
    listener.close()
    started = time.monotonic()
    listener.watch(listener.revision, False, timeout=5)
    assert time.monotonic() - started < 1


def test_forgetting_a_device_tells_the_listener(hk):
    c = hk["client"]
    add(c, "F13", "yeelight:1", {"do": "toggle"})
    revision = hotkeys_api.listener.revision
    c.delete("/api/devices/yeelight:1")
    assert hotkeys_api.listener.revision > revision
    assert c.get("/api/hotkeys").json()["hotkeys"] == []


def test_pickable_keys():
    keys = hotkeys_api.pickable_keys()
    assert {"code": "F13", "label": "F13", "group": "spare", "types": False} in keys



# --- The Desktop App's listener itself -----------------------------------------------


class FakeEngine:
    def __init__(self):
        self.runs = []

    def call(self, method, path, body=None, timeout=30):
        self.runs.append(path)
        return {"name": "Desk lamp", "text": "Brightness 60%", "level": 0.6}


def test_held_keys_repeat_at_most_every_so_often(monkeypatch):
    listener = desktop_hotkeys.HotkeyListener(0)
    listener._engine = FakeEngine()
    shown = []
    listener._show = lambda *args, **kw: shown.append(args)
    listener._pool.submit = lambda fn, *args: fn(*args)  # run right away
    listener._registered = {1: {"uid": "hotkey:a", "repeats": True}, 2: {"uid": "hotkey:b", "repeats": False}}
    clock = [100.0]
    monkeypatch.setattr(desktop_hotkeys.time, "monotonic", lambda: clock[0])

    listener._pressed(1)
    clock[0] += 0.1
    listener._pressed(1)  # Windows repeats the notice while the keys are held: too soon
    clock[0] += desktop_hotkeys.REPEAT_EVERY
    listener._pressed(1)
    listener._pressed(2)
    listener._pressed(3)  # not a Hotkey (any more)
    assert listener._engine.runs == ["/hotkey:a/run", "/hotkey:a/run", "/hotkey:b/run"]
    assert shown[0] == ("Desk lamp", "Brightness 60%", 0.6)


def test_a_press_while_the_last_one_still_runs_is_skipped():
    listener = desktop_hotkeys.HotkeyListener(0)
    submitted = []
    listener._pool.submit = lambda fn, *args: submitted.append(args)
    listener._registered = {1: {"uid": "hotkey:a", "repeats": False}}
    listener._pressed(1)
    listener._pressed(1)
    assert len(submitted) == 1
