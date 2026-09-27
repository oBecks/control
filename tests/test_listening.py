"""Device Triggers and listening (ADR 0011): only named Devices are listened to, changes start Runs,
"stays so for N min", Offline after a minute, and the loop guard."""

import re
import time
from contextlib import closing

import pytest

from control.api import app as api
from control.api import automations as automations_api
from control.api import listening as listening_api
from control.engine import automations, connect
from control.engine.found_device import Category, FoundDevice, Readiness
from control.engine.registry import Registry

from .test_api import client  # noqa: F401 (a fixture)
from .test_automations import create, runner  # noqa: F401 (fixtures)
from .test_groups import home  # noqa: F401 (a fixture)
from .test_groups import make

BOX = "androidtv:box"
NETFLIX = "com.netflix.ninja"


class FakeWatch:
    def __init__(self, uid, report):
        self.uid, self.report, self.closed = uid, report, False

    def close(self):
        self.closed = True


@pytest.fixture
def listening(home, runner, monkeypatch):  # noqa: F811
    r = Registry()
    r.merge_scan([FoundDevice("Android TV", "10.0.0.9", BOX, Category.MEDIA, Readiness.NEEDS_LINK)])
    r.save_link(BOX, "Box", Category.MEDIA, {})
    r.set_streamer(BOX, is_tv=False, apps=[{"app": NETFLIX, "name": "Netflix"}])
    r.close()
    watches: dict[str, FakeWatch] = {}

    def watch(r, device, report):
        watches[device.uid] = FakeWatch(device.uid, report)
        return watches[device.uid]

    monkeypatch.setattr(connect, "watch", watch)
    monkeypatch.setattr(listening_api, "MINUTE", 0.2)
    monkeypatch.setattr(listening_api, "OFFLINE_AFTER", 0.1)
    one = listening_api.Listening()
    for module in (listening_api, automations_api, api):
        monkeypatch.setattr(module, "listening", one)
    one.start()
    yield {"listening": one, "watches": watches, "runner": runner} | home
    one.stop()


def seen(listening, uid, state):
    listening["listening"].seen(uid, state)
    listening["listening"].idle()


def runs(c, uid):
    return c.get(f"/api/automations/{uid}/runs").json()


def notify(text="Hi"):
    return [{"do": "notify", "text": text}]


def settle(listening, uid=None, seconds=0.0):
    time.sleep(seconds)
    listening["listening"].idle()
    if uid:
        listening["runner"].join(uid)


# --- Checking and labels --------------------------------------------------------------------


def test_device_triggers_read_as_sentences(listening):
    c = listening["client"]
    g = make(c, "Lights", "yeelight:1", "yeelight:2")
    a = create(c, triggers=[
        {"type": "state", "target": "tuya:abc", "on": True, "minutes": 90},
        {"type": "state", "target": g["uid"], "on": False},
        {"type": "app", "target": BOX, "app": NETFLIX},
        {"type": "offline", "target": "yeelight:1", "offline": True},
        {"type": "offline", "target": "yeelight:1", "offline": False},
    ], actions=notify())
    assert [t["label"] for t in a["triggers"]] == [
        "Outlet turns on and stays on for 1 h 30 min", "Lights turns off", "Box opens Netflix",
        "Yeelight color goes Offline", "Yeelight color comes back online"]
    assert a["next_run"] is None  # no timed Trigger


@pytest.mark.parametrize("trigger, message", [
    ({"type": "state", "target": "yeelight:1"}, "turns on \\(true\\) or off"),
    ({"type": "state", "target": "yeelight:1", "on": True, "minutes": 2000}, "up to 24 hours"),
    ({"type": "state", "target": "yeelight:1", "on": True, "minutes": 0.5}, "whole minutes"),
    ({"type": "app", "target": "yeelight:1", "app": NETFLIX}, "only a Streamer"),
    ({"type": "offline", "target": "yeelight:1"}, "goes Offline \\(true\\)"),
])
def test_device_triggers_that_arent(listening, trigger, message):
    resp = listening["client"].post("/api/automations", json={"name": "x", "triggers": [trigger],
                                                               "actions": notify()})
    assert resp.status_code == 422
    assert re.search(message, resp.json()["detail"]), resp.json()["detail"]


