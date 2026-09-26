import json

import pytest

from control.api import app as api
from control.engine import connect, streamer
from control.engine.found_device import Category, FoundDevice, Readiness
from control.engine.registry import Registry
from control.engine.scanners import media_scanner as mdns
from control.engine.streamer import StreamerState

from .test_api import client  # noqa: F401 (client is a fixture)
from .test_assistant import error, ok

SHIELD = "androidtv:3c:6d:66:25:2f:5b"
YES = "androidtv:22:22:e3:97:82:76"


class FakeStreamer:
    def __init__(self):
        self.state = StreamerState(on=False, app="com.netflix.ninja", volume=10, volume_max=100, muted=False)
        self.calls = []

    def get_state(self):
        return self.state

    def set_power(self, on):
        self.calls.append(("power", on))
        self.state.on = on

    def press(self, button):
        streamer.key_code(button)  # refuses unknown buttons, like the real one
        self.calls.append(("press", button))

    def wake(self):
        self.calls.append(("wake",))
        self.state.app = "com.google.android.tvlauncher"

    def open_app(self, app):
        self.calls.append(("app", app))
        self.state.on, self.state.app = True, streamer.package_for(app, []) or app


# --- Apps --------------------------------------------------------------------------------


def test_yes_plus_is_ticked_only_on_yes_boxes():
    names = [e["name"] for e in streamer.default_shortcuts("yes")]
    assert names == ["YouTube", "Netflix", "Spotify", "Apple TV", "yes+"]
    shield = {e["name"]: e["default"] for e in streamer.catalogue_for("SHIELD Android TV")}
    assert shield["yes+"] is False and shield["YouTube"] is True


def test_the_open_app_is_named_from_the_shortcuts_the_catalogue_or_its_package():
    mine = [{"name": "Films", "app": "com.netflix.ninja"}]
    assert streamer.app_name("com.netflix.ninja", mine) == "Films"
    assert streamer.app_name("com.google.android.youtube.tv", []) == "YouTube"
    assert streamer.app_name("com.example.coolplayer", []) == "Coolplayer"
    assert streamer.app_name("com.google.android.tvlauncher", []) == "Home screen"
    assert streamer.app_name("com.google.android.backdrop", []) == "Screensaver"
    assert streamer.app_name("", []) is None


def test_find_an_app_by_name_part_or_package():
    apps = [{"name": "Netflix", "app": "com.netflix.ninja"}, {"name": "YouTube", "app": "com.google.android.youtube.tv"}]
    assert streamer.find_shortcut("netflix", apps) == "com.netflix.ninja"
    assert streamer.find_shortcut("tube", apps) == "com.google.android.youtube.tv"
    assert streamer.find_shortcut("Disney+", apps) == "https://www.disneyplus.com"  # the catalogue's link
    assert streamer.find_shortcut("org.example.app", apps) == "org.example.app"
    with pytest.raises(ValueError, match="its apps: Netflix, YouTube"):
        streamer.find_shortcut("Nope", apps)


def test_shortcuts_need_a_name_and_an_app_and_come_once():
    assert streamer.check_shortcuts([{"name": " A ", "app": "x.y", "link": "x://"}, {"name": "B", "app": "x.y"}]) == [
        {"name": "A", "app": "x.y", "link": "x://"}
    ]
    with pytest.raises(ValueError):
        streamer.check_shortcuts([{"name": "", "app": "x.y"}])


def test_tv_makers_are_guessed_as_tvs():
    assert streamer.guess_is_tv("Sony", "BRAVIA 4K")
    assert not streamer.guess_is_tv("NVIDIA", "SHIELD Android TV")
    assert not streamer.guess_is_tv("", "yes")


# --- Scan ----------------------------------------------------------------------------------


def svc(type_, name, ip, **txt):
    return mdns.Service(type_, name, ip, txt)


def test_android_tvs_take_their_model_from_cast_and_others_are_unsupported():
    services = [
        svc(mdns.ANDROID_TV, "SHIELD", "10.0.0.5", bt="3C:6D:66:25:2F:5B"),
        svc(mdns.CAST, "SHIELD-Android-TV-1", "10.0.0.5", md="SHIELD Android TV", fn="SHIELD", id="1"),
        svc(mdns.CAST, "Nest-Mini-2", "10.0.0.6", md="Google Nest Mini", fn="Kitchen speaker", id="2"),
        svc(mdns.AIRPLAY, "Living Room", "10.0.0.7", model="AppleTV14,1", deviceid="AA:BB"),
        svc(mdns.AIRPLAY, "MacBook", "10.0.0.8", model="MacBookPro18,1"),
    ]
    [shield] = mdns.android_tvs(services)
    assert (shield.uid, shield.model, shield.readiness) == (SHIELD, "SHIELD Android TV", Readiness.NEEDS_LINK)
    others = {d.brand: d for d in mdns.unsupported(services)}
    assert set(others) == {"Google Cast", "Apple TV"}  # not the Shield's Cast record, not a Mac
    assert others["Google Cast"].name == "Kitchen speaker"
    assert all(d.readiness is Readiness.UNSUPPORTED for d in others.values())


