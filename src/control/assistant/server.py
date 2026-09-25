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

START_TIMEOUT = 30  # seconds to wait for a Control it started
REQUEST_TIMEOUT = 30  # a device that doesn't answer takes a few seconds to give up on

INSTRUCTIONS = """\
Control reads and controls the Devices in the user's home: lights, plugs, and Remote Devices (ACs,
TVs, fans) that Control drives through an infrared Hub. Refer to a Device by its name or uid.

Be honest about state:
- An Assumed State (ACs, TVs and fans) is what Control last sent. Someone may have used the physical
  remote since, so say "Control last set it to…", not "it is…".
- When power is "unknown", the Device only has a Power Toggle: nobody knows whether it's on.
- An Offline Device wasn't seen in the last scan, so controlling it may fail.

Setting things up (scanning, adding Devices, Learning buttons, renaming) happens in the Control app
itself; point the user there."""

ASSUMED = "Assumed State: what Control last sent. It may differ if someone used the physical remote."
TOGGLE_ONLY = "Only a Power Toggle: Control can press Power but never knows whether the Device is on."
OFFLINE = "Offline: Control didn't see it in its last scan, so it may not answer."
HUB = "transmitter"  # Hubs never appear on Home, so the Assistant doesn't see them either

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
SET = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
# Pressing a button: pressing it again can undo it (a Power Toggle).
PRESS = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)


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


def find(devices: list[dict], ref: str) -> dict:
    """A Device by uid or name: exact name first (any case), then a unique part of a name."""
    ref = ref.strip()
    if not ref:
        raise ToolError("Say which Device, by name or uid.")
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
        raise ToolError(f"'{ref}' matches several Devices: {listed}. Say which one, by name or uid.")
    names = ", ".join(d["name"] for d in devices) or "none yet"
    raise ToolError(f"No Device called '{ref}'. Devices: {names}.")


def controllable(d: dict) -> dict:
    if d["control"] is None:
        raise ToolError(f"'{d['name']}' can't be controlled yet. Finish setting it up in Control (Add devices).")
    return d


def summary(d: dict) -> dict:
    out = {"name": d["name"], "uid": d["uid"], "category": d["category"]}
    if not d["online"]:
        out["offline"] = OFFLINE
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
            if f["can_power"]:
                out["why_unknown"] = TOGGLE_ONLY
        else:
            out["power"] = "on" if s["on"] else "off"
            out["assumed"] = ASSUMED
        out["buttons"] = [b["label"] for b in f["buttons"]]
    return out


def find_button(features: dict, ref: str) -> str:
    """A button's name, from its name or its label ("Volume +", "volume up", "HDMI 1")."""
    key = ref.strip().casefold()
    for b in features["buttons"]:
        if key in (b["name"].casefold(), b["label"].casefold(), b["name"].replace("_", " ").casefold()):
            return b["name"]
    labels = ", ".join(b["label"] for b in features["buttons"]) or "none yet"
    raise ToolError(f"No '{ref}' button. Buttons: {labels}.")


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

    def lookup(ref: str) -> dict:
        return find(engine.call("GET", "/devices"), ref)

    def read(d: dict) -> dict:
        return describe(d, engine.call("GET", f"/devices/{d['uid']}/state"))

    def change(d: dict, body: dict) -> dict:
        return describe(d, engine.call("POST", f"/devices/{d['uid']}/state", body))

    @server.tool(title="List Devices", annotations=READ)
    def list_devices(include_state: bool = False) -> dict:
        """List the Devices in the user's home by name, uid and category (light, plug, climate, media).
        include_state also reads each Device's current state, which takes a few seconds."""
        devices = [d for d in engine.call("GET", "/devices") if d["category"] != HUB]
        ready = [d for d in devices if d["control"]]
        out: dict = {"devices": [summary(d) for d in ready]}
        if include_state:

            def state(d: dict) -> dict:
                try:
                    return read(d)
                except ToolError as exc:
                    return summary(d) | {"error": str(exc)}

            with ThreadPoolExecutor(max_workers=8) as pool:
                out["devices"] = list(pool.map(state, ready))
        not_ready = [d["name"] for d in devices if not d["control"]]
        if not_ready:
            out["not_set_up"] = {"devices": not_ready, "note": "Control can't control these until they're set up in the app."}
        return out

    @server.tool(title="Get Device state", annotations=READ)
    def get_device(device: str) -> dict:
        """One Device's current state (power, brightness, colour, AC mode and temperature…), what can
        be set on it, and for TVs and fans its buttons."""
        return read(controllable(lookup(device)))

    @server.tool(title="Turn a Device on or off", annotations=SET)
    def set_power(device: str, on: bool) -> dict:
        """Turn a Device on or off. Refused for a Device with only a Power Toggle, since Control can't
        know which way Power would switch it; press_button "Power" toggles it."""
        d = controllable(lookup(device))
        if d["control"] == "remote":
            features = engine.call("GET", f"/devices/{d['uid']}/state")["features"]
            if not features["discrete_power"]:
                raise ToolError(f"'{d['name']}' only has a Power Toggle, so Control can't turn it "
                                f"{'on' if on else 'off'} for sure: Power switches it whichever way it wasn't. "
                                "If the user knows it's the other way now, use press_button with \"Power\".")
        return change(d, {"on": on})

    @server.tool(title="Set a light", annotations=SET)
    def set_light(device: str, brightness: int | None = None, color: str | None = None,
                  kelvin: int | None = None) -> dict:
        """Set a light's brightness (1-100), colour (#RRGGBB) or white temperature (kelvin). Setting
        any of them also turns the light on. Use set_power to turn it off."""
        d = controllable(lookup(device))
        if d["control"] != "light":
            raise ToolError(f"'{d['name']}' isn't a light.")
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
        """Set an AC's mode, target temperature, fan speed or swing. Like its remote, changing any of
        them also turns it on. get_device lists the values it accepts."""
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
        """Press one button of a TV's, fan's or other Remote Device's remote, e.g. "Volume +", "Mute",
        "HDMI 1". get_device lists its buttons."""
        d = controllable(lookup(device))
        if d["control"] != "remote":
            raise ToolError(f"'{d['name']}' has no remote buttons. Use set_power, set_light or set_climate.")
        features = engine.call("GET", f"/devices/{d['uid']}/state")["features"]
        return change(d, {"press": find_button(features, button)})

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
    http = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=REQUEST_TIMEOUT)
    create_server(Engine(http, start=lambda: start_control(port))).run("stdio")