def test_a_power_toggle_or_an_ac_cant_be_listened_to_for_what_it_cant_tell(listening):
    c = listening["client"]
    resp = c.post("/api/automations", json={"name": "x", "actions": notify(),
                                            "triggers": [{"type": "state", "target": listening["tv"], "on": True}]})
    assert "Power Toggle" in resp.json()["detail"]
    resp = c.post("/api/automations", json={"name": "y", "actions": notify(),
                                            "triggers": [{"type": "offline", "target": listening["ac"], "offline": True}]})
    assert "no connection of its own" in resp.json()["detail"]


# --- What's listened to -----------------------------------------------------------------------


def test_only_devices_named_by_enabled_device_triggers_are_listened_to(listening):
    c, one = listening["client"], listening["listening"]
    create(c, name="Timed")  # a timed Trigger listens to nothing
    settle(listening)
    assert one.listened() == set()
    g = make(c, "Lights", "yeelight:1", "yeelight:2")
    a = create(c, name="Lights on", triggers=[{"type": "state", "target": g["uid"], "on": True}], actions=notify())
    settle(listening)
    assert one.listened() == {"yeelight:1", "yeelight:2"}
    c.patch(f"/api/groups/{g['uid']}", json={"members": ["yeelight:1"]})
    settle(listening)
    assert one.listened() == {"yeelight:1"} and listening["watches"]["yeelight:2"].closed
    c.patch(f"/api/automations/{a['uid']}", json={"enabled": False})
    settle(listening)
    assert one.listened() == set() and listening["watches"]["yeelight:1"].closed


# --- Changes start Runs ---------------------------------------------------------------------------


def test_turning_on_starts_a_run_but_the_first_reading_doesnt(listening):
    c = listening["client"]
    a = create(c, triggers=[{"type": "state", "target": "tuya:abc", "on": True}], actions=notify())
    settle(listening)
    seen(listening, "tuya:abc", {"on": True})  # already on when listening started
    assert runs(c, a["uid"]) == []
    seen(listening, "tuya:abc", {"on": False})
    seen(listening, "tuya:abc", {"on": False})  # a heartbeat's answer: nothing changed
    assert runs(c, a["uid"]) == []
    seen(listening, "tuya:abc", {"on": True})
    settle(listening, a["uid"])
    run = runs(c, a["uid"])[0]
    assert (run["cause"], run["outcome"]) == ("Outlet turns on", "succeeded")


def test_stays_on_for_n_minutes(listening):
    c = listening["client"]
    a = create(c, triggers=[{"type": "state", "target": "tuya:abc", "on": True, "minutes": 1}], actions=notify())
    settle(listening)
    seen(listening, "tuya:abc", {"on": False})
    seen(listening, "tuya:abc", {"on": True})
    seen(listening, "tuya:abc", {"on": False})  # off again before the minute (0.2 s here) was up
    settle(listening, seconds=0.3)
    assert runs(c, a["uid"]) == []
    seen(listening, "tuya:abc", {"on": True})
    settle(listening, a["uid"], seconds=0.3)
    assert runs(c, a["uid"])[0]["cause"] == "Outlet turns on and stays on for 1 min"


def test_stays_on_fires_once_until_it_changes(listening):
    c = listening["client"]
    a = create(c, triggers=[{"type": "state", "target": "tuya:abc", "on": True, "minutes": 1}], actions=notify())
    settle(listening)
    seen(listening, "tuya:abc", {"on": False})
    seen(listening, "tuya:abc", {"on": True})
    settle(listening, a["uid"], seconds=0.3)
    assert len(runs(c, a["uid"])) == 1
    create(c, name="Other")  # any change makes listening sync again; the plug is still on
    settle(listening, a["uid"], seconds=0.3)
    assert len(runs(c, a["uid"])) == 1
    seen(listening, "tuya:abc", {"on": False})
    seen(listening, "tuya:abc", {"on": True})
    settle(listening, a["uid"], seconds=0.3)
    assert len(runs(c, a["uid"])) == 2


