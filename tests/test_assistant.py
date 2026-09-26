import json

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
    assert {n for n, a in tools.items() if a.read_only_hint} == {"list_devices", "get_device"}
    # Pressing a button again (e.g. a Power Toggle) undoes it; creating a Group twice makes two.
    assert {n for n, a in tools.items() if a.idempotent_hint} == {
        "set_power", "set_light", "set_climate", "edit_group", "delete_group"}
    assert {n for n, a in tools.items() if a.destructive_hint} == {"delete_group"}


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
    assert claude.status() == "off"
    claude.connect()
    config = json.loads(claude_desktop.read_text(encoding="utf-8"))
    assert config["preferences"] == {"theme": "dark"}
    assert config["mcpServers"]["other"] == {"command": "x"}
    assert config["mcpServers"]["control"]["args"][-1] == "--mcp"
    assert json.loads(claude_desktop.with_name(claude.CONFIG + ".bak").read_text(encoding="utf-8")) == theirs
    assert claude.status() == "connected"
    claude.disconnect()
    assert json.loads(claude_desktop.read_text(encoding="utf-8")) == theirs
    assert claude.status() == "off"


def test_connect_creates_the_file_when_claude_has_none(claude_desktop):
    claude.connect()
    assert "control" in json.loads(claude_desktop.read_text(encoding="utf-8"))["mcpServers"]


def test_a_broken_config_is_left_alone(claude_desktop):
    claude_desktop.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="isn't valid JSON"):
        claude.connect()
    claude.disconnect()
    assert claude_desktop.read_text(encoding="utf-8") == "{not json"


def test_the_store_install_is_connected_too(claude_desktop, tmp_path):
    store = tmp_path / "Local" / "Packages" / "Claude_abc123" / "LocalCache" / "Roaming" / "Claude"
    store.mkdir(parents=True)
    claude.connect()
    assert "control" in json.loads((store / claude.CONFIG).read_text(encoding="utf-8"))["mcpServers"]


def test_another_controls_entry_is_outdated_and_not_ours_to_remove(claude_desktop):
    theirs = {"mcpServers": {"control": {"command": "D:\\old\\Control.exe"}}}
    claude_desktop.write_text(json.dumps(theirs), encoding="utf-8")
    assert claude.status() == "outdated"
    claude.disconnect()  # e.g. uninstalling this copy
    assert json.loads(claude_desktop.read_text(encoding="utf-8")) == theirs


def test_odd_mcp_servers_value_reads_as_off(claude_desktop):
    claude_desktop.write_text(json.dumps({"mcpServers": "?"}), encoding="utf-8")
    assert claude.status() == "off"


def test_without_claude_desktop(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert claude.status() == "missing"
    with pytest.raises(LookupError):
        claude.connect()


def test_connect_from_settings(client, claude_desktop):  # noqa: F811
    assert client.get("/api/assistant").json()["claude_desktop"] == "off"
    body = client.put("/api/assistant/claude").json()
    assert body["claude_desktop"] == "connected"
    assert "claude mcp add --scope user control --" in body["claude_code_command"]
    assert client.delete("/api/assistant/claude").json()["claude_desktop"] == "off"


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
    assert claude.status() == "off"
