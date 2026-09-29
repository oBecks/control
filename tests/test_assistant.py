import json
from pathlib import Path

import anyio
import httpx
import pytest
from mcp.client.client import Client
from mcp.server.mcpserver.exceptions import ToolError

from control.api import app as api
from control.assistant import claude, server
from control.engine import connect
from control.engine.found_device import Category
from control.engine.registry import Registry

from .test_access import approve, phone, turn_on
from .test_api import FakeLight, client  # noqa: F401 (client is a fixture)
from .test_climate import FakeTransmitter

TV = {"format": "buttons", "kind": "tv", "buttons": {"power": "AAAA", "volume_up": "AAAB", "input:HDMI 1": "AAAC"}}


@pytest.fixture
def home(client, monkeypatch):  # noqa: F811
    """The Engine's API with a light, an AC and a TV with only a Power Toggle."""
    r = Registry()
    r.add_remote("Living room TV", Category.MEDIA, "broadlink:aa", "learned", TV)
    r.close()
    light, tx = FakeLight(), FakeTransmitter()
    monkeypatch.setattr(api, "connect_light", lambda r, uid: (None, light))
    monkeypatch.setattr(connect, "connect_transmitter", lambda r, uid: (None, tx))
    return server.create_server(server.Engine(client)), light, tx


def call(srv, tool: str, **args):
    async def go():
        async with Client(srv) as c:
            return await c.call_tool(tool, args)

    return anyio.run(go)


def ok(srv, tool: str, **args) -> dict:
    result = call(srv, tool, **args)
    assert not result.is_error, result.content
    return json.loads(result.content[0].text)


def error(srv, tool: str, **args) -> str:
    result = call(srv, tool, **args)
    assert result.is_error
    return result.content[0].text


def test_lists_devices_but_not_hubs(home):
    srv, *_ = home
    out = ok(srv, "list_devices")
    assert {d["name"] for d in out["devices"]} == {"Yeelight color", "AC", "Living room TV"}
    assert out["not_set_up"]["devices"] == ["Tuya device"]  # needs a Link


def test_list_with_state(home):
    srv, *_ = home
    devices = {d["name"]: d for d in ok(srv, "list_devices", include_state=True)["devices"]}
    assert devices["Yeelight color"]["power"] == "off"
    assert devices["Living room TV"]["power"] == "unknown"


def test_devices_by_name_any_case_or_part_of_it(home):
    srv, *_ = home
    assert ok(srv, "get_device", device="living ROOM tv")["uid"].startswith("remote:")
    assert ok(srv, "get_device", device="yeelight")["uid"] == "yeelight:1"
    assert "No Device called 'fridge'" in error(srv, "get_device", device="fridge")


def test_an_ambiguous_name_lists_the_matches():
    devices = [{"uid": "a", "name": "Desk lamp", "category": "light"}, {"uid": "b", "name": "Desk strip", "category": "light"}]
    with pytest.raises(ToolError, match=r"several Devices: Desk lamp \(a\), Desk strip \(b\)"):
        server.find(devices, "desk")
    assert server.find(devices, "Desk lamp")["uid"] == "a"
    with pytest.raises(ToolError, match="Say which Device"):
        server.find(devices[:1], "  ")


def test_set_light_colour(home):
    srv, light, _ = home
    out = ok(srv, "set_light", device="Yeelight color", color="#FF8800", brightness=40)
    assert light.calls == ["on", ("brightness", 40), ("rgb", (255, 136, 0))]
    assert out["power"] == "on" and out["brightness"] == 40
    assert "isn't a colour" in error(srv, "set_light", device="Yeelight color", color="orange")
    assert "not both" in error(srv, "set_light", device="Yeelight color", color="#ffffff", kelvin=3000)


def test_ac_state_is_labelled_assumed(home):
    srv, _, tx = home
    out = ok(srv, "set_climate", device="AC", temperature=25)
    assert (out["power"], out["temperature"]) == ("on", 25)
    assert out["assumed"].startswith("Assumed State")
    assert tx.sent
    assert "temperature must be 16-30" in error(srv, "set_climate", device="AC", temperature=40)
    assert "isn't a light" in error(srv, "set_light", device="AC", brightness=10)