def test_a_stays_on_count_the_pc_slept_through_starts_again(listening, monkeypatch):
    c = listening["client"]
    monkeypatch.setattr(listening_api, "SLEPT", 0.1)
    asleep = [True]
    real = listening_api.awake
    monkeypatch.setattr(listening_api, "awake", lambda: 0.0 if asleep[0] else real())
    a = create(c, triggers=[{"type": "state", "target": "tuya:abc", "on": True, "minutes": 1}], actions=notify())
    settle(listening)
    seen(listening, "tuya:abc", {"on": False})
    seen(listening, "tuya:abc", {"on": True})
    settle(listening, seconds=0.3)  # the whole count went by "asleep"
    assert runs(c, a["uid"]) == []
    asleep[0] = False
    settle(listening, a["uid"], seconds=0.4)  # counted again from the wake, awake this time
    assert len(runs(c, a["uid"])) == 1


def test_a_scan_that_missed_a_device_that_answers_is_overruled(listening):
    c = listening["client"]
    create(c, triggers=[{"type": "state", "target": "yeelight:1", "on": True},
                        {"type": "state", "target": "yeelight:2", "on": True}], actions=notify())
    settle(listening)
    seen(listening, "yeelight:1", {"on": False})  # yeelight:2 hasn't answered yet
    with closing(Registry()) as r:
        r.mark_offline("yeelight:1")  # as a Scan that missed them would
        r.mark_offline("yeelight:2")
    listening["listening"].sync()
    settle(listening)
    online = {uid: c.get(f"/api/devices/{uid}").json()["online"] for uid in ("yeelight:1", "yeelight:2")}
    assert online == {"yeelight:1": True, "yeelight:2": False}
    from control.engine import scan

    assert listening["listening"].sync in scan.after_scan  # every Scan, wherever it starts


def test_stays_on_counts_from_when_listening_starts(listening):
    c = listening["client"]
    a = create(c, triggers=[{"type": "state", "target": "tuya:abc", "on": True, "minutes": 1}], actions=notify())
    settle(listening)
    seen(listening, "tuya:abc", {"on": True})  # already on: counted from now
    settle(listening, a["uid"], seconds=0.3)
    assert len(runs(c, a["uid"])) == 1


def test_a_group_turns_on_with_its_first_member_and_off_with_its_last(listening):
    c = listening["client"]
    g = make(c, "Lights", "yeelight:1", "yeelight:2")
    on = create(c, name="On", triggers=[{"type": "state", "target": g["uid"], "on": True}], actions=notify())
    off = create(c, name="Off", triggers=[{"type": "state", "target": g["uid"], "on": False}], actions=notify())
    settle(listening)
    seen(listening, "yeelight:1", {"on": False})
    assert runs(c, off["uid"]) == []  # the other member isn't known yet
    seen(listening, "yeelight:2", {"on": False})
    seen(listening, "yeelight:1", {"on": True})
    seen(listening, "yeelight:2", {"on": True})  # already on: no second Run
    seen(listening, "yeelight:1", {"on": False})
    settle(listening, on["uid"])
    assert (len(runs(c, on["uid"])), runs(c, off["uid"])) == (1, [])
    seen(listening, "yeelight:2", {"on": False})
    settle(listening, off["uid"])
    assert runs(c, off["uid"])[0]["cause"] == "Lights turns off"


