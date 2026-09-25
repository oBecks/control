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


def test_set_light_colour(home):
    srv, light, _ = home
    out = ok(srv, "set_light", device="Yeelight color", color="#FF8800", brightness=40)
    assert light.calls == ["on", ("brightness", 40), ("rgb", (255, 136, 0))]
    assert out["power"] == "on" and out["brightness"] == 40
    assert "isn't a colour" in error(srv, "set_light", device="Yeelight color", color="orange")


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
    out = ok(srv, "set_power", device="Living room TV", on=False)
    assert out["power"] == "unknown" and "Power Toggle" in out["why_unknown"]
    assert len(tx.sent) == 1


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

    hints = {t.name: t.annotations.read_only_hint for t in anyio.run(go)}
    assert hints == {"list_devices": True, "get_device": True, "set_power": False, "set_light": False,
                     "set_climate": False, "press_button": False}


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


def test_another_controls_entry_is_outdated(claude_desktop):
    claude_desktop.write_text(json.dumps({"mcpServers": {"control": {"command": "D:\\old\\Control.exe"}}}),
                              encoding="utf-8")
    assert claude.status() == "outdated"


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


def test_phones_cant_connect_claude(client, claude_desktop):  # noqa: F811
    turn_on(client)
    p = phone()
    approve(client, p)
    assert p.get("/api/assistant").json()["can_change"] is False
    assert p.put("/api/assistant/claude").status_code == 403
    assert claude.status() == "off"