def test_a_power_toggle_never_claims_on_or_off(home):
    srv, _, tx = home
    assert "only has a Power Toggle" in error(srv, "set_power", device="Living room TV", on=False)
    assert tx.sent == []  # "turn it off" mustn't switch it on
    out = ok(srv, "press_button", device="Living room TV", button="Power")
    assert out["power"] == "unknown" and "Power Toggle" in out["why_unknown"]
    assert len(tx.sent) == 1


def test_separate_on_and_off_not_yet_used_is_unknown_but_not_a_toggle(home, client):  # noqa: F811
    srv, _, tx = home
    r = Registry()
    r.add_remote("Bedroom TV", Category.MEDIA, "broadlink:aa", "learned",
                 {"format": "buttons", "kind": "tv", "buttons": {"power_on": "AAAA", "power_off": "AAAB"}})
    r.close()
    out = ok(srv, "get_device", device="Bedroom TV")
    assert out["power"] == "unknown" and "hasn't turned it on or off yet" in out["why_unknown"]
    out = ok(srv, "set_power", device="Bedroom TV", on=False)
    assert out["power"] == "off" and out["assumed"].startswith("Assumed State")
    assert len(tx.sent) == 1


def test_no_power_button_is_said_plainly(home):
    srv, _, tx = home
    r = Registry()
    r.add_remote("Soundbar", Category.MEDIA, "broadlink:aa", "learned",
                 {"format": "buttons", "kind": "other", "buttons": {"mute": "AAAA"}})
    r.close()
    assert ok(srv, "get_device", device="Soundbar")["why_unknown"].startswith("No Power button")
    assert "has no Power button" in error(srv, "set_power", device="Soundbar", on=True)
    assert tx.sent == []


def test_press_a_button_by_label(home):
    srv, _, tx = home
    assert ok(srv, "get_device", device="Living room TV")["buttons"] == ["Power", "Volume +", "HDMI 1"]
    ok(srv, "press_button", device="Living room TV", button="volume up")
    ok(srv, "press_button", device="Living room TV", button="hdmi 1")
    assert len(tx.sent) == 2
    assert "Buttons: Power, Volume +, HDMI 1" in error(srv, "press_button", device="Living room TV", button="Netflix")


def test_read_tools_are_marked_read_only(home):
    srv, *_ = home

    async def go():
        async with Client(srv) as c:
            return (await c.list_tools()).tools

    tools = {t.name: t.annotations for t in anyio.run(go)}
    assert {n for n, a in tools.items() if a.read_only_hint} == {
        "list_devices", "get_device", "list_scenes", "list_hotkeys", "list_automations", "get_automation",
        "list_people"}
    # Pressing a button again (e.g. a Power Toggle) undoes it; creating a Group twice makes two.
    assert {n for n, a in tools.items() if a.idempotent_hint} == {
        "set_power", "set_light", "set_climate", "edit_group", "delete_group", "set_scene", "edit_scene",
        "delete_scene", "delete_hotkey", "edit_automation", "set_automation_enabled", "delete_automation"}
    assert {n for n, a in tools.items() if a.destructive_hint} == {"delete_group", "delete_scene", "delete_hotkey",
                                                                         "delete_automation"}


# --- Groups --------------------------------------------------------------------------


def test_create_and_control_a_group(home):
    srv, light, tx = home
    made = ok(srv, "create_group", name="Evening", devices=["yeelight", "AC"])
    assert made["members"] == ["Yeelight color", "AC"] and made["controls"] == "power"
    assert ok(srv, "list_devices")["groups"] == [
        {"name": "Evening", "uid": made["uid"], "group": True, "members": ["Yeelight color", "AC"]}]

    out = ok(srv, "set_power", device="evening", on=True)
    assert out["power"] == "on" and out["member_states"] == {"Yeelight color": "on", "AC": "on"}
    assert light.state.on and tx.sent
    assert "isn't a light" in error(srv, "set_light", device="Evening", brightness=10)
    assert "is a Group" in error(srv, "press_button", device="Evening", button="Power")


def test_a_group_of_lights_is_set_like_a_light(home, client):  # noqa: F811
    srv, light, _ = home
    ok(srv, "create_group", name="Lights", devices=["Yeelight color"])
    out = ok(srv, "set_light", device="Lights", brightness=40)
    assert (out["power"], out["brightness"]) == ("on", 40) and out["group"] is True
    assert client.get("/api/groups").json()[0]["made_by"] == "assistant"


