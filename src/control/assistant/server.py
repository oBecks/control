"""The MCP server (ADR 0005): `Control.exe --mcp`, started by Claude (or any MCP client) and speaking
MCP over stdio. It's a Client of the Engine like the Window: every tool is a call to the Engine's API
on 127.0.0.1, and it never opens the Registry.

Read and control only; setup stays in the UI. Answers stay honest: an Assumed State is labelled as
assumed, a Power Toggle's power is unknown, and an Offline Device says so.
"""

import logging
import os
import subprocess
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from .. import __version__
from ..engine.streamer import find_shortcut

MCP_HEADER = "X-Control-MCP"  # sent with every Engine call: this server's version
START_TIMEOUT = 30  # seconds to wait for a Control it started
REQUEST_TIMEOUT = 30  # a device that doesn't answer takes a few seconds to give up on

INSTRUCTIONS = """\
Control reads and controls the Devices in the user's home: lights, plugs, Streamers (Android TV
boxes such as an NVIDIA Shield, and TVs running Android TV), and Remote Devices (ACs, TVs, fans) that
Control drives through an infrared Hub. Refer to a Device by its name or uid.

Be honest about state:
- An Assumed State (ACs, TVs and fans) is what Control last sent. Someone may have used the physical
  remote since, so say "Control last set it to…", not "it is…".
- When power is "unknown", the Device only has a Power Toggle: nobody knows whether it's on.
- An Offline Device wasn't seen in the last scan, so controlling it may fail.
- A Streamer reports its real state (power, the open app, volume). A Streamer's power is the box's:
  the TV it's plugged into usually follows it, but may not.

Groups: a Group is a named set of Devices controlled as one (e.g. "Living room lights"). get_device,
set_power, set_light and set_climate take a Group's name too, and change every member at once. A
Group of lights takes what every one of its lights can do, a Group of ACs likewise, any other Group
only on/off. You can create, edit and delete Groups when the user asks; the app marks them as made
by the Assistant.

Setting things up (scanning, adding Devices, Learning buttons, renaming Devices) happens in the
Control app itself; point the user there."""

ASSUMED = "Assumed State: what Control last sent. It may differ if someone used the physical remote."
TOGGLE_ONLY = "Only a Power Toggle: Control can press Power but never knows whether the Device is on."
NOT_SET_YET = "Control hasn't turned it on or off yet, so it doesn't know. set_power sets it for sure."
NO_POWER = "No Power button has been set up for it yet."
OFFLINE = "Offline: Control didn't see it in its last scan, so it may not answer."
HUB = "transmitter"  # Hubs never appear on Home, so the Assistant doesn't see them either

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
SET = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
# Pressing a button: pressing it again can undo it (a Power Toggle).
PRESS = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
CREATE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
DELETE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False)


# --- The Engine ----------------------------------------------------------------


class Engine:
    """The Engine's HTTP API. If nothing answers, `start` launches Control and the call waits for it."""

    def __init__(self, http: httpx.Client, start: Callable[[], None] | None = None):
        self._http = http
        self._start = start

    def call(self, method: str, path: str, body: dict | None = None):
        try:
            resp = self._send(method, path, body)
        except httpx.ConnectError:
            if self._start is None:
                raise ToolError("Control isn't running. Open Control on this PC and try again.") from None
            self._start_and_wait()
            resp = self._send(method, path, body)
        if resp.is_error:
            raise ToolError(_detail(resp))
        return resp.json() if resp.content else None

    def _send(self, method: str, path: str, body: dict | None) -> httpx.Response:
        try:
            return self._http.request(method, f"/api{path}", json=body)
        except httpx.ConnectError:
            raise
        except httpx.TransportError:
            raise ToolError("Control didn't answer in time. The Device may be unreachable.") from None

    def _start_and_wait(self) -> None:
        self._start()
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            try:
                if self._http.get("/api/access/me", timeout=2).is_success:
                    return
            except httpx.TransportError:
                pass
            time.sleep(0.5)
        raise ToolError("Control didn't start. Open Control on this PC and try again.")


