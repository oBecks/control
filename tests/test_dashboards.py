import pytest

from control.engine import dashboards
from control.engine.found_device import Category, FoundDevice, Readiness
from control.engine.registry import Registry

from .test_access import approve, phone, turn_on
from .test_api import client  # noqa: F401 (client is a fixture)


@pytest.fixture
def pc(client):  # noqa: F811
    """The PC's API with two lights (yeelight:1, yeelight:2), the AC and a Group of both lights."""
    r = Registry()
    r.merge_scan([
        FoundDevice("Yeelight", "10.0.0.2", "yeelight:1", Category.LIGHT, Readiness.READY, model="color"),
        FoundDevice("Yeelight", "10.0.0.5", "yeelight:2", Category.LIGHT, Readiness.READY, model="color"),
    ], brands={"Yeelight"})
    r.close()
    g = client.post("/api/groups", json={"name": "Lights", "members": ["yeelight:1", "yeelight:2"]}).json()
    client.group = g["uid"]
    return client


def ac_uid(c) -> str:
    return next(d["uid"] for d in c.get("/api/devices").json() if d["kind"] == "remote")


def kinds(d: dict) -> list[str]:
    return [i["kind"] + (":" + i["target"] if i.get("target") else "") for i in d["items"]]


# --- Items -----------------------------------------------------------------------------


def test_items_get_an_id_and_their_kinds_default_size():
    items = dashboards.check_items([{"kind": "tile", "target": "a"}, {"kind": "spacer"}], {"a"})
    assert [(i["kind"], i["size"]) for i in items] == [("tile", "2x1"), ("spacer", "1x1")]
    assert all(i["id"] for i in items) and items[0]["id"] != items[1]["id"]


def test_items_keep_their_ids_and_refuse_what_doesnt_fit():
    kept = dashboards.check_items([{"id": "x1", "kind": "tile", "size": "1x1", "target": "a"}], {"a"})
    assert kept == [{"id": "x1", "kind": "tile", "size": "1x1", "target": "a"}]
    with pytest.raises(ValueError, match="comes in"):
        dashboards.check_items([{"kind": "tile", "size": "2x2", "target": "a"}], {"a"})
    with pytest.raises(ValueError, match="unknown"):
        dashboards.check_items([{"kind": "clock"}], set())
    with pytest.raises(LookupError):
        dashboards.check_items([{"kind": "tile", "target": "gone"}], {"a"})
    with pytest.raises(ValueError, match="share"):
        dashboards.check_items([{"id": "x", "kind": "spacer"}, {"id": "x", "kind": "spacer"}], set())


def test_a_heading_keeps_trimmed_text_and_no_target():
    [h] = dashboards.check_items([{"kind": "heading", "text": "  Living room  ", "target": "a"}], {"a"})
    assert h == {"id": h["id"], "kind": "heading", "size": "full", "text": "Living room"}
    # A narrower one sits beside other items, e.g. two rooms side by side.
    [h] = dashboards.check_items([{"kind": "heading", "size": "4x1", "text": "Kitchen"}], set())
    assert h["size"] == "4x1"


# --- API -------------------------------------------------------------------------------


def test_make_arrange_rename_and_delete_a_dashboard(pc):
    d = pc.post("/api/dashboards", json={"name": " Phone remote ", "items": [
        {"kind": "heading", "text": "Lights"},
        {"kind": "tile", "target": "yeelight:1", "size": "1x1"},
        {"kind": "tile", "target": pc.group},
        {"kind": "spacer", "size": "2x1"},
    ]})
    assert d.status_code == 201
    d = d.json()
    assert d["name"] == "Phone remote"
    assert kinds(d) == ["heading", "tile:yeelight:1", f"tile:{pc.group}", "spacer"]

    # The UI sends the whole new list: here the Group's Tile moved to the front and went small.
    items = d["items"]
    items[2]["size"] = "1x1"
    moved = [items[2], items[0], items[1], items[3]]
    d2 = pc.patch(f"/api/dashboards/{d['uid']}", json={"items": moved, "name": "Remote"}).json()
    assert d2["name"] == "Remote"
    assert [i["id"] for i in d2["items"]] == [i["id"] for i in moved]
    assert d2["items"][0]["size"] == "1x1"
    assert pc.get(f"/api/dashboards/{d['uid']}").json() == d2

    assert pc.delete(f"/api/dashboards/{d['uid']}").status_code == 204
    assert pc.get("/api/dashboards").json() == []
    assert pc.get(f"/api/dashboards/{d['uid']}").status_code == 404


def test_names_are_needed_and_unique(pc):
    assert pc.post("/api/dashboards", json={"name": "Bedroom"}).status_code == 201
    assert pc.post("/api/dashboards", json={"name": "bedroom"}).status_code == 422
    assert pc.post("/api/dashboards", json={"name": "  "}).status_code == 422


def test_bad_items_change_nothing(pc):
    d = pc.post("/api/dashboards", json={"name": "A", "items": [{"kind": "tile", "target": "yeelight:1"}]}).json()
    r = pc.patch(f"/api/dashboards/{d['uid']}", json={"items": [{"kind": "tile", "target": "nope"}]})
    assert r.status_code == 404
    assert pc.get(f"/api/dashboards/{d['uid']}").json() == d


def test_the_list_keeps_the_users_order(pc):
    a, b, c = (pc.post("/api/dashboards", json={"name": n}).json()["uid"] for n in "ABC")
    assert [d["name"] for d in pc.get("/api/dashboards").json()] == ["A", "B", "C"]
    assert [d["name"] for d in pc.put("/api/dashboards/order", json={"uids": [c, a]}).json()] == ["C", "A", "B"]
    d = pc.post("/api/dashboards", json={"name": "D"}).json()["uid"]
    assert pc.get("/api/dashboards").json()[-1]["uid"] == d


def test_forgotten_devices_and_deleted_groups_leave_every_dashboard(pc):
    ac = ac_uid(pc)
    items = [{"kind": "tile", "target": t} for t in ("yeelight:1", "yeelight:2", pc.group, ac)]
    items.insert(1, {"kind": "heading", "text": "Stays"})
    a = pc.post("/api/dashboards", json={"name": "A", "items": items}).json()["uid"]
    b = pc.post("/api/dashboards", json={"name": "B", "items": items}).json()["uid"]

    pc.delete("/api/devices/yeelight:1")
    pc.delete(f"/api/devices/{ac}")
    for uid in (a, b):
        assert kinds(pc.get(f"/api/dashboards/{uid}").json()) == ["heading", "tile:yeelight:2", f"tile:{pc.group}"]

    # The Group loses its last member and goes too.
    pc.delete("/api/devices/yeelight:2")
    assert kinds(pc.get(f"/api/dashboards/{a}").json()) == ["heading"]


def test_deleting_a_group_takes_its_tiles_off(pc):
    d = pc.post("/api/dashboards", json={"name": "A", "items": [{"kind": "tile", "target": pc.group}]}).json()
    pc.delete(f"/api/groups/{pc.group}")
    assert pc.get(f"/api/dashboards/{d['uid']}").json()["items"] == []


def test_phones_make_and_arrange_dashboards_too(pc):
    turn_on(pc)
    p = phone()
    assert p.get("/api/dashboards").status_code == 401
    approve(pc, p)
    d = p.post("/api/dashboards", json={"name": "Phone", "items": [{"kind": "tile", "target": "yeelight:1"}]})
    assert d.status_code == 201
    assert pc.get("/api/dashboards").json() == [d.json()]