# --- API -------------------------------------------------------------------------------------


@pytest.fixture
def box(client, monkeypatch):  # noqa: F811
    """A yes box, found and Linked (Link calls faked), and the fake Streamer behind it."""
    r = Registry()
    r.merge_scan([FoundDevice("Android TV", "10.0.0.9", YES, Category.MEDIA, Readiness.NEEDS_LINK,
                              name="TV – סלון", model="yes")], brands={"Android TV"})
    r.close()
    fake = FakeStreamer()
    monkeypatch.setattr(api, "connect_streamer", lambda r, uid: (r.get(uid), fake))
    calls = []
    monkeypatch.setattr(api.androidtv_streamer, "start_link", lambda uid, ip: calls.append(("start", ip)))
    monkeypatch.setattr(api.androidtv_streamer, "finish_link",
                        lambda uid, ip, code: {"manufacturer": "Kaonmedia", "model": "yes"})
    monkeypatch.setattr(api.androidtv_streamer, "forget", lambda uid: calls.append(("forget", uid)))
    return client, fake, calls


def test_a_link_makes_it_a_streamer_with_the_suggested_apps(box):
    client, _, calls = box
    assert client.get(f"/api/devices/{YES}").json()["control"] is None
    assert client.post(f"/api/links/androidtv/{YES}").status_code == 204
    assert calls == [("start", "10.0.0.9")]
    out = client.post(f"/api/links/androidtv/{YES}/code", json={"code": "a1b2c3"}).json()
    assert (out["device"]["control"], out["device"]["name"], out["is_tv_guess"]) == ("streamer", "TV – סלון", False)
    assert [a["name"] for a in out["apps"] if a["default"]][-1] == "yes+"
    reading = client.get(f"/api/devices/{YES}/state").json()
    assert [a["name"] for a in reading["features"]["apps"]] == ["YouTube", "Netflix", "Spotify", "Apple TV", "yes+"]
    assert reading["state"]["app_name"] == "Netflix"


def linked(client):  # noqa: F811
    client.post(f"/api/links/androidtv/{YES}/code", json={"code": "a1b2c3"})


def test_setup_saves_the_name_whether_its_a_tv_and_the_apps(box):
    client, *_ = box
    linked(client)
    client.patch(f"/api/devices/{YES}", json={"name": "Streamer – סלון"})
    apps = [{"name": "yes+", "app": "il.co.yes.yesplus"}, {"name": "My app", "app": "org.example.app"}]
    d = client.put(f"/api/streamers/{YES}", json={"is_tv": True, "apps": apps}).json()
    assert (d["name"], d["is_tv"]) == ("Streamer – סלון", True)
    assert client.get(f"/api/devices/{YES}/state").json()["features"]["apps"] == apps
    # Linking again keeps what setup chose.
    linked(client)
    assert client.get(f"/api/devices/{YES}/state").json()["features"]["apps"] == apps


def test_power_buttons_and_apps(box):
    client, fake, _ = box
    linked(client)
    assert client.post(f"/api/devices/{YES}/state", json={"on": True}).json()["state"]["on"] is True
    client.post(f"/api/devices/{YES}/state", json={"press": "volume_up"})
    client.post(f"/api/devices/{YES}/state", json={"open_app": "com.spotify.tv.android"})
    assert fake.calls == [("power", True), ("press", "volume_up"), ("app", "com.spotify.tv.android")]  # already on
    assert client.post(f"/api/devices/{YES}/state", json={"press": "eject"}).status_code == 422


def test_streamers_join_groups(box):
    client, fake, _ = box
    linked(client)
    assert client.get(f"/api/devices/{YES}").json()["group_problem"] is None
    g = client.post("/api/groups", json={"name": "TVs", "members": [YES, "yeelight:1"]}).json()
    assert g["control"] == "power"


def test_forgetting_a_streamer_closes_its_connection_and_setup(box):
    client, _, calls = box
    linked(client)
    client.delete(f"/api/devices/{YES}")
    assert ("forget", YES) in calls
    r = Registry()
    assert r.streamer(YES) is None
    r.close()