def _detail(resp: httpx.Response) -> str:
    try:
        detail = resp.json().get("detail")
    except ValueError:
        detail = None
    return detail if isinstance(detail, str) else f"Control answered {resp.status_code}"


def start_control(port: int) -> None:
    """Start the Desktop App in the tray, detached so it outlives the Assistant's session."""
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--hidden", "--port", str(port)]
    else:
        cmd = [sys.executable, "-m", "control.desktop", "--hidden", "--port", str(port)]
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    io = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    try:
        # Out of the client's Job Object too: quitting Claude mustn't stop Control. Claude's (Node's)
        # job lets it go anyway; the Python MCP SDK's client forbids it, so there Control stops with
        # the session.
        subprocess.Popen(cmd, creationflags=flags | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0), **io)
    except OSError:
        subprocess.Popen(cmd, creationflags=flags, **io)


# --- Devices ---------------------------------------------------------------------


def find(devices: list[dict], ref: str, what: str = "Device") -> dict:
    """A Device (or Group) by uid or name: exact name first (any case), then a unique part of a name."""
    ref = ref.strip()
    if not ref:
        raise ToolError(f"Say which {what}, by name or uid.")
    devices = [d for d in devices if d["category"] != HUB]
    for d in devices:
        if d["uid"] == ref:
            return d
    key = ref.casefold()
    matches = [d for d in devices if d["name"].casefold() == key] or [d for d in devices if key in d["name"].casefold()]
    if len(matches) == 1:
        return matches[0]
    if matches:
        listed = ", ".join(f"{d['name']} ({d['uid']})" for d in matches)
        raise ToolError(f"'{ref}' matches several {what}s: {listed}. Say which one, by name or uid.")
    names = ", ".join(d["name"] for d in devices) or "none yet"
    raise ToolError(f"No {what} called '{ref}'. {what}s: {names}.")


def is_group(d: dict) -> bool:
    return d["uid"].startswith("group:")


def controllable(d: dict) -> dict:
    if d["control"] is None:
        raise ToolError(f"'{d['name']}' can't be controlled yet. Finish setting it up in Control (Add devices).")
    return d


def summary(d: dict) -> dict:
    out = {"name": d["name"], "uid": d["uid"], "category": d["category"]}
    if not d["online"]:
        out["offline"] = OFFLINE
    return out


def group_summary(g: dict, devices: list[dict]) -> dict:
    names = {d["uid"]: d["name"] for d in devices}
    return {"name": g["name"], "uid": g["uid"], "group": True, "members": [names.get(m, m) for m in g["members"]]}


def describe_group(g: dict, reading: dict, devices: list[dict]) -> dict:
    """A Group's state: what its members share, whether all, some or none are on, and each member."""
    by_uid = {d["uid"]: d for d in devices}
    out = group_summary(g, devices)
    shared = describe({"name": g["name"], "uid": g["uid"], "category": g["category"], "online": True}, reading)
    out |= {k: v for k, v in shared.items() if k not in ("name", "uid", "category")}
    on, total = reading["on_count"], reading["total"]
    out["power"] = "on" if on == total else "off" if on == 0 else f"some on ({on} of {total})"
    out["member_states"] = {
        by_uid[uid]["name"]: describe(by_uid[uid], m)["power"] for uid, m in reading["members"].items() if uid in by_uid
    }
    if reading["failed"]:
        out["not_answering"] = [f["reason"] for f in reading["failed"].values()]
    return out