def test_some_on_is_said_plainly(home, client):  # noqa: F811
    srv, light, _ = home
    r = Registry()
    r.add_remote("Fan", Category.CLIMATE, "broadlink:aa", "learned",
                 {"format": "buttons", "kind": "fan", "buttons": {"power_on": "AAAA", "power_off": "AAAB"}})
    r.close()
    ok(srv, "create_group", name="Bedroom", devices=["Yeelight color", "Fan"])
    ok(srv, "set_power", device="Fan", on=True)
    assert ok(srv, "get_device", device="Bedroom")["power"] == "some on (1 of 2)"


def test_a_power_toggle_cant_join_a_group(home):
    srv, *_ = home
    assert "only has a Power Toggle" in error(srv, "create_group", name="Media", devices=["Living room TV"])


def test_edit_and_delete_a_group(home):
    srv, *_ = home
    ok(srv, "create_group", name="Evening", devices=["Yeelight color"])
    out = ok(srv, "edit_group", group="evening", name="Night", add=["AC"])
    assert (out["name"], out["members"]) == ("Night", ["Yeelight color", "AC"])
    out = ok(srv, "edit_group", group="Night", remove=["Yeelight color"])
    assert out["members"] == ["AC"]
    assert "leave 'Night' empty" in error(srv, "edit_group", group="Night", remove=["AC"])
    assert "Say what to change" in error(srv, "edit_group", group="Night")
    assert ok(srv, "delete_group", group="Night") == {"deleted": "Night"}
    assert "No Group called 'Night'" in error(srv, "delete_group", group="Night")
    assert "groups" not in ok(srv, "list_devices")


# --- Scenes --------------------------------------------------------------------------


def test_create_set_and_read_a_scene(home, client):  # noqa: F811
    srv, light, tx = home
    light.state.on = True
    made = ok(srv, "create_scene", name="Movie night", devices=[
        {"device": "yeelight", "as_now": True}, {"device": "AC", "mode": "cool", "temperature": 24}])
    assert made["devices"] == {"Yeelight color": "On · 50% · 4000 K", "AC": "On · Cool · 24°"}
    assert client.get("/api/scenes").json()[0]["made_by"] == "assistant"
    light.state.on = False
    assert ok(srv, "list_scenes", include_state=True)["scenes"][0] | {"uid": None} == {
        "name": "Movie night", "uid": None, "devices": made["devices"], "active": False,
        "not_as_the_scene_says": ["Yeelight color", "AC"]}
    assert ok(srv, "set_scene", scene="movie") == {"set": "Movie night"}
    assert light.state.on and tx.sent
    assert ok(srv, "list_scenes", include_state=True)["scenes"][0]["active"] is True
    assert "a Power Toggle isn't a state" in error(srv, "create_scene", name="TV", devices=[{"device": "Living room TV"}])
    assert "isn't a Streamer" in error(srv, "create_scene", name="X", devices=[{"device": "AC", "app": "Netflix"}])


def test_edit_and_delete_a_scene(home):
    srv, *_ = home
    ok(srv, "create_scene", name="Evening", devices=[{"device": "Yeelight color", "on": False}])
    out = ok(srv, "edit_scene", scene="evening", name="Night", set_devices=[
        {"device": "Yeelight color", "brightness": 10}, {"device": "AC", "on": False}])
    assert out["devices"] == {"Yeelight color": "On · 10%", "AC": "Off"}
    out = ok(srv, "edit_scene", scene="Night", remove=["AC"])
    assert list(out["devices"]) == ["Yeelight color"]
    assert "leave 'Night' empty" in error(srv, "edit_scene", scene="Night", remove=["Yeelight color"])
    assert "Say what to change" in error(srv, "edit_scene", scene="Night")
    assert ok(srv, "delete_scene", scene="Night") == {"deleted": "Night"}
    assert ok(srv, "list_scenes") == {"scenes": []}


# --- Hotkeys -------------------------------------------------------------------------


@pytest.fixture
def no_listener(monkeypatch):
    from control.api import hotkeys as hotkeys_api
    from control.desktop import hotkeys as desktop_hotkeys

    monkeypatch.setattr(hotkeys_api, "listener", hotkeys_api.Listener())
    monkeypatch.setattr(desktop_hotkeys, "can_register", lambda keys: True)