def test_a_streamer_that_isnt_linked_cant_be_set_up(box):
    client, *_ = box
    assert client.put(f"/api/streamers/{YES}", json={"is_tv": True}).status_code == 422


def test_control_kind_needs_the_link(tmp_path):
    r = Registry(tmp_path / "c.db")
    r.merge_scan([FoundDevice("Android TV", "10.0.0.9", YES, Category.MEDIA, Readiness.NEEDS_LINK)])
    assert connect.control_kind(r, r.get(YES)) is None
    r.save_link(YES, "Box", Category.MEDIA, {})
    assert connect.control_kind(r, r.get(YES)) == "streamer"
    r.close()


# --- Assistant ------------------------------------------------------------------------------


@pytest.fixture
def assistant(box):
    from control.assistant import server

    client, fake, _ = box
    linked(client)
    return server.create_server(server.Engine(client)), fake


def test_the_assistant_reads_a_streamer_and_opens_apps(assistant):
    srv, fake = assistant
    fake.state.on = True
    out = ok(srv, "get_device", device="סלון")
    assert (out["power"], out["open_app"], out["volume"]) == ("on", "Netflix", "10 of 100")
    assert "yes+" in out["apps"]
    ok(srv, "open_app", device="סלון", app="youtube")
    assert fake.calls[-1] == ("app", "https://www.youtube.com")  # by link: a Shield refuses packages
    ok(srv, "press_button", device="סלון", button="Home")
    assert fake.calls[-1] == ("press", "home")
    assert "isn't a Streamer" in error(srv, "open_app", device="Yeelight color", app="Netflix")


def test_the_assistant_turns_a_streamer_off(assistant):
    srv, fake = assistant
    fake.state.on = True
    assert ok(srv, "set_power", device="סלון", on=False)["power"] == "off"
    assert json.dumps(fake.calls) == json.dumps([["power", False]])


# --- The Link's optional second step: adb (ADR 0008) -------------------------------------------


def test_installed_apps_get_known_names_links_and_defaults():
    apps = streamer.installed_catalogue(
        ["com.android.vending", "il.co.yes.yesplus", "com.stremio.one", "com.example.coolplayer", "com.disneyplus.mea"],
        "yes",
    )
    by = {a["app"]: a for a in apps}
    assert by["il.co.yes.yesplus"]["default"] is True  # a yes box
    assert by["com.stremio.one"]["link"] == "stremio://"
    assert by["com.example.coolplayer"]["name"] == "Coolplayer"
    assert by["com.disneyplus.mea"]["name"] == "Disney+"
    assert apps[-1]["app"] == "com.android.vending"  # system apps last


@pytest.fixture
def adb(box, monkeypatch):
    client, fake, _ = box
    linked(client)
    calls = []
    monkeypatch.setattr(api.android_adb, "allow", lambda ip: ["il.co.yes.yesplus", "com.netflix.ninja"])
    monkeypatch.setattr(api.android_adb, "installed", lambda ip: ["il.co.yes.yesplus"])
    def launch(ip, package):
        calls.append(("adb", package))
        fake.state.app = package

    monkeypatch.setattr(api.android_adb, "launch", launch)
    return client, fake, calls


def test_without_adb_a_package_opens_through_the_box_and_links_always_do(adb):
    client, fake, calls = adb
    client.post(f"/api/devices/{YES}/state", json={"open_app": "il.co.yes.yesplus"})
    assert fake.calls[-1] == ("app", "il.co.yes.yesplus") and not calls  # the Play Store way, in the adapter
    assert client.get(f"/api/streamers/{YES}/catalogue").json()["installed"] is False


def test_allowing_adb_lists_installed_apps_and_opens_packages_with_it(adb):
    client, fake, calls = adb
    choices = client.put(f"/api/streamers/{YES}/adb").json()
    assert choices["installed"] and [a["name"] for a in choices["apps"]] == ["yes+", "Netflix"]
    assert client.get(f"/api/devices/{YES}/state").json()["features"]["adb"] is True
    client.post(f"/api/devices/{YES}/state", json={"open_app": "il.co.yes.yesplus"})
    client.post(f"/api/devices/{YES}/state", json={"open_app": "https://www.netflix.com/title"})
    assert calls == [("adb", "il.co.yes.yesplus")]
    assert fake.calls[0] == ("power", True)  # woken first: adb opens apps behind a dark screen
    assert fake.calls[-1] == ("app", "https://www.netflix.com/title")
    assert [a["app"] for a in client.get(f"/api/streamers/{YES}/catalogue").json()["apps"]] == ["il.co.yes.yesplus"]
    client.delete(f"/api/streamers/{YES}/adb")
    assert client.get(f"/api/devices/{YES}/state").json()["features"]["adb"] is False


