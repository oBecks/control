import datetime as dt
import re
import time

import pytest

from control.api import automations as automations_api
from control.engine import automations, sun
from control.engine.registry import Registry

from .test_api import client  # noqa: F401 (a fixture)
from .test_groups import home  # noqa: F401 (a fixture)
from .test_groups import make
from .test_hotkeys import add as add_hotkey
from .test_hotkeys import hk  # noqa: F401 (a fixture)

JERUSALEM = sun.Location("Jerusalem, Israel", 31.78, 35.22)


@pytest.fixture(autouse=True)
def israel_time(monkeypatch):
    """Sun times are the PC's local time: as on a PC in Israel in September, whatever this one's zone."""
    monkeypatch.setattr(sun, "_local_zone", lambda day: dt.timezone(dt.timedelta(hours=3)))


def local(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text)


# --- Time ------------------------------------------------------------------------------


def test_a_time_trigger_fires_on_its_days_only():
    t = automations.check_trigger({"type": "time", "at": "7:00", "days": [0, 1, 2, 3, 4]}, None)
    assert t == {"type": "time", "at": "07:00", "days": [0, 1, 2, 3, 4]}
    # 2026-09-25 is a Friday, so the next is Monday's.
    assert automations.next_occurrence(t, local("2026-09-25T08:00"), None) == local("2026-09-28T07:00")
    week = list(automations.occurrences(t, local("2026-09-27T00:00"), local("2026-10-04T00:00"), None))
    assert [d.day for d in week] == [28, 29, 30, 1, 2]


def test_a_trigger_at_the_edge_fires_once():
    t = automations.check_trigger({"type": "time", "at": "07:00"}, None)
    assert list(automations.occurrences(t, local("2026-09-27T06:59"), local("2026-09-27T07:00"), None)) == [
        local("2026-09-27T07:00")]
    assert list(automations.occurrences(t, local("2026-09-27T07:00"), local("2026-09-27T07:01"), None)) == []


