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


def tile(target: str, x: int, y: int, w: int = 2, h: int = 2) -> dict:
    return {"kind": "tile", "target": target, "x": x, "y": y, "w": w, "h": h}


def check(items: list[dict], targets=("a", "b"), columns=8) -> list[dict]:
    return dashboards.check_items(items, set(targets), columns)


# --- Items -----------------------------------------------------------------------------


def test_items_get_an_id_and_their_kinds_default_size():
    items = check([{"kind": "tile", "target": "a", "x": 0, "y": 1}, {"kind": "heading", "x": 0, "y": 0}])
    assert [(i["kind"], i["w"], i["h"]) for i in items] == [("tile", 2, 2), ("heading", 8, 1)]
    assert all(i["id"] for i in items) and items[0]["id"] != items[1]["id"]


def test_any_size_the_grid_holds():
    assert check([tile("a", 0, 0, 3, 5)])[0] | {"id": ""} == {"id": "", "kind": "tile", "target": "a", "x": 0,
                                                             "y": 0, "w": 3, "h": 5}
    assert check([tile("a", 0, 0, 8, 2)])[0]["w"] == 8
    with pytest.raises(ValueError, match="columns wide"):
        check([tile("a", 0, 0, 9, 2)])
    with pytest.raises(ValueError, match="rows high"):
        check([tile("a", 0, 0, 2, 1)])  # a Tile needs room for its icon and name
    with pytest.raises(ValueError, match="whole number"):
        check([tile("a", 0, 0, 1.5, 2)])


def test_a_heading_sits_right_on_top_of_one_tile():
    items = check([{"kind": "heading", "w": 2, "text": "AC", "x": 0, "y": 0}, tile("a", 0, 1)])
    assert [(i["x"], i["y"]) for i in items] == [(0, 0), (0, 1)]


def test_items_keep_their_ids_and_refuse_what_doesnt_fit():
    kept = check([{"id": "x1", **tile("a", 3, 5, 1, 2)}])
    assert kept == [{"id": "x1", "kind": "tile", "x": 3, "y": 5, "w": 1, "h": 2, "target": "a"}]
    with pytest.raises(ValueError, match="unknown"):
        check([{"kind": "spacer", "x": 0, "y": 0}])
    with pytest.raises(LookupError):
        check([tile("gone", 0, 0)])
    with pytest.raises(ValueError, match="share"):
        check([{"id": "x", **tile("a", 0, 0)}, {"id": "x", **tile("b", 4, 0)}])


def test_items_stay_inside_the_grid_and_never_overlap():
    with pytest.raises(ValueError, match="column"):
        check([tile("a", 7, 0)])  # 2 wide from the last column
    with pytest.raises(ValueError, match="whole number"):
        check([{"kind": "tile", "target": "a"}])  # no cell
    with pytest.raises(ValueError, match="overlap"):
        check([tile("a", 0, 0), tile("b", 1, 1)])
    assert len(check([tile("a", 0, 0), tile("b", 2, 0), tile("a", 0, 2)])) == 3  # side by side, then below


def test_a_heading_is_as_wide_as_the_grid_unless_made_narrower():
    with pytest.raises(ValueError, match="overlap"):
        check([{"kind": "heading", "x": 0, "y": 0}, tile("a", 6, 0)], columns=8)
    with pytest.raises(ValueError, match="columns wide"):
        dashboards.check_columns(5)


def test_a_heading_keeps_trimmed_text_its_style_and_no_target():
    [h] = check([{"kind": "heading", "text": "  Living room  ", "target": "a", "x": 0, "y": 0}])
    assert h == {"id": h["id"], "kind": "heading", "x": 0, "y": 0, "w": 8, "h": 1, "text": "Living room",
                 "align": "start", "text_size": "m", "bold": True}
    [h] = check([{"kind": "heading", "text": "AC", "x": 0, "y": 0, "w": 2, "h": 2, "align": "center",
                  "text_size": "xl", "bold": False}])
    assert (h["align"], h["text_size"], h["bold"], h["h"]) == ("center", "xl", False, 2)
    with pytest.raises(ValueError, match="aligns"):
        check([{"kind": "heading", "x": 0, "y": 0, "align": "left"}])
    with pytest.raises(ValueError, match="text is"):
        check([{"kind": "heading", "x": 0, "y": 0, "text_size": "huge"}])


def test_dashboards_from_before_free_placement_are_laid_out_as_they_looked():
    flow = [
        {"id": "h", "kind": "heading", "size": "full", "text": "Lights"},
        {"id": "a", "kind": "tile", "size": "2x1", "target": "a"},
        {"id": "s", "kind": "spacer", "size": "1x1"},
        {"id": "b", "kind": "tile", "size": "1x1", "target": "b"},
        {"id": "c", "kind": "tile", "size": "2x1", "target": "a"},  # doesn't fit the row: next one
    ]
    placed = dashboards.upgrade(flow, 4)
    assert [(i["id"], i["x"], i["y"], i["w"], i["h"]) for i in placed] == [
        ("h", 0, 0, 4, 1), ("a", 0, 1, 2, 2), ("b", 3, 1, 1, 2), ("c", 0, 3, 2, 2)]
    assert check(placed, columns=4)


def test_a_heading_with_a_size_that_makes_no_sense_spans_the_grid():
    for size in ("wide", "0x1", "", None):
        [h] = dashboards.upgrade([{"id": "h", "kind": "heading", "size": size, "x": 0, "y": 0}], 6)
        assert (h["w"], h["h"]) == (6, 1)


def test_placed_items_with_a_named_size_get_cells():
    named = [{"id": "t", "kind": "tile", "size": "2x2", "target": "a", "x": 0, "y": 1},
             {"id": "h", "kind": "heading", "size": "2x1", "text": "AC", "x": 0, "y": 0}]
    upgraded = dashboards.upgrade(named, 8)
    assert [(i["w"], i["h"]) for i in upgraded] == [(2, 4), (2, 1)]
    assert "size" not in upgraded[0]
    assert (upgraded[1]["align"], upgraded[1]["text_size"], upgraded[1]["bold"]) == ("start", "m", True)


# --- API -------------------------------------------------------------------------------


def test_make_arrange_rename_and_delete_a_dashboard(pc):
    d = pc.post("/api/dashboards", json={"name": " Phone remote ", "columns": 4, "items": [
        {"kind": "heading", "text": "Lights", "x": 0, "y": 0},
        tile("yeelight:1", 0, 1, 1, 2),
        tile(pc.group, 2, 1),
    ]})
    assert d.status_code == 201
    d = d.json()
    assert (d["name"], d["columns"]) == ("Phone remote", 4)
    assert kinds(d) == ["heading", "tile:yeelight:1", f"tile:{pc.group}"]

    # The UI sends the whole new list: the Group's Tile moved to the top, and the heading down.
    items = d["items"]
    items[2].update(x=0, y=0, h=4)
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
    # Repeated and unknown uids are ignored rather than leaving holes in the order.
    names = [x["name"] for x in pc.put("/api/dashboards/order", json={"uids": [b, "nope", b, d]}).json()]
    assert names == ["B", "D", "C", "A"]


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
    flow = [{"id": "h", "kind": "heading", "size": "2x1", "text": "AC"},
            {"id": "t", "kind": "tile", "size": "2x1", "target": "yeelight:1"}]
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