def describe(d: dict, reading: dict) -> dict:
    """A Device's state in the words the Assistant should use, and what can be set."""
    out = summary(d)
    control, s, f = reading["control"], reading["state"], reading["features"]
    if control == "light":
        out["power"] = "on" if s["on"] else "off"
        out["brightness"] = s["brightness"]
        if s["mode"] == "color" and s.get("rgb"):
            out["color"] = "#{:02x}{:02x}{:02x}".format(*s["rgb"])
        elif s.get("kelvin"):
            out["color"] = f"white {s['kelvin']}K"
        out["can_set"] = {"brightness": "1-100", "color": f["color"]}
        if f["color_temp"]:
            out["can_set"]["kelvin"] = f"{f['min_kelvin']}-{f['max_kelvin']}"
    elif control == "plug":
        out["power"] = "on" if s["on"] else "off"
    elif control == "climate":
        out["power"] = "on" if s["on"] else "off"
        out |= {"mode": s["mode"], "temperature": s["target_temp"], "fan": s["fan"]}
        if s.get("swing"):
            out["swing"] = s["swing"]
        out["assumed"] = ASSUMED
        options = {"mode": f["modes"], "temperature": f"{f['min_temp']:g}-{f['max_temp']:g}",
                   "fan": f["fan_modes"], "swing": f["swing_modes"]}
        out["can_set"] = {k: v for k, v in options.items() if v}  # an AC without swing has no swing
    elif control == "remote":
        if s["on"] is None:
            out["power"] = "unknown"
            if f["discrete_power"]:
                out["why_unknown"] = NOT_SET_YET
            elif f["can_power"]:
                out["why_unknown"] = TOGGLE_ONLY
            else:
                out["why_unknown"] = NO_POWER
        else:
            out["power"] = "on" if s["on"] else "off"
            out["assumed"] = ASSUMED
        out["buttons"] = [b["label"] for b in f["buttons"]]
    elif control == "streamer":
        out["power"] = "on" if s["on"] else "off"
        if s["on"] and s.get("app_name"):
            out["open_app"] = s["app_name"]
        if s.get("volume") is not None and s.get("volume_max"):
            out["volume"] = f"{s['volume']} of {s['volume_max']}" + (" (muted)" if s.get("muted") else "")
        out["buttons"] = [b["label"] for b in f["buttons"]]
        out["apps"] = [a["name"] for a in f["apps"]]
    return out


def find_button(features: dict, ref: str) -> str:
    """A button's name, from its name or its label ("Volume +", "volume up", "HDMI 1")."""
    key = ref.strip().casefold()
    for b in features["buttons"]:
        if key in (b["name"].casefold(), b["label"].casefold(), b["name"].replace("_", " ").casefold()):
            return b["name"]
    labels = ", ".join(b["label"] for b in features["buttons"]) or "none yet"
    raise ToolError(f"No '{ref}' button. Buttons: {labels}.")


def find_app(apps: list[dict], ref: str) -> str:
    """An app's package from its name: one of the Streamer's apps, or a well-known one."""
    return find_shortcut(ref, apps)


