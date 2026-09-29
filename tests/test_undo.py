"""Putting a Device back (ADR 0017): an Action's "undo" after some minutes, or while the Only if holds."""

import datetime as dt
import time
from contextlib import closing

from control.engine.registry import Registry

from .test_api import client  # noqa: F401 (a fixture)
from .test_automations import create, runner  # noqa: F401 (a fixture)
from .test_groups import home  # noqa: F401 (a fixture)

LIGHT = "yeelight:1"


def on(undo=None, **body):
    action = {"do": "set", "target": LIGHT, "state": {"on": True}} | ({"undo": undo} if undo else {})
    return create(body.pop("c"), name=body.pop("name", "Porch"), triggers=[], actions=[action], **body)


def run(c, runner, a):  # noqa: F811
    assert c.post(f"/api/automations/{a['uid']}/run").status_code == 202
    runner.join(a["uid"])
    return c.get(f"/api/automations/{a['uid']}/runs").json()[0]


def look(runner, ahead):  # noqa: F811
    with closing(Registry()) as r:
        runner.undo_check(r, time.time() + ahead)


def step(c, a):
    return c.get(f"/api/automations/{a['uid']}/runs").json()[0]["steps"][0]


def test_only_a_toggle_set_or_step_on_one_device_can_be_put_back(home):  # noqa: F811
    c = home["client"]
    a = on({"after": 10}, c=c)
    assert a["actions"][0]["label"].endswith(", then put it back after 10 min")
    for bad, why in (
        ({"do": "notify", "text": "Hi", "undo": {"after": 5}}, "not a notify"),
        ({"do": "set", "target": LIGHT, "state": {"on": True}, "undo": {"after": 0}}, "1 up to 24 hours"),
        ({"do": "set", "target": LIGHT, "state": {"on": True}, "undo": {"after": 5, "while": True}}, '"after"'),
    ):
        body = {"name": "x", "actions": [bad]}
        resp = c.post("/api/automations", json=body)
        assert resp.status_code == 422 and why in resp.json()["detail"], resp.text
    body = {"name": "x", "actions": [{"do": "set", "target": LIGHT, "state": {"on": True}, "undo": {"while": True}}]}
    assert "if there is an Only if" in c.post("/api/automations", json=body).json()["detail"]
    body["conditions"] = [{"type": "days", "days": [0, 1, 2, 3, 4, 5, 6]}]
    assert c.post("/api/automations", json=body).status_code == 201


def test_a_device_is_put_back_after_its_minutes(home, runner):  # noqa: F811
    c, light = home["client"], home["lights"][LIGHT]
    a = on({"after": 10}, c=c)
    run(c, runner, a)
    assert light.state.on is True and step(c, a)["undo"] == "Will be put back after 10 min"
    look(runner, 300)
    assert light.state.on is True  # not yet
    look(runner, 601)
    assert light.state.on is False and step(c, a)["undo"] == "Put back to how it was"
    look(runner, 1200)  # only once
    assert light.calls.count("off") == 1


def test_a_device_someone_changed_meanwhile_is_left_alone(home, runner):  # noqa: F811
    c, light = home["client"], home["lights"][LIGHT]
    a = on({"after": 10}, c=c)
    run(c, runner, a)
    light.state.brightness = 90  # someone dimmed it, or turned it off, from the app
    look(runner, 601)
    assert light.state.on is True and "off" not in light.calls
    assert step(c, a)["undo"] == "Left as it is: it had been changed since"


def test_nothing_is_put_back_that_was_already_so(home, runner):  # noqa: F811
    c, light = home["client"], home["lights"][LIGHT]
    light.state.on = True
    a = on({"after": 10}, c=c)
    run(c, runner, a)
    assert step(c, a)["undo"] == "Nothing to put back: it was already like that"
    look(runner, 601)
    assert "off" not in light.calls


def test_a_device_is_put_back_once_the_only_if_stops_holding(home, runner):  # noqa: F811
    c, light = home["client"], home["lights"][LIGHT]
    today = dt.date.today().weekday()
    a = on({"while": True}, c=c, conditions=[{"type": "days", "days": [today]}])
    run(c, runner, a)
    assert step(c, a)["undo"] == "Will be put back when the Only if stops holding"
    look(runner, 0)
    assert light.state.on is True
    c.patch(f"/api/automations/{a['uid']}", json={"conditions": [{"type": "days", "days": [(today + 1) % 7]}]})
    look(runner, 5)  # looked at a moment ago: not again yet
    assert light.state.on is True
    look(runner, 90)
    assert light.state.on is False and step(c, a)["undo"] == "Put back to how it was"


def test_deleting_the_automation_forgets_what_it_would_put_back(home, runner):  # noqa: F811
    c = home["client"]
    a = on({"after": 10}, c=c)
    run(c, runner, a)
    with closing(Registry()) as r:
        assert len(r.undos()) == 1
    assert c.delete(f"/api/automations/{a['uid']}").status_code == 204
    with closing(Registry()) as r:
        assert r.undos() == []


def test_removing_the_only_if_ends_what_waited_on_it(home, runner):  # noqa: F811
    c, light = home["client"], home["lights"][LIGHT]
    a = on({"while": True}, c=c, conditions=[{"type": "days", "days": [dt.date.today().weekday()]}])
    run(c, runner, a)
    assert c.patch(f"/api/automations/{a['uid']}", json={"conditions": [], "actions": [
        {"do": "set", "target": LIGHT, "state": {"on": True}}]}).status_code == 200
    with closing(Registry()) as r:
        assert r.undos() == []
    assert step(c, a)["undo"].startswith("Left as it is: the Only if")
    look(runner, 300)
    assert light.state.on is True
