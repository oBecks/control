from contextlib import closing

import pytest

from control.api import access, people
from control.engine import neighbors
from control.engine.neighbors import Neighbor
from control.engine.presence import AWAY_AFTER, Change, Tracker
from control.engine.registry import Registry

from .test_access import ANDROID_CHROME, approve, phone, turn_on
from .test_api import client  # noqa: F401 (a fixture)
from .test_automations import create, runner  # noqa: F401 (fixtures)
from .test_groups import home  # noqa: F401 (a fixture)

MAC = "4a:84:cf:32:5e:d9"
MAC2 = "6e:11:22:33:44:55"


# --- Presence, counted ----------------------------------------------------------------


def tracked(**people):
    t = Tracker()
    t.set_phones(people, 0)
    return t


def test_seen_is_home_at_once_but_the_first_reading_fires_nothing():
    t = tracked(**{"person:a": [MAC]})
    assert t.home("person:a") is None and t.anyone() is None
    assert t.update({MAC}, 30) == []
    assert t.home("person:a") is True and t.anyone() is True


def test_away_only_after_ten_minutes_unseen():
    t = tracked(**{"person:a": [MAC]})
    t.update({MAC}, 30)
    assert t.update(set(), 30 + AWAY_AFTER - 1) == []  # a sleeping phone, a short Wi-Fi drop
    assert t.update(set(), 30 + AWAY_AFTER) == [Change("person:a", False), Change(None, False)]
    assert t.update({MAC}, 30 + AWAY_AFTER + 30) == [Change("person:a", True), Change(None, True)]


def test_never_seen_is_away_after_ten_minutes_without_firing():
    t = tracked(**{"person:a": [MAC]})
    assert t.update(set(), AWAY_AFTER - 1) == [] and t.home("person:a") is None
    assert t.update(set(), AWAY_AFTER) == [] and t.home("person:a") is False  # was unknown: no "leaves"
    assert t.anyone() is False


def test_any_phone_of_theirs_keeps_a_person_home():
    t = tracked(**{"person:a": [MAC, MAC2]})
    t.update({MAC, MAC2}, 0)
    t.update({MAC2}, AWAY_AFTER)  # the phone left on the table, the other one in a pocket
    assert t.home("person:a") is True


def test_first_arrives_and_last_leaves():
    t = tracked(**{"person:a": [MAC], "person:b": [MAC2]})
    t.update({MAC}, 0)
    t.update(set(), AWAY_AFTER)  # b never seen, a gone
    assert t.anyone() is False
    assert t.update({MAC2}, AWAY_AFTER + 30) == [Change("person:b", True), Change(None, True)]
    assert t.update({MAC, MAC2}, AWAY_AFTER + 60) == [Change("person:a", True)]  # not the first
    t.update({MAC2}, 3 * AWAY_AFTER)
    assert t.update(set(), 4 * AWAY_AFTER) == [Change("person:b", False), Change(None, False)]


def test_a_phone_marked_later_starts_unknown():
    t = tracked(**{"person:a": [MAC]})
    t.update(set(), AWAY_AFTER)
    t.set_phones({"person:a": [MAC], "person:b": [MAC2]}, AWAY_AFTER)
    assert t.home("person:b") is None and t.anyone() is None
    assert t.update({MAC2}, AWAY_AFTER + 30) == []  # unknown to home: nothing
    assert t.missing(AWAY_AFTER + 30, 60) == {MAC}


# --- The network ------------------------------------------------------------------------


def test_macs_and_addresses():
    assert neighbors.normal_mac("4A-84-CF-32-5E-D9") == MAC
    with pytest.raises(ValueError):
        neighbors.normal_mac("4a:84:cf")
    assert neighbors.is_private(MAC) and not neighbors.is_private("7c:49:eb:0f:94:e0")
    hosts = neighbors.subnet_hosts(["192.168.1.130"])
    assert len(hosts) == 253 and "192.168.1.130" not in hosts and hosts[0] == "192.168.1.1"