def test_a_streamer_opening_an_app_but_not_its_screensaver(listening):
    c = listening["client"]
    a = create(c, triggers=[{"type": "app", "target": BOX, "app": NETFLIX}], actions=notify())
    settle(listening)
    seen(listening, BOX, {"on": True, "app": "com.google.android.tvlauncher"})
    seen(listening, BOX, {"on": True, "app": NETFLIX})
    seen(listening, BOX, {"on": True, "app": "com.google.android.backdrop"})  # the screensaver
    seen(listening, BOX, {"on": True, "app": NETFLIX})
    settle(listening, a["uid"])
    assert [r["cause"] for r in runs(c, a["uid"])] == ["Box opens Netflix"]


def test_a_remote_device_changes_when_control_sends_it(listening):
    c = listening["client"]
    a = create(c, triggers=[{"type": "state", "target": listening["fan"], "on": True}], actions=notify())
    settle(listening)
    assert c.post(f"/api/devices/{listening['fan']}/state", json={"on": True}).status_code == 200
    settle(listening, a["uid"])
    assert runs(c, a["uid"])[0]["cause"] == "Fan turns on"


# --- Offline --------------------------------------------------------------------------------------


def test_offline_after_a_minute_without_an_answer_and_back_on_any_answer(listening):
    c = listening["client"]
    gone = create(c, name="Gone", triggers=[{"type": "offline", "target": "yeelight:1", "offline": True}],
                  actions=notify())
    back = create(c, name="Back", triggers=[{"type": "offline", "target": "yeelight:1", "offline": False}],
                  actions=notify())
    settle(listening)
    seen(listening, "yeelight:1", {"on": True})
    seen(listening, "yeelight:1", None)
    seen(listening, "yeelight:1", {"on": True})  # reconnected in time: a Wi-Fi blip
    settle(listening, seconds=0.2)
    assert runs(c, gone["uid"]) == []
    seen(listening, "yeelight:1", None)
    settle(listening, gone["uid"], seconds=0.2)
    assert runs(c, gone["uid"])[0]["cause"] == "Yeelight color goes Offline"
    assert c.get("/api/devices/yeelight:1").json()["online"] is False  # on Home too
    seen(listening, "yeelight:1", {"on": True})
    settle(listening, back["uid"])
    assert runs(c, back["uid"])[0]["cause"] == "Yeelight color comes back online"
    assert c.get("/api/devices/yeelight:1").json()["online"] is True


# --- The loop guard -------------------------------------------------------------------------------


def test_an_automations_own_change_doesnt_trigger_it(listening):
    c = listening["client"]
    a = create(c, triggers=[{"type": "state", "target": "yeelight:1", "on": True}],
               actions=[{"do": "toggle", "target": "yeelight:1"}])
    settle(listening)
    seen(listening, "yeelight:1", {"on": False})
    c.post(f"/api/automations/{a['uid']}/run")  # it turns the light on
    settle(listening, a["uid"])
    seen(listening, "yeelight:1", {"on": True})  # the light reports it
    settle(listening, a["uid"])
    assert len(runs(c, a["uid"])) == 1


def test_one_set_off_too_often_is_switched_off(listening, monkeypatch):
    c = listening["client"]
    monkeypatch.setattr(listening_api, "MINUTE", 60)
    a = create(c, triggers=[{"type": "state", "target": "yeelight:1", "on": True}], actions=notify())
    settle(listening)
    seen(listening, "yeelight:1", {"on": False})
    for _ in range(listening_api.MAX_PER_MINUTE + 1):
        seen(listening, "yeelight:1", {"on": True})
        seen(listening, "yeelight:1", {"on": False})
        settle(listening, a["uid"])
    b = c.get(f"/api/automations/{a['uid']}").json()
    assert (b["enabled"], len(runs(c, a["uid"]))) == (False, listening_api.MAX_PER_MINUTE)
    assert "loop" in b["attention"]
    assert "Switched off" in c.get("/api/notices").json()[-1]["text"]