def test_create_list_and_delete_hotkeys(home, client, no_listener):  # noqa: F811
    srv, *_ = home
    made = ok(srv, "create_hotkey", keys="ctrl+alt+l", device="yeelight", action="toggle")
    assert made == {"keys": "Ctrl+Alt+L", "does": "Yeelight color: Toggle", "device": "Yeelight color",
                    "made_by": "assistant", "problem": server.HOTKEYS_OFF}
    ok(srv, "create_hotkey", keys="F13", device="Yeelight color", action="brightness_down", step=20)
    ok(srv, "create_hotkey", keys="F14", device="AC", action="set", mode="heat", temperature=24)
    ok(srv, "create_hotkey", keys="F15", device="Living room TV", action="press", button="Volume +")
    listed = ok(srv, "list_hotkeys")
    assert [h["does"] for h in listed["hotkeys"]] == [
        "Yeelight color: Toggle", "Yeelight color: Brightness down 20%", "AC: Set heat, 24°", "Living room TV: Press Volume +"]
    assert listed["note"] == server.HOTKEYS_OFF
    assert ok(srv, "delete_hotkey", keys="Alt+Ctrl+L") == {"deleted": "Ctrl+Alt+L", "was": "Yeelight color: Toggle"}
    assert "No Hotkey uses Ctrl+Alt+L" in error(srv, "delete_hotkey", keys="Ctrl+Alt+L")


def test_hotkeys_the_engine_refuses_say_why(home, no_listener):
    srv, *_ = home
    assert "used for typing" in error(srv, "create_hotkey", keys="L", device="yeelight", action="toggle")
    assert "small amount" in error(srv, "create_hotkey", keys="F13", device="yeelight", action="brightness_up", step=0)
    assert "only an AC" in error(srv, "create_hotkey", keys="F13", device="yeelight", action="temperature_up")
    assert "has no remote buttons" in error(srv, "create_hotkey", keys="F13", device="AC", action="press", button="x")
    warned = ok(srv, "create_hotkey", keys="Play/Pause", device="yeelight", action="toggle")
    assert "only for Control" in warned["warning"]


def test_starts_control_when_no_engine_answers():
    started = []

    def handler(request):
        if not started:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json={"access": "local"} if request.url.path == "/api/access/me" else [])

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:8321")
    assert server.Engine(http, start=lambda: started.append(True)).call("GET", "/devices") == []
    assert started == [True]


def test_without_starting_it_says_control_isnt_running():
    def handler(request):
        raise httpx.ConnectError("refused")

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:8321")
    with pytest.raises(ToolError, match="isn't running"):
        server.Engine(http).call("GET", "/devices")


# --- Connect Claude ------------------------------------------------------------------


