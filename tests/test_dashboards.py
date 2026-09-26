import json

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


def tile(target: str, x: int, y: int, size: str = "2x1") -> dict:
    return {"kind": "tile", "target": target, "x": x, "y": y, "size": size}


def check(items: list[dict], targets=("a", "b"), columns=8) -> list[dict]:
    return dashboards.check_items(items, set(targets), columns)


# --- Items -----------------------------------------------------------------------------


def test_items_get_an_id_and_their_kinds_default_size():
    items = check([{"kind": "tile", "target": "a", "x": 0, "y": 1}, {"kind": "heading", "x": 0, "y": 0}])
    assert [(i["kind"], i["size"]) for i in items] == [("tile", "2x1"), ("heading", "full")]
    assert all(i["id"] for i in items) and items[0]["id"] != items[1]["id"]


def test_a_tile_is_two_rows_high_and_a_heading_one():
    assert dashboards.cells("tile", "2x1", 8) == (2, 2)
    assert dashboards.cells("tile", "1x1", 8) == (1, 2)
    assert dashboards.cells("tile", "2x2", 8) == (2, 4)
    assert dashboards.cells("heading", "2x1", 8) == (2, 1)
    assert dashboards.cells("heading", "full", 6) == (6, 1)


def test_a_heading_sits_right_on_top_of_one_tile():
    items = check([{"kind": "heading", "size": "2x1", "text": "AC", "x": 0, "y": 0}, tile("a", 0, 1)])
    assert [(i["x"], i["y"]) for i in items] == [(0, 0), (0, 1)]


def test_items_keep_their_ids_and_refuse_what_doesnt_fit():
    kept = check([{"id": "x1", **tile("a", 3, 5, "1x1")}])
    assert kept == [{"id": "x1", "kind": "tile", "size": "1x1", "x": 3, "y": 5, "target": "a"}]
    with pytest.raises(ValueError, match="comes in"):
        check([tile("a", 0, 0, "4x1")])
    with pytest.raises(ValueError, match="unknown"):
        check([{"kind": "spacer", "x": 0, "y": 0}])
    with pytest.raises(LookupError):
        check([tile("gone", 0, 0)])
    with pytest.raises(ValueError, match="share"):
        check([{"id": "x", **tile("a", 0, 0)}, {"id": "x", **tile("b", 4, 0)}])


def test_items_stay_inside_the_grid_and_never_overlap():
    with pytest.raises(ValueError, match="column"):
        check([tile("a", 7, 0)])  # 2 wide from the last column
    with pytest.raises(ValueError, match="cell"):
        check([{"kind": "tile", "target": "a"}])  # no cell
    with pytest.raises(ValueError, match="overlap"):
        check([tile("a", 0, 0), tile("b", 1, 1)])
    assert len(check([tile("a", 0, 0), tile("b", 2, 0), tile("a", 0, 2)])) == 3  # side by side, then below


def test_a_full_heading_is_as_wide_as_the_grid():
    with pytest.raises(ValueError, match="overlap"):
        check([{"kind": "heading", "x": 0, "y": 0}, tile("a", 6, 0)], columns=8)
    with pytest.raises(ValueError, match="columns wide"):
        dashboards.check_columns(5)


def test_a_heading_keeps_trimmed_text_and_no_target():
    [h] = check([{"kind": "heading", "text": "  Living room  ", "target": "a", "x": 0, "y": 0}])
    assert h == {"id": h["id"], "kind": "heading", "size": "full", "x": 0, "y": 0, "text": "Living room"}


def test_dashboards_from_before_free_placement_are_laid_out_as_they_looked():
    flow = [
        {"id": "h", "kind": "heading", "size": "full", "text": "Lights"},
        {"id": "a", "kind": "tile", "size": "2x1", "target": "a"},
        {"id": "s", "kind": "spacer", "size": "1x1"},
        {"id": "b", "kind": "tile", "size": "1x1", "target": "b"},
        {"id": "c", "kind": "tile", "size": "2x1", "target": "a"},  # doesn't fit the row: next one
    ]
    placed = dashboards.from_flow(flow, 4)
    assert [(i["id"], i["x"], i["y"]) for i in placed] == [("h", 0, 0), ("a", 0, 1), ("b", 3, 1), ("c", 0, 3)]
    assert check(placed, columns=4)


# --- API -------------------------------------------------------------------------------


def test_make_arrange_rename_and_delete_a_dashboard(pc):
    d = pc.post("/api/dashboards", json={"name": " Phone remote ", "columns": 4, "items": [
        {"kind": "heading", "text": "Lights", "x": 0, "y": 0},
        tile("yeelight:1", 0, 1, "1x1"),
        tile(pc.group, 2, 1),
    ]})
    assert d.status_code == 201
    d = d.json()
    assert (d["name"], d["columns"]) == ("Phone remote", 4)
    assert kinds(d) == ["heading", "tile:yeelight:1", f"tile:{pc.group}"]

    # The UI sends the whole new list: the Group's Tile moved to the top, and the heading down.
    items = d["items"]
    items[2].update(x=0, y=0, size="2x2")
    items[0].update(y=4)
    items[1].update(x=2, y=0)
    d2 = pc.patch(f"/api/dashboards/{d['uid']}", json={"items": items, "name": "Remote"}).json()
    assert d2["name"] == "Remote"
    assert [(i["x"], i["y"]) for i in d2["items"]] == [(0, 4), (2, 0), (0, 0)]
    assert pc.get(f"/api/dashboards/{d['uid']}").json() == d2

    assert pc.delete(f"/api/dashboards/{d['uid']}").status_code == 204
    assert pc.get("/api/dashboards").json() == []
    assert pc.get(f"/api/dashboards/{d['uid']}").status_code == 404