def test_a_chain_of_automations_stops(listening, monkeypatch):
    c = listening["client"]
    monkeypatch.setattr(listening_api, "MAX_HOPS", 1)
    # A turns on the plug when the light turns on; B turns on the strip when the plug does; C would
    # go on, but it's a hop too many.
    a = create(c, name="A", triggers=[{"type": "state", "target": "yeelight:1", "on": True}],
               actions=[{"do": "set", "target": "tuya:abc", "state": {"on": True}}])
    b = create(c, name="B", triggers=[{"type": "state", "target": "tuya:abc", "on": True}],
               actions=[{"do": "set", "target": "yeelight:2", "state": {"on": True}}])
    chained = create(c, name="C", triggers=[{"type": "state", "target": "yeelight:2", "on": True}],
                     actions=notify())
    settle(listening)
    for uid in ("yeelight:1", "tuya:abc", "yeelight:2"):
        seen(listening, uid, {"on": False})
    seen(listening, "yeelight:1", {"on": True})  # someone turned it on
    settle(listening, a["uid"])
    seen(listening, "tuya:abc", {"on": True})  # A's doing
    settle(listening, b["uid"])
    seen(listening, "yeelight:2", {"on": True})  # B's doing, one hop on
    settle(listening, chained["uid"])
    assert [len(runs(c, x["uid"])) for x in (a, b, chained)] == [1, 1, 1]
    stopped = runs(c, chained["uid"])[0]  # kept in its history, not only in a notice that goes away
    assert (stopped["outcome"], stopped["cause"]) == ("skipped", "Yeelight strip turns on")
    assert "set each other off" in stopped["note"]
    assert "set each other off" in c.get("/api/notices").json()[-1]["text"]


def test_listened_devices_follow_the_automation_parts(listening):
    uid = create(listening["client"], triggers=[{"type": "offline", "target": BOX, "offline": True}],
                 actions=notify())["uid"]
    with closing(Registry()) as r:
        assert automations.listened(r.get_automation(uid)) == {BOX}


def test_a_bulbs_power_from_its_answer_and_notifications():
    from control.engine.adapters.yeelight_light import _power

    assert _power(b'{"id": 1, "result": ["on"]}') == "on"
    assert _power(b'{"method": "props", "params": {"power": "off", "bright": 10}}') == "off"
    assert _power(b'{"method": "props", "params": {"bright": 10}}') is None  # brightness only
    assert _power(b"not json") is None


class FakeRemote:
    """Enough of an Android TV Remote connection for listening."""

    def __init__(self, host, available=True):
        self.host, self.available, self.is_on, self.current_app = host, available, True, NETFLIX
        self.callbacks = []

    def add_is_on_updated_callback(self, cb):
        self.callbacks.append(cb)

    def remove_is_on_updated_callback(self, cb):
        self.callbacks.remove(cb)

    add_current_app_updated_callback = add_is_available_updated_callback = add_is_on_updated_callback
    remove_current_app_updated_callback = remove_is_available_updated_callback = remove_is_on_updated_callback

    def drop(self):
        self.available = False
        for cb in self.callbacks:
            cb(False)


def test_a_streamer_that_moved_is_listened_to_at_its_new_address(monkeypatch):
    import asyncio

    from control.engine.adapters import androidtv_streamer as atv

    monkeypatch.setattr(atv, "RETRY_SECONDS", 0.05)
    address = ["10.0.0.9"]
    tried: list[str] = []
    reports: list = []

    async def connected(uid, ip):
        tried.append(ip)
        remote = FakeRemote(ip)
        atv._remotes[uid] = remote
        atv._attach(uid, remote)
        return remote

    monkeypatch.setattr(atv, "_connected", connected)
    watch = atv.AndroidTVWatch("androidtv:moved", lambda: address[0], lambda uid, s: reports.append(s))
    try:
        deadline = time.monotonic() + 2
        while not tried and time.monotonic() < deadline:
            time.sleep(0.01)
        assert tried == ["10.0.0.9"] and reports[-1] == {"on": True, "app": NETFLIX}
        address[0] = "10.0.0.20"  # a Scan found it here
        atv._loop.call_soon_threadsafe(atv._remotes["androidtv:moved"].drop)
        while len(tried) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert tried == ["10.0.0.9", "10.0.0.20"]
        assert None in reports and reports[-1] == {"on": True, "app": NETFLIX}
    finally:
        remote = atv._remotes["androidtv:moved"]
        watch.close()
        asyncio.run_coroutine_threadsafe(asyncio.sleep(0), atv._loop).result(1)
        atv._remotes.pop("androidtv:moved", None)
    assert remote.callbacks == []  # listening again won't pile them up


