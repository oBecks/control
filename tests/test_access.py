import pytest
from fastapi.testclient import TestClient

from control.api import access
from control.api import app as api

IPHONE_SAFARI = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
                 "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1")
IPHONE_APP = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
              "(KHTML, like Gecko) Mobile/15E148")
ANDROID_CHROME = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Mobile Safari/537.36")


@pytest.fixture
def pc(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROL_DATA_DIR", str(tmp_path))
    access._asks.clear()
    return TestClient(api.app, base_url="http://localhost", client=("127.0.0.1", 50000))


def phone(ip="10.0.0.9", ua=IPHONE_SAFARI):
    return TestClient(api.app, base_url="http://localhost", client=(ip, 50000), headers={"user-agent": ua})


def turn_on(pc):
    assert pc.put("/api/access/phone", json={"on": True}).json()["on"] is True


def approve(pc, p):
    claim = p.post("/api/access/requests").json()["claim"]
    ref = pc.get("/api/access/requests").json()[0]["ref"]
    assert pc.post(f"/api/access/requests/{ref}/approve").status_code == 204
    assert p.get(f"/api/access/claims/{claim}").json() == {"status": "approved"}


def test_phones_get_nothing_while_phone_access_is_off(pc):
    assert pc.get("/api/devices").status_code == 200
    assert pc.get("/api/access/me").json()["access"] == "local"
    r = phone().get("/api/devices")
    assert r.status_code == 403 and r.json()["code"] == "phone_access_off"


def test_unapproved_phone_only_sees_the_ui_and_the_way_in(pc):
    turn_on(pc)
    p = phone()
    r = p.get("/api/devices")
    assert r.status_code == 401 and r.json()["code"] == "approval_required"
    for path in ("/openapi.json", "/api/access/requests", "/api/access/browsers"):
        assert p.get(path).status_code == 401, path
    assert p.get("/api/access/me").json()["access"] == "none"
    assert p.get("/").status_code in (200, 503)  # the UI shell (503 until it's built)


def test_approval_gives_the_phone_a_cookie_once(pc):
    turn_on(pc)
    p = phone()
    asked = p.post("/api/access/requests").json()
    pending = pc.get("/api/access/requests").json()
    assert [(a["code"], a["name"]) for a in pending] == [(asked["code"], "iPhone · Safari")]
    assert p.get(f"/api/access/claims/{asked['claim']}").json() == {"status": "pending"}

    assert pc.post(f"/api/access/requests/{pending[0]['ref']}/approve").status_code == 204
    assert p.get(f"/api/access/claims/{asked['claim']}").json() == {"status": "approved"}
    assert p.get("/api/devices").status_code == 200
    assert p.get("/api/access/me").json()["access"] == "approved"
    # The claim is spent: nobody else can trade it for a token.
    assert phone("10.0.0.10").get(f"/api/access/claims/{asked['claim']}").json() == {"status": "expired"}

    [b] = pc.get("/api/access/browsers").json()
    assert b["name"] == "iPhone · Safari" and b["current"] is False
    assert p.get("/api/access/browsers").json()[0]["current"] is True


def test_denied_phone_stays_out(pc):
    turn_on(pc)
    p = phone()
    claim = p.post("/api/access/requests").json()["claim"]
    ref = pc.get("/api/access/requests").json()[0]["ref"]
    pc.post(f"/api/access/requests/{ref}/deny")
    assert p.get(f"/api/access/claims/{claim}").json() == {"status": "denied"}
    assert p.get("/api/devices").status_code == 401


def test_asking_again_replaces_the_earlier_code(pc):
    turn_on(pc)
    p = phone()
    p.post("/api/access/requests")
    second = p.post("/api/access/requests").json()
    assert [a["code"] for a in pc.get("/api/access/requests").json()] == [second["code"]]


def test_an_approved_phone_can_approve_others_but_not_change_phone_access(pc):
    turn_on(pc)
    first = phone()
    approve(pc, first)
    second = phone("10.0.0.10", ANDROID_CHROME)
    claim = second.post("/api/access/requests").json()["claim"]
    [ask] = first.get("/api/access/requests").json()
    assert ask["name"] == "Android · Chrome"
    first.post(f"/api/access/requests/{ask['ref']}/approve")
    assert second.get(f"/api/access/claims/{claim}").json() == {"status": "approved"}

    assert first.put("/api/access/phone", json={"on": False}).status_code == 403
    assert first.get("/api/access/phone").json()["can_change"] is False


def test_revoked_phone_is_locked_out(pc):
    turn_on(pc)
    p = phone()
    approve(pc, p)
    [b] = pc.get("/api/access/browsers").json()
    assert pc.delete(f"/api/access/browsers/{b['id']}").status_code == 204
    assert p.get("/api/devices").status_code == 401


def test_turning_phone_access_off_keeps_approvals(pc):
    turn_on(pc)
    p = phone()
    approve(pc, p)
    pc.put("/api/access/phone", json={"on": False})
    assert p.get("/api/devices").status_code == 403
    turn_on(pc)
    assert p.get("/api/devices").status_code == 200


def test_other_hosts_and_origins_are_refused(pc):
    # DNS rebinding: a website that points its own name at 127.0.0.1.
    assert pc.get("/api/devices", headers={"host": "evil.example"}).json()["code"] == "bad_host"
    # A page on another website posting to the Engine.
    r = pc.post("/api/scan", headers={"origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["code"] == "bad_origin"
    assert pc.post("/api/devices/seen", headers={"origin": "http://localhost:5173"}).status_code == 204


@pytest.mark.parametrize("ua, name", [
    (IPHONE_SAFARI, "iPhone · Safari"),
    (IPHONE_APP, "iPhone · Home Screen app"),
    (ANDROID_CHROME, "Android · Chrome"),
    ("", "Browser"),
])
def test_browser_name(ua, name):
    assert access.browser_name(ua) == name