def parse_color(text: str) -> list[int]:
    hex_ = text.strip().lstrip("#")
    if len(hex_) != 6:
        raise ToolError(f"'{text}' isn't a colour. Give it as #RRGGBB, e.g. #ff8800.")
    try:
        return [int(hex_[i : i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        raise ToolError(f"'{text}' isn't a colour. Give it as #RRGGBB, e.g. #ff8800.") from None


# --- The server ------------------------------------------------------------------


def create_server(engine: Engine) -> MCPServer:
    server = MCPServer("Control", title="Control", instructions=INSTRUCTIONS, version=__version__)

    def home_devices() -> list[dict]:
        return [d for d in engine.call("GET", "/devices") if d["category"] != HUB]

    def lookup(ref: str) -> dict:
        """A Device or a Group (which acts as one Device)."""
        return find(home_devices() + engine.call("GET", "/groups"), ref)

    def lookup_group(ref: str) -> dict:
        return find(engine.call("GET", "/groups"), ref, "Group")

    def read(d: dict) -> dict:
        if is_group(d):
            return describe_group(d, engine.call("GET", f"/groups/{d['uid']}/state"), home_devices())
        return describe(d, engine.call("GET", f"/devices/{d['uid']}/state"))

    def change(d: dict, body: dict) -> dict:
        if is_group(d):
            return describe_group(d, engine.call("POST", f"/groups/{d['uid']}/state", body), home_devices())
        return describe(d, engine.call("POST", f"/devices/{d['uid']}/state", body))

    def member_uids(refs: list[str]) -> list[str]:
        known = home_devices()
        return [find(known, ref)["uid"] for ref in refs]

    @server.tool(title="List Devices", annotations=READ)
    def list_devices(include_state: bool = False) -> dict:
        """List the Devices in the user's home by name, uid and category (light, plug, climate, media),
        and the user's Groups with their members. include_state also reads each Device's and Group's
        current state, which takes a few seconds."""
        everything = home_devices()
        ready = [d for d in everything if d["control"]]
        group_list = engine.call("GET", "/groups")
        out: dict = {"devices": [summary(d) for d in ready]}
        if group_list:
            out["groups"] = [group_summary(g, everything) for g in group_list]
        if include_state:

            def state(d: dict) -> dict:
                try:
                    return read(d)
                except ToolError as exc:
                    return (group_summary(d, everything) if is_group(d) else summary(d)) | {"error": str(exc)}

            with ThreadPoolExecutor(max_workers=8) as pool:
                out["devices"] = list(pool.map(state, ready))
                if group_list:
                    out["groups"] = list(pool.map(state, group_list))
        not_ready = [d["name"] for d in everything if not d["control"]]
        if not_ready:
            out["not_set_up"] = {"devices": not_ready, "note": "Control can't control these until they're set up in the app."}
        return out

    @server.tool(title="Get Device state", annotations=READ)
    def get_device(device: str) -> dict:
        """One Device's or Group's current state (power, brightness, colour, AC mode and temperature…),
        what can be set on it, and for TVs and fans its buttons. A Group also lists each member's power."""
        return read(controllable(lookup(device)))

    @server.tool(title="Turn a Device on or off", annotations=SET)
    def set_power(device: str, on: bool) -> dict:
        """Turn a Device, or every Device in a Group, on or off. Refused for a Device with only a Power
        Toggle, since Control can't know which way Power would switch it; press_button "Power" toggles it."""
        d = controllable(lookup(device))
        if d["control"] == "remote":
            features = engine.call("GET", f"/devices/{d['uid']}/state")["features"]
            if not features["can_power"]:
                raise ToolError(f"'{d['name']}' has no Power button yet. It can be taught in Control (Add devices).")
            if not features["discrete_power"]:
                raise ToolError(f"'{d['name']}' only has a Power Toggle, so Control can't turn it "
                                f"{'on' if on else 'off'} for sure: Power switches it whichever way it wasn't. "
                                "If the user knows it's the other way now, use press_button with \"Power\".")
        return change(d, {"on": on})

    @server.tool(title="Set a light", annotations=SET)
    def set_light(device: str, brightness: int | None = None, color: str | None = None,
                  kelvin: int | None = None) -> dict:
        """Set a light's (or a Group of lights') brightness (1-100), colour (#RRGGBB) or white
        temperature (kelvin). Setting any of them also turns the light on. Use set_power to turn it off."""
        d = controllable(lookup(device))
        if d["control"] != "light":
            raise ToolError(f"'{d['name']}' isn't a light.")
        if color is not None and kelvin is not None:
            raise ToolError("Give either a color or a white temperature (kelvin), not both.")
        body: dict = {"brightness": brightness, "kelvin": kelvin}
        if color is not None:
            body["rgb"] = parse_color(color)
        body = {k: v for k, v in body.items() if v is not None}
        if not body:
            raise ToolError("Say what to set: brightness, color or kelvin.")
        return change(d, body)

    @server.tool(title="Set an AC", annotations=SET)
    def set_climate(device: str, mode: str | None = None, temperature: float | None = None,
                    fan: str | None = None, swing: str | None = None) -> dict:
        """Set an AC's (or a Group of ACs') mode, target temperature, fan speed or swing. Like its
        remote, changing any of them also turns it on. get_device lists the values it accepts."""
        d = controllable(lookup(device))
        if d["control"] != "climate":
            raise ToolError(f"'{d['name']}' isn't an AC.")
        body = {k: v for k, v in {"mode": mode, "target_temp": temperature, "fan": fan, "swing": swing}.items()
                if v is not None}
        if not body:
            raise ToolError("Say what to set: mode, temperature, fan or swing.")
        return change(d, body)

    @server.tool(title="Press a remote button", annotations=PRESS)
    def press_button(device: str, button: str) -> dict:
        """Press one button of a TV's, fan's or other Remote Device's remote, or of a Streamer's, e.g.
        "Volume +", "Mute", "HDMI 1", "Home". get_device lists its buttons."""
        d = controllable(lookup(device))
        if d["control"] not in ("remote", "streamer"):
            what = "is a Group, which has" if is_group(d) else "has"
            raise ToolError(f"'{d['name']}' {what} no remote buttons. Use set_power, set_light or set_climate.")
        features = engine.call("GET", f"/devices/{d['uid']}/state")["features"]
        return change(d, {"press": find_button(features, button)})

    @server.tool(title="Open an app", annotations=PRESS)
    def open_app(device: str, app: str) -> dict:
        """Open an app on a Streamer (e.g. "Netflix", "YouTube"), by the name of one of its apps
        (get_device lists them) or of another well-known app. Opening an app also wakes the Streamer."""
        d = controllable(lookup(device))
        if d["control"] != "streamer":
            raise ToolError(f"'{d['name']}' isn't a Streamer, so it can't open apps.")
        apps = engine.call("GET", f"/devices/{d['uid']}/state")["features"]["apps"]
        try:
            package = find_app(apps, app)
        except ValueError as exc:
            raise ToolError(str(exc)) from None
        return change(d, {"open_app": package})

    @server.tool(title="Create a Group", annotations=CREATE)
    def create_group(name: str, devices: list[str]) -> dict:
        """Create a Group: a named set of Devices controlled as one (e.g. "Living room lights" from the
        lights in the living room). Devices by name or uid. A Device with only a Power Toggle can't join,
        since a Group couldn't be sure to turn it off. The Group works right away."""
        g = engine.call("POST", "/groups", {"name": name, "members": member_uids(devices), "by_assistant": True})
        return group_summary(g, home_devices()) | {"controls": g["control"]}

    @server.tool(title="Edit a Group", annotations=SET)
    def edit_group(group: str, name: str | None = None, add: list[str] | None = None,
                   remove: list[str] | None = None) -> dict:
        """Rename a Group, or add Devices to it and remove Devices from it (by name or uid)."""
        g = lookup_group(group)
        members = list(g["members"])
        if add:
            members += [uid for uid in member_uids(add) if uid not in members]
        if remove:
            gone = set(member_uids(remove))
            members = [m for m in members if m not in gone]
        if name is None and members == g["members"]:
            raise ToolError("Say what to change: a new name, or Devices to add or remove.")
        if not members:
            raise ToolError(f"That would leave '{g['name']}' empty. Use delete_group to remove it.")
        body = {"name": name, "members": members if members != g["members"] else None}
        g = engine.call("PATCH", f"/groups/{g['uid']}", {k: v for k, v in body.items() if v is not None})
        return group_summary(g, home_devices()) | {"controls": g["control"]}

    @server.tool(title="Delete a Group", annotations=DELETE)
    def delete_group(group: str) -> dict:
        """Delete a Group. Its Devices stay as they are; only the Group goes."""
        g = lookup_group(group)
        engine.call("DELETE", f"/groups/{g['uid']}")
        return {"deleted": g["name"]}

    return server


def run(port: int) -> None:
    """`Control.exe --mcp`: serve MCP on stdin/stdout until the client closes them."""
    # Windows otherwise decodes the pipes in the system code page and garbles non-English names.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if stream is not None:
            stream.reconfigure(encoding="utf-8")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # a line per Engine call in Claude's log
    if sys.stderr is None:  # a client that doesn't collect the server's log
        sys.stderr = open(os.devnull, "w")  # noqa: SIM115 (lives as long as the server)
    # The header tells the Engine which version's tools Claude has (Settings says when to restart Claude).
    http = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=REQUEST_TIMEOUT,
                        headers={MCP_HEADER: __version__})
    create_server(Engine(http, start=lambda: start_control(port))).run("stdio")