@pytest.fixture
def claude_desktop(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    folder = tmp_path / "Roaming" / "Claude"
    folder.mkdir(parents=True)
    return folder / claude.CONFIG


def test_connect_keeps_the_rest_of_claudes_config(claude_desktop):
    theirs = {"mcpServers": {"other": {"command": "x"}}, "preferences": {"theme": "dark"}}
    claude_desktop.write_text(json.dumps(theirs), encoding="utf-8")
    assert claude.status() == ("off", None)
    claude.connect()
    config = json.loads(claude_desktop.read_text(encoding="utf-8"))
    assert config["preferences"] == {"theme": "dark"}
    assert config["mcpServers"]["other"] == {"command": "x"}
    assert config["mcpServers"]["control"]["args"][-1] == "--mcp"
    assert json.loads(claude_desktop.with_name(claude.CONFIG + ".bak").read_text(encoding="utf-8")) == theirs
    assert claude.status() == ("connected", None)
    claude.disconnect()
    assert json.loads(claude_desktop.read_text(encoding="utf-8")) == theirs
    assert claude.status() == ("off", None)


def test_connect_creates_the_file_when_claude_has_none(claude_desktop):
    claude.connect()
    assert "control" in json.loads(claude_desktop.read_text(encoding="utf-8"))["mcpServers"]


def test_a_broken_config_is_left_alone(claude_desktop):
    claude_desktop.write_text("{not json", encoding="utf-8")
    state, why = claude.status()
    assert state == "broken" and "isn't valid JSON" in why and str(claude_desktop) in why
    with pytest.raises(ValueError, match="isn't valid JSON"):
        claude.connect()
    claude.disconnect()
    assert claude_desktop.read_text(encoding="utf-8") == "{not json"


def test_an_unreadable_config_is_broken(claude_desktop, monkeypatch):
    claude_desktop.write_text("{}", encoding="utf-8")

    def denied(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_text", denied)
    state, why = claude.status()
    assert state == "broken" and "can't be read" in why and "denied" not in why
    with pytest.raises(ValueError, match="can't be read"):
        claude.connect()


def test_the_store_install_is_connected_too(claude_desktop, tmp_path):
    store = tmp_path / "Local" / "Packages" / "Claude_abc123" / "LocalCache" / "Roaming" / "Claude"
    store.mkdir(parents=True)
    claude.connect()
    assert "control" in json.loads((store / claude.CONFIG).read_text(encoding="utf-8"))["mcpServers"]


def test_only_one_install_connected_is_partial(claude_desktop, tmp_path):
    claude.connect()
    store = tmp_path / "Local" / "Packages" / "Claude_abc123" / "LocalCache" / "Roaming" / "Claude"
    store.mkdir(parents=True)  # the Store install came later
    assert claude.status() == ("partial", None)
    claude.connect()
    assert claude.status() == ("connected", None)


def test_another_controls_entry_is_outdated_and_not_ours_to_remove(claude_desktop):
    theirs = {"mcpServers": {"control": {"command": "D:\\old\\Control.exe"}}}
    claude_desktop.write_text(json.dumps(theirs), encoding="utf-8")
    assert claude.status() == ("outdated", None)
    claude.disconnect()  # e.g. uninstalling this copy
    assert json.loads(claude_desktop.read_text(encoding="utf-8")) == theirs


def test_odd_mcp_servers_value_reads_as_off(claude_desktop):
    claude_desktop.write_text(json.dumps({"mcpServers": "?"}), encoding="utf-8")
    assert claude.status() == ("off", None)


def test_without_claude_desktop(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert claude.status() == ("missing", None)
    with pytest.raises(LookupError):
        claude.connect()


def test_connect_from_settings(client, claude_desktop):  # noqa: F811
    assert client.get("/api/assistant").json()["claude_desktop"] == "off"
    body = client.put("/api/assistant/claude").json()
    assert body["claude_desktop"] == "connected"
    assert client.delete("/api/assistant/claude").json()["claude_desktop"] == "off"


def test_a_broken_config_is_explained_before_connecting(client, claude_desktop):  # noqa: F811
    claude_desktop.write_text("{not json", encoding="utf-8")
    body = client.get("/api/assistant").json()
    assert body["claude_desktop"] == "broken" and "isn't valid JSON" in body["claude_desktop_error"]


def test_the_claude_code_command_needs_the_claude_cli(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(claude.shutil, "which", lambda name: None)
    assert client.get("/api/assistant").json()["claude_code_command"] is None
    monkeypatch.setattr(claude.shutil, "which", lambda name: r"C:\bin\claude.cmd")
    monkeypatch.setattr(claude, "command", lambda: [r"C:\Users\me\Control.exe", "--mcp"])
    assert client.get("/api/assistant").json()["claude_code_command"] == (
        r'claude mcp add --scope user control -- "C:\Users\me\Control.exe" --mcp')


def test_connect_errors_reach_the_user(client, claude_desktop):  # noqa: F811
    claude_desktop.write_text("{not json", encoding="utf-8")
    resp = client.put("/api/assistant/claude")
    assert resp.status_code == 422 and "isn't valid JSON" in resp.json()["detail"]
    claude_desktop.unlink()
    claude_desktop.parent.rmdir()
    resp = client.put("/api/assistant/claude")
    assert resp.status_code == 404 and "isn't installed" in resp.json()["detail"]


def test_phones_cant_connect_claude(client, claude_desktop):  # noqa: F811
    turn_on(client)
    p = phone()
    approve(client, p)
    assert p.get("/api/assistant").json()["can_change"] is False
    assert p.put("/api/assistant/claude").status_code == 403
    assert claude.status() == ("off", None)
    claude_desktop.write_text("{not json", encoding="utf-8")
    body = p.get("/api/assistant").json()
    assert body["claude_desktop"] == "broken" and body["claude_desktop_error"] is None  # the path is this PC's


# --- After an update, say to restart Claude until the new server calls -------------------------


def test_after_an_update_settings_say_to_restart_claude_until_the_new_server_calls(client, monkeypatch):  # noqa: F811
    from control import __version__
    from control.api import assistant as assistant_api

    monkeypatch.setattr(assistant_api, "_restart_pending", None)
    monkeypatch.setattr(claude, "status", lambda: ("connected", None))
    r = Registry()
    r.set_setting("version", "0.0.1")  # the Engine last ran an older Control
    r.close()
    assert client.get("/api/assistant").json()["restart_claude"] == __version__
    client.get("/api/devices", headers={server.MCP_HEADER: "0.0.1"})  # Claude still runs the old one
    assert client.get("/api/assistant").json()["restart_claude"] == __version__
    client.get("/api/devices", headers={server.MCP_HEADER: __version__})  # Claude was restarted
    assert client.get("/api/assistant").json()["restart_claude"] is None


def test_the_restart_note_can_be_dismissed_and_needs_claude(client, monkeypatch):  # noqa: F811
    from control.api import assistant as assistant_api

    monkeypatch.setattr(assistant_api, "_restart_pending", None)
    monkeypatch.setattr(claude, "status", lambda: ("off", None))
    # No version recorded yet but devices exist: an update from before the note.
    assert client.get("/api/assistant").json()["restart_claude"] is None  # Claude isn't connected
    monkeypatch.setattr(claude, "status", lambda: ("connected", None))
    assert client.get("/api/assistant").json()["restart_claude"] is not None
    assert client.delete("/api/assistant/restart-note").json()["restart_claude"] is None
    assert client.get("/api/assistant").json()["restart_claude"] is None


# --- Automations ---------------------------------------------------------------------


@pytest.fixture
def runner(monkeypatch):
    from control.api import automations as automations_api

    r = automations_api.Runner()
    monkeypatch.setattr(automations_api, "runner", r)
    yield r
    r.stop()


def test_create_run_and_read_an_automation(home, client, runner):  # noqa: F811
    srv, light, tx = home
    made = ok(srv, "create_automation", name="Evening",
              triggers=[{"type": "time", "at": "19:30", "days": ["Sun", "mon"]}],
              conditions=[{"type": "time", "after": "18:00", "before": "23:00"}],
              actions=[{"action": "on", "device": "yeelight"}, {"action": "wait", "minutes": 0.5},
                       {"action": "set", "device": "AC", "mode": "heat", "temperature": 24},
                       {"action": "notify", "text": "Evening on"}])
    assert made["summary"] == ("When: at 19:30, on Mon, Sun. Only if between 18:00 and 23:00. Then: Turn on "
                               "Yeelight color, then Wait 30 s, then Set AC to heat, 24°, then Notify: Evening on.")
    assert (made["on"], made["made_by"]) == (True, "assistant") and "next_run" in made
    assert client.get("/api/automations").json()[0]["made_by"] == "assistant"

    started = ok(srv, "run_automation", automation="evening")
    assert started["actions"][0] == "Turn on Yeelight color"
    runner.join(made["uid"], timeout=0.5)  # it's waiting now
    assert light.state.on
    got = ok(srv, "get_automation", automation="Evening")
    assert got["running"] and got["recent_runs"][0]["started_by"] == "Run by hand"
    assert got["actions"][0] == {"action": "on", "device": "yeelight:1", "label": "Turn on Yeelight color"}
    assert got["triggers"] == [{"type": "time", "at": "19:30", "days": ["mon", "sun"], "label": "At 19:30, on Mon, Sun"}]
    assert got["match"] == "all"
    # The parts go straight back into edit_automation: adding one Action keeps the others as they were.
    kept = [{k: v for k, v in x.items() if k != "label"} for x in got["actions"]]
    out = ok(srv, "edit_automation", automation="Evening", actions=[*kept, {"action": "off", "device": "yeelight"}])
    assert out["summary"].endswith("then Notify: Evening on, then Turn off Yeelight color.")
    assert "Set AC to heat, 24°" in out["summary"] and "Wait 30 s" in out["summary"]
    assert got["recent_runs"][0]["actions"][0] == "Turn on Yeelight color: done"


def test_edit_switch_off_and_delete_an_automation(home, runner):
    srv, *_ = home
    ok(srv, "create_automation", name="Night", actions=[{"action": "off", "device": "Yeelight color"}])
    out = ok(srv, "edit_automation", automation="night", triggers=[{"type": "time", "at": "23:00"}], name="Late")
    assert out["summary"].startswith("When: at 23:00, every day.")
    assert ok(srv, "set_automation_enabled", automation="Late", enabled=False)["on"] is False
    assert "Say what to change" in error(srv, "edit_automation", automation="Late")
    assert ok(srv, "list_automations")["automations"][0]["name"] == "Late"
    assert ok(srv, "delete_automation", automation="Late") == {"deleted": "Late"}
    assert "No Automation called 'Late'" in error(srv, "delete_automation", automation="Late")


def test_an_automation_that_runs_another(home, runner):
    srv, *_ = home
    evening = ok(srv, "create_automation", name="Evening", actions=[{"action": "on", "device": "yeelight"}])
    made = ok(srv, "create_automation", name="Home", actions=[{"action": "run_automation", "device": "evening"}])
    assert made["summary"] == "When: only when run by hand. Then: Run Evening."
    got = ok(srv, "get_automation", automation="Home")
    assert got["actions"] == [{"action": "run_automation", "device": evening["uid"], "label": "Run Evening"}]
    # What get_automation says goes straight back in.
    kept = [{k: v for k, v in x.items() if k != "label"} for x in got["actions"]]
    assert ok(srv, "edit_automation", automation="Home", actions=kept)["summary"].endswith("Run Evening.")
    assert "can't run itself" in error(srv, "edit_automation", automation="Home",
                                       actions=[{"action": "run_automation", "device": "Home"}])
    assert "Say which Automation" in error(srv, "create_automation", name="x",
                                           actions=[{"action": "run_automation"}])


def test_automations_the_engine_refuses_say_why(home, runner):
    srv, *_ = home
    assert "set your location first" in error(srv, "create_automation", name="Dusk",
                                              triggers=[{"type": "sun", "event": "sunset"}],
                                              actions=[{"action": "on", "device": "yeelight"}])
    assert "Power Toggle" in error(srv, "create_automation", name="TV",
                                   conditions=[{"type": "state", "device": "Living room TV", "on": True}],
                                   actions=[{"action": "on", "device": "yeelight"}])
    assert "`dark`" in error(srv, "create_automation", name="Night", conditions=[{"type": "sun"}],
                             actions=[{"action": "on", "device": "yeelight"}])
    assert "'someday' isn't a day" in error(srv, "create_automation", name="x",
                                            triggers=[{"type": "time", "at": "07:00", "days": ["someday"]}],
                                            actions=[{"action": "on", "device": "yeelight"}])


def test_device_triggers_from_the_assistant(home, runner):
    srv, *_ = home
    made = ok(srv, "create_automation", name="Lamp left on",
              triggers=[{"type": "state", "device": "yeelight", "on": True, "stays_minutes": 120},
                        {"type": "offline", "device": "Yeelight color", "offline": True}],
              actions=[{"action": "notify", "text": "Check the lamp"}])
    assert made["summary"].startswith("When: Yeelight color turns on and stays on for 2 h or Yeelight color goes "
                                      "Offline.")
    got = ok(srv, "get_automation", automation="Lamp left on")
    assert got["triggers"][0] == {"type": "state", "device": "yeelight:1", "on": True, "stays_minutes": 120,
                                  "label": "Yeelight color turns on and stays on for 2 h"}
    # They go straight back into edit_automation.
    kept = [{k: v for k, v in t.items() if k != "label"} for t in got["triggers"]]
    assert ok(srv, "edit_automation", automation="Lamp left on", triggers=kept)["summary"] == made["summary"]
    assert "says `on`" in error(srv, "create_automation", name="x", triggers=[{"type": "state", "device": "yeelight"}],
                                actions=[{"action": "notify", "text": "x"}])
    assert "isn't a Streamer" in error(srv, "create_automation", name="y",
                                       triggers=[{"type": "app", "device": "yeelight", "app": "Netflix"}],
                                       actions=[{"action": "notify", "text": "x"}])


def test_an_automation_with_scenes(home, runner):
    srv, *_ = home
    ok(srv, "create_scene", name="Movie night", devices=[{"device": "yeelight", "on": True}])
    made = ok(srv, "create_automation", name="Movie", triggers=[{"type": "scene", "scene": "movie"}],
              conditions=[{"type": "scene", "scene": "Movie night", "active": True}],
              actions=[{"action": "notify", "text": "Enjoy"}])
    assert made["summary"] == "When: Movie night is set. Only if Movie night is active. Then: Notify: Enjoy."
    setter = ok(srv, "create_automation", name="Dusk", actions=[{"action": "set_scene", "device": "movie"}])
    assert setter["summary"] == "When: only when run by hand. Then: Set Movie night."
    got = ok(srv, "get_automation", automation="Movie")
    kept = {k: [{f: v for f, v in x.items() if f != "label"} for x in got[k]] for k in ("triggers", "conditions")}
    assert kept["triggers"][0]["type"] == "scene" and kept["conditions"][0]["active"] is True
    assert ok(srv, "edit_automation", automation="Movie", **kept)["summary"] == made["summary"]
    assert "starts this Automation again" in error(srv, "edit_automation", automation="Movie",
                                                   actions=[{"action": "set_scene", "device": "movie"}])
    assert "Say which Scene" in error(srv, "create_automation", name="x", actions=[{"action": "set_scene"}])


def test_people_and_presence_in_automations(home, runner, monkeypatch):
    srv, *_ = home
    from control.api import people

    monkeypatch.setattr(people, "presence", people.Presence())
    r = Registry()
    dana = r.add_person("Dana")
    r.add_phone(dana, "4a:84:cf:32:5e:d9", "iPhone")
    r.close()
    assert ok(srv, "list_people") == {"people": [{"name": "Dana", "uid": dana, "is": "not known yet",
                                                  "phones": ["iPhone"]}]}
    made = ok(srv, "create_automation", name="Welcome", triggers=[{"type": "person", "person": "dana", "home": True}],
              conditions=[{"type": "home", "home": True}], actions=[{"action": "notify", "text": "Hi"}])
    assert made["summary"] == "When: Dana arrives home. Only if someone is home. Then: Notify: Hi."
    got = ok(srv, "get_automation", automation="Welcome")
    kept = {k: [{f: v for f, v in x.items() if f != "label"} for x in got[k]] for k in ("triggers", "conditions")}
    assert ok(srv, "edit_automation", automation="Welcome", **kept)["summary"] == made["summary"]
    assert "says `home`" in error(srv, "create_automation", name="x", triggers=[{"type": "home"}],
                                  actions=[{"action": "notify", "text": "Hi"}])


def test_pc_events_in_automations(home, runner):
    srv, *_ = home
    made = ok(srv, "create_automation", name="Good night", triggers=[{"type": "pc", "pc": "sleeps"}],
              actions=[{"action": "notify", "text": "Bye"}])
    assert made["summary"] == "When: the PC goes to sleep. Then: Notify: Bye."
    got = ok(srv, "get_automation", automation="Good night")
    kept = [{f: v for f, v in x.items() if f != "label"} for x in got["triggers"]]
    assert kept == [{"type": "pc", "pc": "sleeps"}]
    assert ok(srv, "edit_automation", automation="Good night", triggers=kept)["summary"] == made["summary"]
    assert "says what happens to the PC" in error(srv, "create_automation", name="x", triggers=[{"type": "pc"}],
                                                  actions=[{"action": "notify", "text": "Hi"}])


def test_a_web_link_trigger_from_the_assistant_keeps_its_secret(home, runner):
    srv, *_ = home
    made = ok(srv, "create_automation", name="Movie", triggers=[{"type": "web"}],
              actions=[{"action": "notify", "text": "Hi"}])
    assert made["summary"] == "When: the web link is opened. Then: Notify: Hi."
    assert "token" not in str(made) and "hooks" not in str(made)  # the secret stays in the app
    kept = [{f: v for f, v in x.items() if f != "label"} for x in ok(srv, "get_automation", automation="Movie")["triggers"]]
    assert kept == [{"type": "web"}]
    ok(srv, "edit_automation", automation="Movie", triggers=kept)