def test_adb_not_allowed_is_explained(adb, monkeypatch):
    client, *_ = adb

    def refuse(ip):
        raise api.android_adb.NotAllowed("the TV didn't allow Control")

    monkeypatch.setattr(api.android_adb, "allow", refuse)
    r = client.put(f"/api/streamers/{YES}/adb")
    assert r.status_code == 422 and "allow" in r.json()["detail"]


def test_an_older_database_gets_the_adb_column(tmp_path):
    import sqlite3

    db = sqlite3.connect(tmp_path / "old.db")
    db.execute("CREATE TABLE streamers (uid TEXT PRIMARY KEY, is_tv INTEGER NOT NULL DEFAULT 0, apps TEXT NOT NULL DEFAULT '[]')")
    db.execute("INSERT INTO streamers VALUES ('androidtv:x', 0, '[]')")
    db.commit()
    db.close()
    r = Registry(tmp_path / "old.db")
    assert r.streamer("androidtv:x")["adb"] is False
    r.close()


class FakeRemote:
    """The Play Store answers a details link; OK on its page opens the app (when installed)."""

    def __init__(self, installed=True):
        self.current_app, self.installed, self.sent = "com.google.android.tvlauncher", installed, []

    def send_launch_app_command(self, link):
        self.sent.append(link)
        self.current_app = "com.android.vending" if link.startswith("market://details") else "com.netflix.ninja"

    def send_key_command(self, key):
        self.sent.append(key)
        if key == "DPAD_CENTER" and self.installed:
            self.current_app = "il.co.yes.yesplus"


def test_an_app_without_a_link_opens_through_its_play_store_page(monkeypatch):
    from control.engine.adapters import androidtv_streamer as atv

    remote = FakeRemote()

    async def connected(uid, ip):
        return remote

    monkeypatch.setattr(atv, "_connected", connected)
    monkeypatch.setattr(atv.asyncio, "sleep", _no_wait(atv.asyncio.sleep))
    box = atv.AndroidTVStreamer.__new__(atv.AndroidTVStreamer)
    box._uid, box._ip = "androidtv:x", "10.0.0.9"
    box.open_app("il.co.yes.yesplus")
    assert remote.sent == ["market://details?id=il.co.yes.yesplus", "DPAD_CENTER"]
    box.open_app("https://www.netflix.com/title")
    assert remote.sent[-1] == "https://www.netflix.com/title"
    remote.installed = False
    with pytest.raises(ValueError, match="is it installed"):
        box.open_app("il.co.yes.yesplus")


def _no_wait(sleep):
    async def quick(seconds):
        await sleep(0)

    return quick


# --- Small fixes ---------------------------------------------------------------------------


def test_a_link_names_its_package():
    mine = [{"name": "Mine", "app": "org.example.tv", "link": "example://"}]
    assert streamer.package_for("https://www.youtube.com", []) == "com.google.android.youtube.tv"
    assert streamer.package_for("example://", mine) == "org.example.tv"
    assert streamer.package_for("il.co.yes.yesplus", []) == "il.co.yes.yesplus"
    assert streamer.package_for("unknown://", []) is None


def test_opening_an_app_answers_once_the_streamer_reports_it(adb, monkeypatch):
    client, fake, _ = adb
    client.put(f"/api/streamers/{YES}/adb")
    reads = {"n": 0}
    real = fake.get_state

    def slow_state():  # the box reports yes+ only on the third read after adb opens it
        reads["n"] += 1
        state = real()
        state.app = "il.co.yes.yesplus" if reads["n"] >= 3 else "com.google.android.tvlauncher"
        return state

    fake.get_state = slow_state
    monkeypatch.setattr(api.time, "sleep", lambda s: None)
    reply = client.post(f"/api/devices/{YES}/state", json={"open_app": "il.co.yes.yesplus"}).json()
    assert reply["state"]["app_name"] == "yes+"


def test_a_box_showing_its_screensaver_is_woken_before_an_app_opens(box):
    client, fake, _ = box
    linked(client)
    fake.state.on, fake.state.app = True, "com.google.android.backdrop"
    client.post(f"/api/devices/{YES}/state", json={"open_app": "https://www.youtube.com"})
    assert fake.calls == [("wake",), ("app", "https://www.youtube.com")]