def test_sunset_with_an_offset():
    t = automations.check_trigger({"type": "sun", "event": "sunset", "offset": -30}, JERUSALEM)
    at = automations.next_occurrence(t, local("2026-09-27T12:00"), JERUSALEM)
    sunset = sun.event_at(JERUSALEM, dt.date(2026, 9, 27), "sunset")
    assert (sunset.hour, sunset.minute // 10) == (18, 2)  # about 18:29 Israel summer time
    assert at == (sunset - dt.timedelta(minutes=30)).replace(second=0, microsecond=0)


def test_sun_needs_a_location():
    with pytest.raises(ValueError, match="location"):
        automations.check_trigger({"type": "sun", "event": "sunrise"}, None)
    with pytest.raises(ValueError, match="location"):
        automations.check_condition({"type": "sun", "is": "dark"}, None)


@pytest.mark.parametrize("trigger, message", [
    ({"type": "time", "at": "25:00"}, "isn't a time"),
    ({"type": "time", "at": "07:00", "days": []}, "at least one"),
    ({"type": "time", "at": "07:00", "days": [7]}, "weekday numbers"),
    ({"type": "sun", "event": "noon"}, "sunrise or sunset"),
    ({"type": "every", "minutes": 5}, "a Trigger is one of"),
])
def test_triggers_that_arent(trigger, message):
    with pytest.raises(ValueError, match=message):
        automations.check_trigger(trigger, JERUSALEM)


def test_a_time_window_may_cross_midnight():
    night = automations.check_condition({"type": "time", "after": "22:00", "before": "06:00"}, None)
    assert automations.time_condition(night, local("2026-09-27T23:30"), None)
    assert automations.time_condition(night, local("2026-09-27T05:59"), None)
    assert not automations.time_condition(night, local("2026-09-27T06:00"), None)
    day = automations.check_condition({"type": "time", "after": "09:00", "before": "17:00"}, None)
    assert automations.time_condition(day, local("2026-09-27T09:00"), None)
    assert not automations.time_condition(day, local("2026-09-27T17:00"), None)


def test_dark_is_between_sunset_and_sunrise():
    dark = automations.check_condition({"type": "sun", "is": "dark"}, JERUSALEM)
    assert automations.time_condition(dark, local("2026-09-27T23:00"), JERUSALEM)
    assert automations.time_condition(dark, local("2026-09-27T03:00"), JERUSALEM)
    assert not automations.time_condition(dark, local("2026-09-27T12:00"), JERUSALEM)


def test_labels_read_as_sentences():
    assert automations.trigger_label({"type": "time", "at": "07:00", "days": [0, 1, 2, 3, 4]}, {}) == \
        "At 07:00, Monday to Friday"
    assert automations.trigger_label({"type": "sun", "event": "sunset", "offset": -30, "days": list(range(7))}, {}) == \
        "30 min before sunset, every day"
    assert automations.condition_label({"type": "days", "days": [4, 5]}, {}, {}) == "It's Fri, Sat"
    assert automations.wait_label(3900) == "Wait 1 h 5 min"
    assert automations.action_label({"do": "set", "state": {"on": True}}, "Bulb", {}, {}) == "Turn on Bulb"
    assert automations.action_label({"do": "set", "state": {"brightness": 30}}, "Bulb", {}, {}) == \
        "Set Bulb to brightness 30%"
    assert automations.action_label({"do": "step", "field": "target_temp", "by": -1}, "AC", {}, {}) == \
        "AC: temperature down 1°"


# --- Setting up ---------------------------------------------------------------------------


def create(c, **body):
    body = {"name": "Evening", "triggers": [{"type": "time", "at": "19:00"}],
            "actions": [{"do": "set", "target": "yeelight:1", "state": {"on": True}}]} | body
    resp = c.post("/api/automations", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_an_automation_says_what_it_does(home):
    c = home["client"]
    a = create(c, conditions=[{"type": "state", "target": "tuya:abc", "on": False}],
               actions=[{"do": "set", "target": "yeelight:1", "state": {"on": True}},
                        {"do": "wait", "seconds": 600},
                        {"do": "notify", "text": "  Lights on  "}])
    assert a["summary"] == ("When: at 19:00, every day. Only if Outlet is off. "
                            "Then: Turn on Yeelight color, then Wait 10 min, then Notify: Lights on.")
    assert [x["label"] for x in a["actions"]][2] == "Notify: Lights on"
    assert (a["enabled"], a["made_by"], a["running"], a["last_run"]) == (True, "user", False, None)
    assert a["next_run"] is not None
    assert c.get("/api/automations").json()[0]["uid"] == a["uid"]


@pytest.mark.parametrize("body, message", [
    ({"actions": []}, "at least one Action"),
    ({"triggers": [{"type": "time", "at": "7"}]}, "Trigger 1: '7' isn't a time"),
    ({"actions": [{"do": "set", "target": "nope", "state": {"on": True}}]}, "Action 1: there's no Device"),
    ({"actions": [{"do": "wait", "seconds": 0}]}, "Action 1: wait between"),
    ({"conditions": [{"type": "state", "target": "yeelight:1"}]}, "Condition 1: .*on \\(true\\) or off"),
    ({"conditions": [{"type": "app", "target": "yeelight:1", "app": "x"}]}, "only a Streamer"),
    ({"match": "most"}, "all or any"),
    ({"name": " "}, "a name"),
])
def test_what_an_automation_cant_be(home, body, message):
    base = {"name": "Evening", "triggers": [], "actions": [{"do": "toggle", "target": "yeelight:1"}]}
    resp = home["client"].post("/api/automations", json=base | body)
    assert resp.status_code == 422
    assert re.search(message, resp.json()["detail"]), resp.json()["detail"]


def test_a_power_toggle_cant_be_a_condition(home):
    resp = home["client"].post("/api/automations", json={
        "name": "x", "conditions": [{"type": "state", "target": home["tv"], "on": True}],
        "actions": [{"do": "toggle", "target": "yeelight:1"}]})
    assert "Power Toggle" in resp.json()["detail"]


def test_names_are_unique(home):
    create(home["client"])
    assert home["client"].post("/api/automations", json={
        "name": "evening", "actions": [{"do": "toggle", "target": "yeelight:1"}]}).status_code == 422


def test_editing_and_deleting(home):
    c = home["client"]
    a = create(c)
    b = c.patch(f"/api/automations/{a['uid']}", json={"enabled": False, "name": "Night"}).json()
    assert (b["name"], b["enabled"], b["next_run"]) == ("Night", False, None)
    b = c.patch(f"/api/automations/{a['uid']}", json={"triggers": []}).json()
    assert b["summary"].startswith("When: only when run by hand.")
    assert c.patch(f"/api/automations/{a['uid']}", json={"actions": []}).status_code == 422
    assert c.delete(f"/api/automations/{a['uid']}").status_code == 204
    assert c.get(f"/api/automations/{a['uid']}").status_code == 404


def test_forgetting_a_device_removes_only_the_parts_naming_it(home):
    c = home["client"]
    a = create(c, conditions=[{"type": "state", "target": "tuya:abc", "on": False}],
               actions=[{"do": "set", "target": "yeelight:1", "state": {"on": True}},
                        {"do": "toggle", "target": "tuya:abc"}])
    assert c.delete("/api/devices/tuya:abc").status_code == 204
    b = c.get(f"/api/automations/{a['uid']}").json()
    assert (b["conditions"], len(b["actions"]), b["enabled"], b["attention"]) == ([], 1, True, None)
    # Losing its last Action switches it off, and says so.
    assert c.delete("/api/devices/yeelight:1").status_code == 204
    b = c.get(f"/api/automations/{a['uid']}").json()
    assert (b["actions"], b["enabled"]) == ([], False)
    assert "last Action" in b["attention"]


def test_deleting_a_group_takes_its_trigger_and_switches_off(home):
    c = home["client"]
    g = make(c, "Lights", "yeelight:1", "yeelight:2")
    a = create(c, actions=[{"do": "set", "target": g["uid"], "state": {"on": False}},
                           {"do": "notify", "text": "Off"}])
    c.delete(f"/api/groups/{g['uid']}")
    b = c.get(f"/api/automations/{a['uid']}").json()
    assert ([x["do"] for x in b["actions"]], b["enabled"]) == (["notify"], True)


# --- Running ------------------------------------------------------------------------------


@pytest.fixture
def runner(monkeypatch):
    r = automations_api.Runner()
    monkeypatch.setattr(automations_api, "runner", r)
    monkeypatch.setattr(automations_api, "WAIT_CHUNK", 0.01)
    yield r
    r.stop()


def run(c, runner, uid):
    resp = c.post(f"/api/automations/{uid}/run")
    assert resp.status_code == 202, resp.text
    runner.join(uid)
    return c.get(f"/api/automations/{uid}/runs").json()[0]


def test_running_by_hand_skips_the_conditions(home, runner):
    c, light = home["client"], home["lights"]["yeelight:1"]
    a = create(c, conditions=[{"type": "time", "after": "03:00", "before": "03:01"}])
    done = run(c, runner, a["uid"])
    assert (done["cause"], done["outcome"]) == ("Run by hand", "succeeded")
    assert done["steps"] == [{"label": "Turn on Yeelight color", "result": "done"}]
    assert light.state.on


def test_a_failed_action_doesnt_stop_the_others_and_says_so(home, runner, monkeypatch):
    c, light = home["client"], home["lights"]["yeelight:2"]
    from control.api import app as api
    from control.engine.errors import DeviceUnreachable

    def unreachable(r, uid):
        raise DeviceUnreachable("Yeelight strip didn't answer")

    monkeypatch.setattr(api, "connect_plug", unreachable)
    a = create(c, actions=[{"do": "set", "target": "tuya:abc", "state": {"on": True}},
                           {"do": "set", "target": "yeelight:2", "state": {"on": True}}])
    done = run(c, runner, a["uid"])
    assert done["outcome"] == "partly_failed"
    assert [s["result"] for s in done["steps"]] == ["failed", "done"]
    assert light.state.on
    notice = c.get("/api/notices").json()[-1]
    assert notice["title"] == "Evening" and "Turn on Outlet failed" in notice["text"]


def test_a_new_trigger_restarts_a_run_thats_waiting(home, runner):
    c = home["client"]
    a = create(c, actions=[{"do": "wait", "seconds": 600}, {"do": "toggle", "target": "yeelight:1"}])
    c.post(f"/api/automations/{a['uid']}/run")
    assert c.get(f"/api/automations/{a['uid']}").json()["running"]
    c.post(f"/api/automations/{a['uid']}/run")
    time.sleep(0.2)
    first, second = c.get(f"/api/automations/{a['uid']}/runs").json()[::-1]
    assert (first["outcome"], second["outcome"]) == ("restarted", "running")
    assert first["steps"][1]["result"] == "not_run"


def test_sleeping_through_a_wait_interrupts_the_run(home, runner, monkeypatch):
    c, light = home["client"], home["lights"]["yeelight:1"]
    now = [time.time()]
    monkeypatch.setattr(automations_api, "clock", lambda: now[0])
    a = create(c, name="Night AC", actions=[{"do": "wait", "seconds": 60}, {"do": "toggle", "target": "yeelight:1"}])
    c.post(f"/api/automations/{a['uid']}/run")
    time.sleep(0.1)
    now[0] += 2 * 3600  # the PC slept
    runner.join(a["uid"])
    done = c.get(f"/api/automations/{a['uid']}/runs").json()[0]
    assert done["outcome"] == "interrupted"
    assert not light.state.on
    assert c.get("/api/notices").json()[-1]["text"] == "Toggle Yeelight color didn't run"


def test_quitting_mid_run_interrupts_it_and_says_so_next_time(home, runner):
    c = home["client"]
    a = create(c, actions=[{"do": "wait", "seconds": 600}, {"do": "toggle", "target": "yeelight:1"}])
    c.post(f"/api/automations/{a['uid']}/run")
    # Control stopped without a chance to tidy up (the PC turned off): the Run is still "running".
    r = Registry()
    try:
        assert r.runs(a["uid"])[0].outcome == "running"
        automations_api.Runner().recover(r)
        assert r.runs(a["uid"])[0].outcome == "interrupted"
        assert r.notices()[-1].text == "Toggle Yeelight color didn't run"
    finally:
        r.close()


def test_conditions_that_dont_hold_skip_the_run(home, runner):
    c, light = home["client"], home["lights"]["yeelight:1"]
    a = create(c, conditions=[{"type": "state", "target": "yeelight:2", "on": True},
                              {"type": "days", "days": list(range(7))}])
    r = Registry()
    try:
        runner.run(r, a["uid"], "At 19:00, every day")
    finally:
        r.close()
    runner.join(a["uid"])
    done = c.get(f"/api/automations/{a['uid']}/runs").json()[0]
    assert done["outcome"] == "skipped"
    assert done["note"] == "Only if Yeelight strip is on: no"
    assert not light.state.on
    # With "any", the days are enough.
    c.patch(f"/api/automations/{a['uid']}", json={"match": "any"})
    r = Registry()
    try:
        runner.run(r, a["uid"], "At 19:00, every day")
    finally:
        r.close()
    runner.join(a["uid"])
    assert c.get(f"/api/automations/{a['uid']}/runs").json()[0]["outcome"] == "succeeded"


# --- The schedule ----------------------------------------------------------------------------


def test_due_triggers_run_and_late_ones_are_missed(home, runner):
    c = home["client"]
    a = create(c, triggers=[{"type": "time", "at": "07:00"}])
    r = Registry()
    try:
        r._db.execute("UPDATE automations SET armed = 0")  # made long ago
        r._db.commit()
        seven = local("2026-09-28T07:00").timestamp()
        runner.check(r, seven - 30, seven + 10)
        runner.join(a["uid"])
        assert [(x.cause, x.outcome) for x in r.runs(a["uid"])] == [("At 07:00, every day", "succeeded")]
        # Control wasn't running for two days: one missed Run, at the latest time, and nothing done.
        runner.check(r, seven + 10, seven + 2 * 86400 + 3600)
        missed = r.runs(a["uid"])[0]
        assert (missed.outcome, missed.started) == ("missed", seven + 2 * 86400)
        assert not runner.running(a["uid"])
    finally:
        r.close()


def test_a_new_automation_doesnt_count_earlier_times_as_missed(home, runner):
    a = create(home["client"], triggers=[{"type": "time", "at": "00:00"}])
    r = Registry()
    try:
        runner.check(r, time.time() - 5 * 86400, time.time())
        assert r.runs(a["uid"]) == []
    finally:
        r.close()


def test_the_next_due_time_skips_disabled_automations(home, runner):
    c = home["client"]
    a = create(c, triggers=[{"type": "time", "at": "07:00"}])
    r = Registry()
    try:
        assert runner.next_due(r, time.time()) == a["next_run"]
        c.patch(f"/api/automations/{a['uid']}", json={"enabled": False})
        assert runner.next_due(r, time.time()) is None
    finally:
        r.close()


# --- Location and notices ----------------------------------------------------------------------


def test_location_from_a_city_or_coordinates(client):
    assert client.get("/api/location").json() is None
    city = client.get("/api/location/cities", params={"q": "jeru"}).json()[0]
    assert city["name"] == "Jerusalem, Israel"
    where = client.put("/api/location", json=city).json()
    assert where["name"] == "Jerusalem, Israel" and ":" in where["sunset"]
    where = client.put("/api/location", json={"lat": 32.08, "lon": 34.78}).json()
    assert where["name"] == "32.0800, 34.7800"
    assert client.put("/api/location", json={"lat": 91, "lon": 0}).status_code == 422


def test_notices_are_seen_once(client):
    r = Registry()
    try:
        r.add_notice("Night AC", "AC off didn't run")
    finally:
        r.close()
    assert [n["text"] for n in client.get("/api/notices").json()] == ["AC off didn't run"]
    client.post("/api/notices/seen", json={})
    assert client.get("/api/notices").json() == []
    assert len(client.get("/api/notices", params={"unseen": False}).json()) == 1


def test_the_builder_previews_a_draft_without_saving_it(home):
    c = home["client"]
    body = {"triggers": [{"type": "time", "at": "7:5"}], "actions": []}
    assert c.post("/api/automations/preview", json=body).status_code == 422
    body = {"triggers": [{"type": "time", "at": "07:05", "days": [5, 6]}], "actions": []}
    out = c.post("/api/automations/preview", json=body).json()
    assert out["triggers"][0]["label"] == "At 07:05, on Sat, Sun"
    assert out["summary"] == "When: at 07:05, on Sat, Sun. Then: nothing yet."
    assert c.get("/api/automations").json() == []


# --- Run Automation: Hotkeys and Dashboards --------------------------------------------------


def test_a_hotkey_runs_an_automation_skipping_its_conditions(hk, runner):  # noqa: F811
    c, light = hk["client"], hk["lights"]["yeelight:1"]
    a = create(c, conditions=[{"type": "time", "after": "03:00", "before": "03:01"}])
    h = add_hotkey(c, "F13", a["uid"], {"do": "run"})
    assert (h["target_name"], h["action_label"], h["repeats"]) == ("Evening", "Run", False)
    assert c.post(f"/api/hotkeys/{h['uid']}/run").json() == {"name": "Evening", "text": "Running", "level": None}
    runner.join(a["uid"])
    done = c.get(f"/api/automations/{a['uid']}/runs").json()[0]
    assert (done["cause"], done["outcome"]) == ("Hotkey F13", "succeeded")
    assert light.state.on


def test_only_an_automation_runs_and_it_only_runs(hk):  # noqa: F811
    c = hk["client"]
    a = create(c)
    assert "only an Automation runs" in add_hotkey(c, "F13", a["uid"], {"do": "toggle"}, 422)["detail"]
    assert "only an Automation runs" in add_hotkey(c, "F13", "yeelight:1", {"do": "run"}, 422)["detail"]
    assert add_hotkey(c, "F13", "automation:nope", {"do": "run"}, 404)


# --- Chaining: an Action that runs another Automation ------------------------------------------


def test_an_automation_runs_another_skipping_its_conditions(home, runner):
    c, light = home["client"], home["lights"]["yeelight:1"]
    # Switched off too: that only stops its own Triggers.
    a = create(c, enabled=False, conditions=[{"type": "time", "after": "03:00", "before": "03:01"}])
    chain = create(c, name="Chain", actions=[{"do": "run", "target": a["uid"]}, {"do": "notify", "text": "Hi"}])
    assert chain["summary"] == "When: at 19:00, every day. Then: Run Evening, then Notify: Hi."
    done = run(c, runner, chain["uid"])
    assert (done["outcome"], done["steps"][0]) == ("succeeded", {"label": "Run Evening", "result": "done"})
    runner.join(a["uid"])
    other = c.get(f"/api/automations/{a['uid']}/runs").json()[0]
    assert (other["cause"], other["outcome"]) == ("Run by Chain", "succeeded")
    assert light.state.on


@pytest.mark.parametrize("action, message", [
    ({"do": "run", "target": "yeelight:1"}, "only an Automation runs"),
    ({"do": "run", "target": "automation:nope"}, "no Automation"),
    ({"do": "run"}, "say which"),
])
def test_what_a_run_action_cant_be(home, action, message):
    resp = home["client"].post("/api/automations", json={"name": "Chain", "actions": [action]})
    assert resp.status_code == 422 and message in resp.json()["detail"]


def test_an_automation_cant_be_toggled(home):
    a = create(home["client"])
    resp = home["client"].post("/api/automations", json={
        "name": "Chain", "actions": [{"do": "toggle", "target": a["uid"]}]})
    assert resp.status_code == 422 and "no Device or Group" in resp.json()["detail"]


def test_automations_cant_run_each_other_in_a_loop(home):
    c = home["client"]
    a = create(c)
    b = create(c, name="B", actions=[{"do": "run", "target": a["uid"]}])
    d = create(c, name="D", actions=[{"do": "notify", "text": "x"}, {"do": "run", "target": b["uid"]}])
    itself = c.patch(f"/api/automations/{a['uid']}", json={"actions": [{"do": "run", "target": a["uid"]}]})
    assert itself.status_code == 422 and itself.json()["detail"] == "Action 1: an Automation can't run itself"
    loop = c.patch(f"/api/automations/{a['uid']}", json={"actions": [{"do": "run", "target": d["uid"]}]})
    assert loop.json()["detail"] == "Action 1: D → B runs this one again, so they'd run each other in a loop"
    # The builder hears it as soon as the Action is kept.
    preview = c.post("/api/automations/preview", json={"uid": a["uid"], "actions": [{"do": "run", "target": b["uid"]}]})
    assert "B runs this one again" in preview.json()["detail"]
    # A new one can't be in a loop yet: nothing runs it.
    assert c.post("/api/automations/preview", json={"actions": [{"do": "run", "target": b["uid"]}]}).status_code == 200


def test_deleting_an_automation_removes_the_actions_that_ran_it(home):
    c = home["client"]
    a, b = create(c), create(c, name="Morning")
    both = create(c, name="Both", actions=[{"do": "run", "target": a["uid"]}, {"do": "run", "target": b["uid"]}])
    c.delete(f"/api/automations/{a['uid']}")
    after = c.get(f"/api/automations/{both['uid']}").json()
    assert ([x["label"] for x in after["actions"]], after["enabled"]) == (["Run Morning"], True)
    c.delete(f"/api/automations/{b['uid']}")
    after = c.get(f"/api/automations/{both['uid']}").json()
    assert (after["actions"], after["enabled"]) == ([], False)
    assert "Automation that was removed" in after["attention"]


def test_a_chain_of_run_actions_stops(home, runner, monkeypatch):
    from control.api import listening as listening_api

    monkeypatch.setattr(listening_api, "MAX_HOPS", 1)
    c = home["client"]
    last = create(c, name="C", triggers=[])
    middle = create(c, name="B", triggers=[], actions=[{"do": "run", "target": last["uid"]}])
    first = create(c, name="A", actions=[{"do": "run", "target": middle["uid"]}])
    assert run(c, runner, first["uid"])["outcome"] == "succeeded"
    runner.join(middle["uid"])
    b = c.get(f"/api/automations/{middle['uid']}/runs").json()[0]
    assert (b["outcome"], b["steps"][0]["result"]) == ("partly_failed", "failed")
    stopped = c.get(f"/api/automations/{last['uid']}/runs").json()[0]
    assert (stopped["outcome"], stopped["cause"]) == ("skipped", "Run by B")
    assert "set each other off" in stopped["note"]


def test_deleting_an_automation_deletes_its_hotkeys_and_run_buttons(hk):  # noqa: F811
    c = hk["client"]
    a, b = create(c), create(c, name="Morning")
    add_hotkey(c, "F13", a["uid"], {"do": "run"})
    add_hotkey(c, "F14", b["uid"], {"do": "run"})
    items = [{"kind": "run", "target": a["uid"], "x": 0, "y": 0},
             {"kind": "run", "target": b["uid"], "x": 2, "y": 0, "w": 4, "h": 1}]
    d = c.post("/api/dashboards", json={"name": "A", "items": items}).json()
    assert [(i["w"], i["h"]) for i in d["items"]] == [(2, 2), (4, 1)]

    c.delete(f"/api/automations/{a['uid']}")
    assert [h["keys"] for h in c.get("/api/hotkeys").json()["hotkeys"]] == ["F14"]
    assert [i["target"] for i in c.get(f"/api/dashboards/{d['uid']}").json()["items"]] == [b["uid"]]
    # Forgetting a Device keeps Run Buttons: they point at an Automation, not a Device.
    c.delete("/api/devices/yeelight:2")
    assert len(c.get(f"/api/dashboards/{d['uid']}").json()["items"]) == 1


def test_a_run_button_points_at_an_automation_and_a_tile_doesnt(home):
    c = home["client"]
    a = create(c)
    for item in ({"kind": "run", "target": "yeelight:1", "x": 0, "y": 0},
                 {"kind": "tile", "target": a["uid"], "x": 0, "y": 0}):
        assert c.post("/api/dashboards", json={"name": "A", "items": [item]}).status_code == 404