@pytest.fixture
def network(monkeypatch):
    """A fake home network: of `answering` (ip -> mac), what the last look nudged answers (Windows
    only asks for what it sends to), and the router always; nudges are recorded; no waiting."""
    net = {"answering": {"10.0.0.50": MAC}, "nudged": []}
    net["answering"]["10.0.0.254"] = "b0:bb:e5:79:42:27"  # the router

    def table():
        asked = net["nudged"][-1] if net["nudged"] else set()
        return [Neighbor(ip, mac, ip in asked) for ip, mac in net["answering"].items()]

    monkeypatch.setattr(neighbors, "nudge", lambda ips: net["nudged"].append(set(ips)))
    monkeypatch.setattr(neighbors, "table", table)
    monkeypatch.setattr(neighbors, "gateway", lambda own: "10.0.0.254")
    monkeypatch.setattr(neighbors, "SETTLE", 0)
    monkeypatch.setattr(people.time, "sleep", lambda s: None)
    monkeypatch.setattr(people.lan, "lan_ips", lambda: ["10.0.0.1"])
    monkeypatch.setattr(people.socket, "gethostbyaddr", lambda ip: ("iPhone.home", [], [ip]))
    monkeypatch.setattr(people, "presence", people.Presence())
    monkeypatch.setattr(people, "_last_sweep", (0.0, []))
    return net