def test_names_are_needed_and_unique(pc):
    assert pc.post("/api/dashboards", json={"name": "Bedroom"}).json()["columns"] == 8
    assert pc.post("/api/dashboards", json={"name": "bedroom"}).status_code == 422
    assert pc.post("/api/dashboards", json={"name": "  "}).status_code == 422


def test_narrowing_needs_the_items_to_fit(pc):
    d = pc.post("/api/dashboards", json={"name": "A", "items": [tile("yeelight:1", 6, 0)]}).json()
    assert pc.patch(f"/api/dashboards/{d['uid']}", json={"columns": 4}).status_code == 422
    moved = [{**d["items"][0], "x": 2}]
    d2 = pc.patch(f"/api/dashboards/{d['uid']}", json={"columns": 4, "items": moved}).json()
    assert (d2["columns"], d2["items"][0]["x"]) == (4, 2)


def test_bad_items_change_nothing(pc):
    d = pc.post("/api/dashboards", json={"name": "A", "items": [tile("yeelight:1", 0, 0)]}).json()
    r = pc.patch(f"/api/dashboards/{d['uid']}", json={"items": [tile("nope", 0, 0)]})
    assert r.status_code == 404
    r = pc.patch(f"/api/dashboards/{d['uid']}", json={"items": [tile("yeelight:1", 0, 0), tile("yeelight:2", 1, 0)]})
    assert r.status_code == 422
    assert pc.get(f"/api/dashboards/{d['uid']}").json() == d


def test_the_list_keeps_the_users_order(pc):
    a, b, c = (pc.post("/api/dashboards", json={"name": n}).json()["uid"] for n in "ABC")
    assert [d["name"] for d in pc.get("/api/dashboards").json()] == ["A", "B", "C"]
    assert [d["name"] for d in pc.put("/api/dashboards/order", json={"uids": [c, a]}).json()] == ["C", "A", "B"]
    d = pc.post("/api/dashboards", json={"name": "D"}).json()["uid"]
    assert pc.get("/api/dashboards").json()[-1]["uid"] == d


def test_forgotten_devices_and_deleted_groups_leave_every_dashboard(pc):
    ac = ac_uid(pc)
    items = [tile(t, 0, 1 + 2 * n) for n, t in enumerate(("yeelight:1", "yeelight:2", pc.group, ac))]
    items.insert(1, {"kind": "heading", "text": "Stays", "x": 0, "y": 0})
    a = pc.post("/api/dashboards", json={"name": "A", "items": items}).json()["uid"]
    b = pc.post("/api/dashboards", json={"name": "B", "items": items}).json()["uid"]

    pc.delete("/api/devices/yeelight:1")
    pc.delete(f"/api/devices/{ac}")
    for uid in (a, b):
        d = pc.get(f"/api/dashboards/{uid}").json()
        assert kinds(d) == ["heading", "tile:yeelight:2", f"tile:{pc.group}"]
        assert [i["y"] for i in d["items"]] == [0, 3, 5]  # the rest stays where it was

    # The Group loses its last member and goes too.
    pc.delete("/api/devices/yeelight:2")
    assert kinds(pc.get(f"/api/dashboards/{a}").json()) == ["heading"]


def test_deleting_a_group_takes_its_tiles_off(pc):
    d = pc.post("/api/dashboards", json={"name": "A", "items": [tile(pc.group, 0, 0)]}).json()
    pc.delete(f"/api/groups/{pc.group}")
    assert pc.get(f"/api/dashboards/{d['uid']}").json()["items"] == []


def test_a_dashboard_stored_as_a_flow_comes_back_placed(pc):
    uid = pc.post("/api/dashboards", json={"name": "Old"}).json()["uid"]
    r = Registry()
    flow = [{"id": "h", "kind": "heading", "size": "2x1", "text": "AC"}, {"id": "t", "kind": "tile", "size": "2x1",
                                                                          "target": "yeelight:1"}]
    with r._db:
        r._db.execute("UPDATE dashboards SET items = ? WHERE uid = ?", (json.dumps(flow), uid))
    r.close()
    d = pc.get(f"/api/dashboards/{uid}").json()
    assert [(i["id"], i["x"], i["y"]) for i in d["items"]] == [("h", 0, 0), ("t", 2, 0)]


def test_phones_make_and_arrange_dashboards_too(pc):
    turn_on(pc)
    p = phone()
    assert p.get("/api/dashboards").status_code == 401
    approve(pc, p)
    d = p.post("/api/dashboards", json={"name": "Phone", "columns": 4, "items": [tile("yeelight:1", 0, 0)]})
    assert d.status_code == 201
    assert pc.get("/api/dashboards").json() == [d.json()]