def test_a_plugs_heartbeat_answer_or_closing_is_told_apart():
    import socket

    from control.engine.adapters.tuya_plug import TuyaWatch

    class Dev:
        retry = True

        def __init__(self, sock):
            self.socket = sock

        def receive(self):
            assert self.retry is False  # an empty answer is the whole answer: don't wait for more
            self.socket.recv(4096)
            return None

    ours, plug = socket.socketpair()
    dev = Dev(ours)
    assert TuyaWatch._read(dev) is None  # nothing to read: a command read it meanwhile
    plug.send(bytes(28))  # a heartbeat's empty answer
    assert TuyaWatch._read(dev) is None and dev.retry is True
    plug.close()
    assert TuyaWatch._read(dev) is False  # the plug closed the connection
    ours.close()


def test_a_streamer_keeping_an_app_open_for_n_minutes(listening):
    c = listening["client"]
    a = create(c, triggers=[{"type": "app", "target": BOX, "app": NETFLIX, "minutes": 1}], actions=notify())
    assert a["triggers"][0]["label"] == "Box opens Netflix and keeps it open for 1 min"
    settle(listening)
    seen(listening, BOX, {"on": True, "app": "com.google.android.tvlauncher"})
    seen(listening, BOX, {"on": True, "app": NETFLIX})
    seen(listening, BOX, {"on": True, "app": "com.google.android.youtube.tv"})  # left before the minute
    settle(listening, seconds=0.3)
    assert runs(c, a["uid"]) == []
    seen(listening, BOX, {"on": True, "app": NETFLIX})
    seen(listening, BOX, {"on": False, "app": NETFLIX})  # the box went to sleep with it open
    settle(listening, seconds=0.3)
    assert runs(c, a["uid"]) == []
    seen(listening, BOX, {"on": True, "app": NETFLIX})
    seen(listening, BOX, {"on": True, "app": "com.google.android.backdrop"})  # the screensaver: still Netflix
    settle(listening, a["uid"], seconds=0.3)
    assert [r["cause"] for r in runs(c, a["uid"])] == ["Box opens Netflix and keeps it open for 1 min"]


def test_a_command_while_the_plug_is_being_connected_waits_for_that_connection(monkeypatch):
    import socket

    from control.engine.adapters import tuya_plug

    opened = []

    class Dev:
        def __init__(self):
            self.socket, self._plug = socket.socketpair()
            self.address = "10.0.0.3"
            self.retry = True

        def set_socketPersistent(self, _):
            pass

        def status(self):
            time.sleep(0.3)  # the plug takes a moment to answer
            return {"dps": {"1": True}}

        def turn_off(self, switch):
            return {"dps": {"1": False}}

        def heartbeat(self, nowait):
            pass

        def close(self):
            self.socket.close()
            self._plug.close()

    def device(*args):
        opened.append(args)
        return Dev()

    monkeypatch.setattr(tuya_plug, "_device", device)
    reports = []
    watch = tuya_plug.TuyaWatch("tuya:x", "k", "3.3", lambda: "10.0.0.3", lambda uid, s: reports.append(s))
    try:
        plug = tuya_plug.TuyaPlug("x", "10.0.0.3", "k", "3.3")  # while the watch is still connecting
        assert len(opened) == 1  # it waited and used the watch's connection: no second one
        assert plug.get_state().on is True
        plug.turn_off()
        assert watch.on is False and reports[-1] == {"on": False}
    finally:
        watch.close()