def add_person(c, name="Dana"):
    resp = c.post("/api/people", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_a_person_and_a_phone_from_the_nearby_list(client, network):  # noqa: F811
    dana = add_person(client)
    assert dana["home"] is None and dana["phones"] == []
    network["answering"] |= {"10.0.0.2": "7c:49:eb:0f:94:e0", "10.0.0.60": "44:85:00:25:a6:e8"}
    nearby = client.get("/api/people/nearby").json()
    # The Yeelight at 10.0.0.2 is a Device, not a phone; private MACs come first.
    assert [(n["ip"], n["private"], n["name"]) for n in nearby] == [
        ("10.0.0.50", True, "iPhone"), ("10.0.0.60", False, "iPhone"), ("10.0.0.254", False, "iPhone")]
    assert len(network["nudged"][0]) == 253  # the whole subnet

    resp = client.post(f"/api/people/{dana['uid']}/phones", json={"mac": MAC.upper(), "ip": "10.0.0.50",
                                                                   "name": "iPhone"})
    assert resp.status_code == 201, resp.text
    assert [(p["mac"], p["name"], p["private"]) for p in resp.json()["phones"]] == [(MAC, "iPhone", True)]
    assert [n["ip"] for n in client.get("/api/people/nearby").json()] == ["10.0.0.60", "10.0.0.254"]  # marked: left out
    assert len(network["nudged"]) == 1  # the second browser got the same sweep's answers

    assert client.delete(f"/api/people/{dana['uid']}/phones/{MAC}").status_code == 204
    assert client.get("/api/people").json()[0]["phones"] == []


def test_a_person_needs_a_name_of_their_own(client, network):  # noqa: F811
    add_person(client)
    assert client.post("/api/people", json={"name": "dana"}).status_code == 422
    assert client.post("/api/people", json={"name": " "}).status_code == 422


def test_this_is_my_phone_only_from_the_phone(client, network):  # noqa: F811
    dana = add_person(client)
    resp = client.post(f"/api/people/{dana['uid']}/phones", json={"this_phone": True})
    assert resp.status_code == 422 and "open Control on the phone" in resp.json()["detail"]

    turn_on(client)
    access._asks.clear()
    p = phone("10.0.0.50", ANDROID_CHROME)
    approve(client, p)
    resp = p.post(f"/api/people/{dana['uid']}/phones", json={"this_phone": True})
    assert resp.status_code == 201, resp.text
    assert [(ph["mac"], ph["name"], ph["current"]) for ph in resp.json()["phones"]] == [(MAC, "Android", True)]
    assert client.get("/api/people").json()[0]["phones"][0]["current"] is False  # the PC isn't that phone

    stranger = phone("10.0.0.77", ANDROID_CHROME)  # on mobile data, say: Windows never saw it
    approve(client, stranger)
    resp = stranger.post(f"/api/people/{dana['uid']}/phones", json={"this_phone": True})
    assert resp.status_code == 422 and "can't see this phone" in resp.json()["detail"]


def test_presence_finds_a_phone_that_moved(client, network, monkeypatch):  # noqa: F811
    monkeypatch.setattr(people, "SWEEP_AFTER", 0)  # missing long enough to look everywhere
    dana = add_person(client)
    client.post(f"/api/people/{dana['uid']}/phones", json={"mac": MAC, "ip": "10.0.0.9"})
    del network["answering"]["10.0.0.50"]
    network["answering"]["10.0.0.51"] = MAC  # a new address from the router
    people.presence.check({MAC: "10.0.0.9"})
    assert people.presence.home(dana["uid"]) is True  # seen: home (from unknown, so nothing fired)
    assert network["nudged"][-1] == {"10.0.0.9"} | set(neighbors.subnet_hosts(["10.0.0.1"]))  # the router among them
    with closing(Registry()) as r:
        assert r.phone(MAC).ip == "10.0.0.51"
    assert client.get("/api/people").json()[0]["phones"][0]["seen"] is not None


# --- Automations --------------------------------------------------------------------------


@pytest.fixture
def dana(home, network):  # noqa: F811
    c = home["client"]
    person = add_person(c)
    c.post(f"/api/people/{person['uid']}/phones", json={"mac": MAC, "ip": "10.0.0.50"})
    return person["uid"]


def notify(text="Hi"):
    return [{"do": "notify", "text": text}]


def test_presence_triggers_and_conditions_read_as_sentences(home, dana):  # noqa: F811
    a = create(home["client"], name="Welcome",
               triggers=[{"type": "person", "target": dana, "home": True}, {"type": "home", "occupied": False}],
               conditions=[{"type": "person", "target": dana, "home": False}, {"type": "home", "occupied": True}],
               match="any", actions=notify())
    assert [t["label"] for t in a["triggers"]] == ["Dana arrives home", "The last person leaves home"]
    assert [c["label"] for c in a["conditions"]] == ["Dana is away", "Someone is home"]
    assert a["summary"] == ("When: Dana arrives home or the last person leaves home. "
                            "Only if Dana is away or someone is home. Then: Notify: Hi.")


def test_presence_needs_people_with_phones(home, network):  # noqa: F811
    c = home["client"]
    body = {"name": "Welcome", "triggers": [{"type": "home", "occupied": True}], "actions": notify()}
    resp = c.post("/api/automations", json=body)
    assert resp.status_code == 422 and "Settings → People" in resp.json()["detail"]
    nobody = add_person(c, "Noa")
    body["triggers"] = [{"type": "person", "target": nobody["uid"], "home": True}]
    resp = c.post("/api/automations", json=body)
    assert resp.status_code == 422 and "mark Noa's phone first" in resp.json()["detail"]
    body["triggers"] = [{"type": "person", "target": "person:nope", "home": True}]
    assert c.post("/api/automations", json=body).status_code == 422
    body["triggers"] = [{"type": "person", "target": nobody["uid"]}]
    assert "home (true) or away" in c.post("/api/automations", json=body).json()["detail"]


def test_arriving_starts_the_automations_it_triggers(home, dana, runner):  # noqa: F811
    c = home["client"]
    arrives = create(c, name="Welcome", triggers=[{"type": "person", "target": dana, "home": True}], actions=notify())
    first = create(c, name="First", triggers=[{"type": "home", "occupied": True}], actions=notify())
    leaves = create(c, name="Bye", triggers=[{"type": "person", "target": dana, "home": False}], actions=notify())
    with closing(Registry()) as r:
        people.started(r, [Change(dana, True), Change(None, True)])
    for uid in (arrives["uid"], first["uid"]):
        runner.join(uid)
        assert c.get(f"/api/automations/{uid}/runs").json()[0]["outcome"] == "succeeded"
    cause = c.get(f"/api/automations/{arrives['uid']}/runs").json()[0]["cause"]
    assert cause == "Dana arrives home"
    assert c.get(f"/api/automations/{leaves['uid']}/runs").json() == []


def test_a_presence_condition_not_known_yet_isnt_met(home, dana, runner, network):  # noqa: F811
    c = home["client"]
    a = create(c, name="Lights", triggers=[], conditions=[{"type": "person", "target": dana, "home": True}],
               actions=notify())
    with closing(Registry()) as r:
        runner.run(r, a["uid"], "test")
    runner.join(a["uid"])
    run = c.get(f"/api/automations/{a['uid']}/runs").json()[0]
    assert run["outcome"] == "skipped" and "couldn't tell yet" in run["note"]

    people.presence.check({MAC: "10.0.0.50"})  # Dana's phone answers
    with closing(Registry()) as r:
        runner.run(r, a["uid"], "test")
    runner.join(a["uid"])
    assert c.get(f"/api/automations/{a['uid']}/runs").json()[0]["outcome"] == "succeeded"


def test_deleting_a_person_removes_the_parts_naming_them(home, dana):  # noqa: F811
    c = home["client"]
    a = create(c, name="Welcome", triggers=[{"type": "person", "target": dana, "home": True}], actions=notify())
    assert c.delete(f"/api/people/{dana}").status_code == 204
    after = c.get(f"/api/automations/{a['uid']}").json()
    assert after["triggers"] == [] and after["enabled"] is False and "Person" in after["attention"]


# --- Sweeps and outages -------------------------------------------------------------------


@pytest.fixture
def clock(monkeypatch):
    """The PC's awake time, moved by hand."""
    now = {"t": 1000.0}
    monkeypatch.setattr(people, "awake", lambda: now["t"])
    return now


def swept(network):
    """Whether the last look covered the whole subnet."""
    return len(network["nudged"][-1]) > 100  # a look nudges the phones and the router; a sweep, 253


def test_sweeps_at_start_then_only_for_a_missing_phone_backing_off(client, network, clock):  # noqa: F811
    dana = add_person(client)
    client.post(f"/api/people/{dana['uid']}/phones", json={"mac": MAC, "ip": "10.0.0.50"})
    p = people.presence
    p.check({MAC: "10.0.0.50"})
    assert swept(network)  # Control just started: the phones may be anywhere now
    clock["t"] += 30
    p.check({MAC: "10.0.0.50"})
    assert not swept(network)  # every phone answered: only their own addresses

    del network["answering"]["10.0.0.50"]  # Dana left
    looks = []
    for _ in range(80):  # 40 minutes, a look every 30 s
        clock["t"] += 30
        p.check({MAC: "10.0.0.50"})
        looks.append(swept(network))
    sweeps = [i for i, s in enumerate(looks) if s]
    # First after 5 minutes missing, then every 30 minutes: 2 sweeps in 40 minutes, not 8.
    assert len(sweeps) == 2 and (sweeps[1] - sweeps[0]) * 30 == people.SWEEP_BACKOFF

    network["answering"]["10.0.0.61"] = MAC  # back, on a new address
    clock["t"] += 30
    p.check({MAC: "10.0.0.50"})  # not found at the old address, and no sweep due yet
    assert p.home(dana["uid"]) is False
    clock["t"] += people.SWEEP_BACKOFF
    p.check({MAC: "10.0.0.50"})
    assert p.home(dana["uid"]) is True


def test_a_new_address_for_this_pc_sweeps_at_once(client, network, clock, monkeypatch):  # noqa: F811
    dana = add_person(client)
    client.post(f"/api/people/{dana['uid']}/phones", json={"mac": MAC, "ip": "10.0.0.50"})
    people.presence.check({MAC: "10.0.0.50"})
    clock["t"] += 30
    monkeypatch.setattr(people.lan, "lan_ips", lambda: ["10.0.0.7"])  # the router gave the PC a new one
    people.presence.check({MAC: "10.0.0.50"})
    assert swept(network)


def test_an_outage_makes_nobody_leave_or_arrive(home, dana, runner, clock):  # noqa: F811
    c = home["client"]
    left = create(c, name="Bye", triggers=[{"type": "home", "occupied": False}], actions=notify())
    back = create(c, name="Hi", triggers=[{"type": "home", "occupied": True}], actions=notify())
    p = people.presence
    p.check({MAC: "10.0.0.50"})
    assert p.home(dana) is True

    people.neighbors.table, real = (lambda: []), people.neighbors.table  # the router is off: nothing answers
    try:
        for _ in range(40):  # 20 minutes
            clock["t"] += 30
            p.check({MAC: "10.0.0.50"})
        assert p.home(dana) is None and p.anyone() is None  # can't tell, rather than "everyone left"
    finally:
        people.neighbors.table = real
    clock["t"] += 30
    p.check({MAC: "10.0.0.50"})  # the network is back, and so is Dana's phone
    assert p.home(dana) is True
    assert c.get(f"/api/automations/{left['uid']}/runs").json() == []
    assert c.get(f"/api/automations/{back['uid']}/runs").json() == []


def test_no_address_on_the_home_network_is_an_outage_too(client, network, clock, monkeypatch):  # noqa: F811
    dana = add_person(client)
    client.post(f"/api/people/{dana['uid']}/phones", json={"mac": MAC, "ip": "10.0.0.50"})
    people.presence.check({MAC: "10.0.0.50"})
    monkeypatch.setattr(people.lan, "lan_ips", lambda: [])  # the PC lost its Wi-Fi
    clock["t"] += 30
    people.presence.check({MAC: "10.0.0.50"})
    assert people.presence.home(dana["uid"]) is None


def test_each_missing_phone_gets_its_own_first_sweep(client, network, clock):  # noqa: F811
    dana, noa = add_person(client), add_person(client, "Noa")
    client.post(f"/api/people/{dana['uid']}/phones", json={"mac": MAC, "ip": "10.0.0.50"})
    client.post(f"/api/people/{noa['uid']}/phones", json={"mac": MAC2, "ip": "10.0.0.51"})
    network["answering"]["10.0.0.51"] = MAC2
    phones = {MAC: "10.0.0.50", MAC2: "10.0.0.51"}
    p = people.presence
    p.check(phones)
    del network["answering"]["10.0.0.50"]  # Dana leaves for the day
    for _ in range(30):  # 15 minutes: her first sweep at 5, then quiet
        clock["t"] += 30
        p.check(phones)
    del network["answering"]["10.0.0.51"]  # now Noa leaves too
    looks = []
    for _ in range(12):  # 6 minutes
        clock["t"] += 30
        p.check(phones)
        looks.append(swept(network))
    # Noa's first sweep comes 5 minutes after she went missing, not when Dana's back-off ends.
    assert looks.index(True) * 30 + 30 == people.SWEEP_AFTER


def test_without_a_router_found_it_just_doesnt_check_for_outages(client, network, clock, monkeypatch):  # noqa: F811
    dana = add_person(client)
    client.post(f"/api/people/{dana['uid']}/phones", json={"mac": MAC, "ip": "10.0.0.50"})
    monkeypatch.setattr(neighbors, "gateway", lambda own: None)  # e.g. a network without a default route
    people.presence.check({MAC: "10.0.0.50"})
    assert people.presence.home(dana["uid"]) is True
