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
from typing import Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from .. import __version__
from ..engine import hotkeys
from ..engine.streamer import CATALOGUE, find_shortcut

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

Hotkeys: keys on this PC (e.g. Ctrl+Alt+L, F13, or a media key such as Play/Pause) that do one thing
to one Device or Group: toggle it, turn it on or off, step brightness or temperature, set it, press
one of its buttons, or open a Streamer's app. You can list, create and delete them when the user
asks; the app marks them as made by the Assistant. They work only while the Control app runs on this
PC, and the keys then reach only Control, never the app in front: suggest spare keys (F13-F24, or
Ctrl+Alt with a letter) rather than keys the user types or uses elsewhere.

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

    @server.tool(title="List Hotkeys", annotations=READ)
    def list_hotkeys() -> dict:
        """List the Hotkeys: keys on this PC that do one thing to a Device or Group."""
        body = engine.call("GET", "/hotkeys")
        out: dict = {"hotkeys": [hotkey_summary(h) for h in body["hotkeys"]]}
        if not body["listening"]:
            out["note"] = HOTKEYS_OFF
        return out

    @server.tool(title="Create a Hotkey", annotations=CREATE)
    def create_hotkey(keys: str, device: str, action: HotkeyAction, step: float | None = None,
                      button: str | None = None, app: str | None = None, brightness: int | None = None,
                      color: str | None = None, kelvin: int | None = None, mode: str | None = None,
                      temperature: float | None = None, fan: str | None = None) -> dict:
        """Create a Hotkey: keys on this PC (e.g. "Ctrl+Alt+L", "F13", "Play/Pause") that do one thing
        to a Device or Group. action:
        - toggle, on, off
        - brightness_up / brightness_down (a light, by `step` %, default 10), temperature_up /
          temperature_down (an AC, by `step` degrees, default 1); holding the keys keeps stepping
        - set: any of brightness, color (#RRGGBB), kelvin, mode, temperature, fan
        - press: one of a remote's or Streamer's buttons (`button`, e.g. "Volume +"); holding repeats
        - open_app: a Streamer's app (`app`, e.g. "Netflix")
        Keys that type text need Ctrl, Alt or Win. The keys then reach only Control.
        The same keys can also have a double press ("Ctrl+Alt+L (double)") and a long press
        ("Ctrl+Alt+L (long)", held half a second); their single press then waits a moment for a
        second press. A sequence ("Ctrl+Alt+L, then 1") takes a second key within 2 seconds, which may
        type text, and the first keys then start only sequences."""
        d = controllable(lookup(device))
        action_body = hotkey_action(d, action, step, button, app,
                                    {"brightness": brightness, "kelvin": kelvin, "mode": mode,
                                     "target_temp": temperature, "fan": fan, "color": color})
        h = engine.call("POST", "/hotkeys", {"keys": keys, "target": d["uid"], "action": action_body,
                                             "by_assistant": True})
        out = hotkey_summary(h)
        check = engine.call("POST", "/hotkeys/check", {"keys": h["keys"], "uid": h["uid"]})
        if check.get("warning"):
            out["warning"] = check["warning"]
        return out

    @server.tool(title="Delete a Hotkey", annotations=DELETE)
    def delete_hotkey(keys: str) -> dict:
        """Delete a Hotkey, by its keys (e.g. "Ctrl+Alt+L", "F13 (double)", "Ctrl+Alt+L, then 1").
        The keys go back to other apps."""
        try:
            label = hotkeys.parse_trigger(keys).label
        except ValueError as exc:
            raise ToolError(str(exc)) from None
        found = [h for h in engine.call("GET", "/hotkeys")["hotkeys"] if h["keys"].casefold() == label.casefold()]
        if not found:
            raise ToolError(f"No Hotkey uses {label}. list_hotkeys lists them.")
        engine.call("DELETE", f"/hotkeys/{found[0]['uid']}")
        return {"deleted": label, "was": f"{found[0]['target_name']}: {found[0]['action_label']}"}

    def hotkey_action(d: dict, action: str, step: float | None, button: str | None, app: str | None,
                      settings: dict) -> dict:
        if action == "toggle":
            return {"do": "toggle"}
        if action in ("on", "off"):
            return {"do": "set", "state": {"on": action == "on"}}
        if action in ("brightness_up", "brightness_down", "temperature_up", "temperature_down"):
            field = "brightness" if action.startswith("brightness") else "target_temp"
            by = abs(step) if step is not None else hotkeys.DEFAULT_STEP[field]  # 0 is refused by the Engine
            return {"do": "step", "field": field, "by": by if action.endswith("_up") else -by}
        if action == "press":
            if not button:
                raise ToolError("Say which button to press.")
            if is_group(d) or d["control"] not in ("remote", "streamer"):
                raise ToolError(f"'{d['name']}' has no remote buttons.")
            features = engine.call("GET", f"/devices/{d['uid']}/state")["features"]
            return {"do": "press", "button": find_button(features, button)}
        if action == "open_app":
            if not app:
                raise ToolError("Say which app to open.")
            if d["control"] != "streamer":
                raise ToolError(f"'{d['name']}' isn't a Streamer, so it can't open apps.")
            apps = engine.call("GET", f"/devices/{d['uid']}/state")["features"]["apps"]
            return {"do": "open_app", "app": app_package(apps, app)}
        if action == "set":
            color = settings.pop("color")
            state = {k: v for k, v in settings.items() if v is not None}
            if color is not None:
                state["rgb"] = parse_color(color)
            if not state:
                raise ToolError("Say what to set: brightness, color, kelvin, mode, temperature or fan.")
            return {"do": "set", "state": state}
        raise ToolError(f"Unknown action '{action}'.")

    return server


HotkeyAction = Literal["toggle", "on", "off", "brightness_up", "brightness_down", "temperature_up",
                       "temperature_down", "set", "press", "open_app"]
HOTKEYS_OFF = "The Control app isn't running on this PC, so Hotkeys don't work until it starts."
HOTKEY_PROBLEMS = {
    "off": HOTKEYS_OFF,
    "taken": "Another app has these keys, so this Hotkey doesn't work. Pick other keys.",
}


def hotkey_summary(h: dict) -> dict:
    out = {"keys": h["keys"], "does": f"{h['target_name']}: {h['action_label']}", "device": h["target_name"]}
    if h["made_by"] == "assistant":
        out["made_by"] = "assistant"
    if h["status"] in HOTKEY_PROBLEMS:
        out["problem"] = HOTKEY_PROBLEMS[h["status"]]
    return out


def app_package(apps: list[dict], ref: str) -> str:
    """A Streamer app's package from its name: one of its apps, or one Control knows."""
    key = ref.strip().casefold()
    for pool in (apps, CATALOGUE):
        exact = [a for a in pool if a["name"].casefold() == key or a["app"] == ref]
        if exact:
            return exact[0]["app"]
        partial = [a for a in pool if key and key in a["name"].casefold()]
        if len(partial) == 1:
            return partial[0]["app"]
    names = ", ".join(a["name"] for a in apps) or "none yet"
    raise ToolError(f"No app '{ref}' on this Streamer. Its apps: {names}.")


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
