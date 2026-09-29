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
from pydantic import BaseModel, Field
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from .. import __version__
from ..engine import hotkeys
from . import MCP_HEADER
from ..engine.streamer import CATALOGUE, find_shortcut

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

Scenes: a Scene is a named end state for several Devices and Groups (e.g. "Movie night": the ceiling
light off, the lamp at 20% warm white, the AC at 24° cool, the SHIELD on Netflix), set in one go with
set_scene. It holds states, not steps or button presses, and each Device sets only what the Scene
says (a lamp that's just "off" keeps its colour). A Scene is active while every Device in it is as
the Scene says (an AC's Assumed State counts). A Remote Device with only a Power Toggle can't be in
one. You can create (from how things are now, or with the values the user gives), edit and delete
Scenes when the user asks; the app marks them as made by the Assistant.

Hotkeys: keys on this PC (e.g. Ctrl+Alt+L, F13, or a media key such as Play/Pause) that do one thing
to one Device or Group: toggle it, turn it on or off, step brightness or temperature, set it, press
one of its buttons, or open a Streamer's app; or that run one Automation or set one Scene. You can
list, create and delete them when the user asks; the app marks them as made by the Assistant. They work only while the Control app runs on this
PC, and the keys then reach only Control, never the app in front: suggest spare keys (F13-F24, or
Ctrl+Alt with a letter) rather than keys the user types or uses elsewhere.

Automations: When (Triggers: a time on some days; sunrise/sunset with an offset; a Device or Group
turns on or off, or a Streamer opens an app, each optionally only once it stays so for some
minutes; a Device goes Offline or comes back online; a Scene is set, by anyone; a Person arrives
or leaves; the first person arrives or the last leaves) → Only if (Conditions: a Device or Group is
on/off, a Streamer has an app open, a Scene is active or not, a Person is home or away, someone or
nobody is home, a time window, some days, dark or light; all of them or any one) → Then (Actions in order: control a
Device or Group the way a Hotkey does, set a Scene, run another Automation, wait, notify). Control runs them itself while it's running on this PC. You can list,
read (with recent Runs), create, edit, delete, run, and switch them on and off when the user asks;
they're active right away and the app marks them as made by the Assistant. After creating one, tell
the user its `summary` so they can check it. A timed Trigger missed while the PC was off or asleep
is skipped, never run late. Running one by hand, or from another Automation's Action, skips its
Conditions; Automations can't run each other in a loop. Device Triggers fire on changes
from anywhere (a wall switch, another app, Control, another Automation); an AC, TV or fan changes
only when Control sends it something, and one with only a Power Toggle can't be a Trigger. A Device
counts as Offline after a minute without answering. An Automation isn't set off by its own changes,
and one set off too often in a minute is switched off (it may be in a loop). Sunrise and sunset need the
home's location, set in Control (Settings or the Automation builder).

People: the people who live in the home, each known by their phone(s). A Person is home while one
of their phones answers on the home Wi-Fi, and away once none has for 10 minutes; right after
Control starts it may not know yet. list_people says who's home. People and their phones are set up
in the Control app (Settings → People).

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


# --- Automations -----------------------------------------------------------------

DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DEVICE_TRIGGERS = ("state", "app", "offline")


class SceneDeviceIn(BaseModel):
    """One Device or Group in a Scene, and how it should be. Give no values (or as_now) to keep how
    it is now."""

    device: str = Field(description="a Device's or Group's name or uid")
    as_now: bool = Field(False, description="keep how it is right now (the other values are then ignored)")
    on: bool | None = Field(None, description="false: off (then nothing else); setting anything else turns it on")
    brightness: int | None = Field(None, description="a light: 1-100")
    color: str | None = Field(None, description="a light: #RRGGBB")
    kelvin: int | None = Field(None, description="a light: white temperature")
    mode: str | None = Field(None, description="an AC's mode")
    temperature: float | None = Field(None, description="an AC's temperature")
    fan: str | None = Field(None, description="an AC's fan speed")
    swing: str | None = Field(None, description="an AC's swing")
    app: str | None = Field(None, description='a Streamer: the app it has open, e.g. "Netflix"')


def scene_summary(sc: dict, active: dict | None = None) -> dict:
    out = {"name": sc["name"], "uid": sc["uid"],
           "devices": {p["target_name"]: p["label"] for p in sc["parts"]}}
    if sc["attention"]:
        out["needs_attention"] = sc["attention"]
    if active is not None:
        out["active"] = active["active"]
        if not active["active"]:
            out["not_as_the_scene_says"] = [p["target_name"] for p, ok in zip(sc["parts"], active["parts"]) if not ok]
    return out


class TriggerIn(BaseModel):
    """What starts an Automation."""

    type: Literal["time", "sun", "state", "app", "offline", "scene", "person", "home", "pc"]
    at: str | None = Field(None, description='time: "HH:MM", 24-hour, the PC\'s local time')
    event: Literal["sunrise", "sunset"] | None = Field(None, description="sun")
    offset_minutes: int = Field(0, description="sun: minutes before (negative) or after, at most 180")
    days: list[str] | None = Field(None, description='time, sun: e.g. ["mon", "tue"]; left out: every day')
    device: str | None = Field(None, description="state, app, offline: a Device's name or uid (state: or a Group's)")
    on: bool | None = Field(None, description="state: true when it turns on (a Group: its first member), false "
                                              "when it turns off (a Group: its last member)")
    stays_minutes: int = Field(0, description="state, app: only once it has stayed so (on, off, or the app "
                                               "open) this long, 0-1440 minutes; 0: at once")
    app: str | None = Field(None, description="app: when this Streamer opens this app, e.g. Netflix")
    offline: bool | None = Field(None, description="offline: true when it goes Offline (a minute without an "
                                                   "answer), false when it comes back online")
    scene: str | None = Field(None, description="scene: when this Scene is set (by name or uid), by anyone")
    person: str | None = Field(None, description="person: a Person's name or uid")
    home: bool | None = Field(None, description="person: true when they arrive home, false when they leave; "
                                                "home: true when the first person arrives, false when the last leaves")
    pc: Literal["starts", "wakes", "unlocks", "locks", "sleeps", "shuts_down"] | None = Field(
        None, description="pc: Control starts (with Windows, say), the PC wakes from sleep, you unlock it or sign "
                          "in, it's locked, it goes to sleep, or it shuts down or you sign out. Going to sleep and "
                          "shutting down leave only a moment, so only quick Actions get done")


class ConditionIn(BaseModel):
    """Something that must be true when a Trigger fires."""

    type: Literal["state", "app", "time", "days", "sun", "scene", "person", "home"]
    device: str | None = Field(None, description="state, app: a Device's or Group's name or uid")
    on: bool | None = Field(None, description="state: true while it's on (a Group: any member), false while off")
    app: str | None = Field(None, description="app: the app a Streamer has open, e.g. Netflix")
    after: str | None = Field(None, description='time: from "HH:MM"')
    before: str | None = Field(None, description='time: until "HH:MM" (may be past midnight)')
    days: list[str] | None = Field(None, description='days: e.g. ["fri", "sat"]')
    dark: bool | None = Field(None, description="sun: true between sunset and sunrise, false in daylight")
    scene: str | None = Field(None, description="scene: a Scene's name or uid")
    active: bool = Field(True, description="scene: true while every Device in it is as it says, false while not")
    person: str | None = Field(None, description="person: a Person's name or uid")
    home: bool | None = Field(None, description="person: true while they're home, false while away; "
                                                "home: true while someone is home, false while nobody is")


class ActionIn(BaseModel):
    """One step of an Automation, done in order."""

    action: Literal["toggle", "on", "off", "brightness_up", "brightness_down", "temperature_up",
                    "temperature_down", "set", "press", "open_app", "run_automation", "set_scene", "wait",
                    "notify"]
    device: str | None = Field(None, description="a Device's or Group's name or uid, for all but wait and notify; "
                                                 "run_automation: the Automation's; set_scene: the Scene's")
    step: float | None = Field(None, description="brightness_* (%, default 10) or temperature_* (degrees, default 1)")
    button: str | None = Field(None, description='press: e.g. "Volume +"')
    app: str | None = Field(None, description='open_app: e.g. "Netflix"')
    brightness: int | None = Field(None, description="set: 1-100")
    color: str | None = Field(None, description="set: #RRGGBB")
    kelvin: int | None = Field(None, description="set: white temperature")
    mode: str | None = Field(None, description="set: an AC's mode")
    temperature: float | None = Field(None, description="set: an AC's temperature")
    fan: str | None = Field(None, description="set: an AC's fan speed")
    minutes: float | None = Field(None, description="wait: how long, e.g. 10 or 0.5")
    text: str | None = Field(None, description="notify: what the notification says")


def automation_trigger(t: TriggerIn) -> dict:
    if t.type == "time":
        return {"type": "time", "at": t.at, "days": day_numbers(t.days)}
    return {"type": "sun", "event": t.event, "offset": t.offset_minutes, "days": day_numbers(t.days)}


def day_numbers(days: list[str] | None) -> list[int] | None:
    if days is None:
        return None
    out = []
    for d in days:
        key = d.strip().casefold()[:3]
        if key not in DAY_NAMES:
            raise ToolError(f"'{d}' isn't a day. Days: {', '.join(DAY_NAMES)}.")
        out.append(DAY_NAMES.index(key))
    return out


def _days_in(days: list[int]) -> list[str] | None:
    return None if len(days) == 7 else [DAY_NAMES[d] for d in days]


def _without_none(part: dict) -> dict:
    return {k: v for k, v in part.items() if v is not None}


# An Automation's parts as the Engine keeps them, back in the shape create_automation and
# edit_automation take (with the Engine's `label`), so an edit can pass the ones that stay unchanged.
# Devices are given by uid, buttons and apps by the names Control keeps.


def trigger_in(t: dict) -> dict:
    kind, label = t["type"], t["label"]
    if kind == "state":
        return {"type": kind, "device": t["target"], "on": t["on"], "stays_minutes": t["minutes"], "label": label}
    if kind == "app":
        return {"type": kind, "device": t["target"], "app": t["app"], "stays_minutes": t.get("minutes", 0),
                "label": label}
    if kind == "offline":
        return {"type": kind, "device": t["target"], "offline": t["offline"], "label": label}
    if kind == "scene":
        return {"type": kind, "scene": t["target"], "label": label}
    if kind == "person":
        return {"type": kind, "person": t["target"], "home": t["home"], "label": label}
    if kind == "home":
        return {"type": kind, "home": t["occupied"], "label": label}
    if kind == "pc":
        return {"type": kind, "pc": t["event"], "label": label}
    if t["type"] == "time":
        return _without_none({"type": "time", "at": t["at"], "days": _days_in(t["days"]), "label": t["label"]})
    return _without_none({"type": "sun", "event": t["event"], "offset_minutes": t["offset"],
                          "days": _days_in(t["days"]), "label": t["label"]})


def condition_in(c: dict) -> dict:
    kind, label = c["type"], c["label"]
    if kind == "state":
        return {"type": kind, "device": c["target"], "on": c["on"], "label": label}
    if kind == "app":
        return {"type": kind, "device": c["target"], "app": c["app"], "label": label}
    if kind == "time":
        return {"type": kind, "after": c["after"], "before": c["before"], "label": label}
    if kind == "days":
        return {"type": kind, "days": [DAY_NAMES[d] for d in c["days"]], "label": label}
    if kind == "scene":
        return {"type": kind, "scene": c["target"], "active": c["active"], "label": label}
    if kind == "person":
        return {"type": kind, "person": c["target"], "home": c["home"], "label": label}
    if kind == "home":
        return {"type": kind, "home": c["occupied"], "label": label}
    return {"type": kind, "dark": c["is"] == "dark", "label": label}


_SET_FIELDS = {"brightness": "brightness", "kelvin": "kelvin", "mode": "mode", "target_temp": "temperature",
               "fan": "fan"}


def action_in(a: dict) -> dict:
    do, label = a["do"], a["label"]
    if do == "wait":
        return {"action": "wait", "minutes": a["seconds"] / 60, "label": label}
    if do == "notify":
        return {"action": "notify", "text": a["text"], "label": label}
    out: dict = {"device": a["target"], "label": label}
    if do == "toggle":
        return {"action": "toggle"} | out
    if do == "run":
        return {"action": "run_automation"} | out
    if do == "set_scene":
        return {"action": "set_scene"} | out
    if do == "press":
        return {"action": "press", "button": a["button"]} | out
    if do == "open_app":
        return {"action": "open_app", "app": a["app"]} | out
    if do == "step":
        kind = "brightness" if a["field"] == "brightness" else "temperature"
        return {"action": f"{kind}_{'up' if a['by'] > 0 else 'down'}", "step": abs(a["by"])} | out
    state = a["state"]
    if set(state) == {"on"}:
        return {"action": "on" if state["on"] else "off"} | out
    fields = {_SET_FIELDS[k]: v for k, v in state.items() if k in _SET_FIELDS}
    if state.get("rgb"):
        fields["color"] = "#{:02x}{:02x}{:02x}".format(*state["rgb"])
    return {"action": "set"} | fields | out


def _when(ts: float) -> str:
    return time.strftime("%a %d %b %H:%M", time.localtime(ts))


def automation_summary(a: dict) -> dict:
    out = {"name": a["name"], "uid": a["uid"], "on": a["enabled"], "summary": a["summary"]}
    if a["next_run"]:
        out["next_run"] = _when(a["next_run"])
    if a["running"]:
        out["running"] = True
    if a["last_run"]:
        out["last_run"] = run_summary(a["last_run"])
    if a["attention"]:
        out["needs_attention"] = a["attention"]
    if a["made_by"] == "assistant":
        out["made_by"] = "assistant"
    return out


def run_summary(run: dict) -> dict:
    out = {"when": _when(run["started"]), "started_by": run["cause"], "outcome": run["outcome"].replace("_", " ")}
    if run["note"]:
        out["note"] = run["note"]
    if run["outcome"] not in ("missed", "skipped"):
        out["actions"] = [
            f"{s['label']}: {s['result'].replace('_', ' ')}" + (f" ({s['detail']})" if s.get("detail") else "")
            for s in run["steps"]
        ]
    return out


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

    def lookup_scene(ref: str) -> dict:
        return find([sc | {"category": "scene"} for sc in engine.call("GET", "/scenes")], ref, "Scene")

    def scene_parts(devices: list[SceneDeviceIn]) -> list[dict]:
        """The parts, with those to keep as they are now read from the Devices."""
        known = home_devices() + engine.call("GET", "/groups")
        parts, now = [], []
        for spec in devices:
            d = controllable(find(known, spec.device))
            state = {"on": spec.on, "brightness": spec.brightness, "kelvin": spec.kelvin, "mode": spec.mode,
                     "target_temp": spec.temperature, "fan": spec.fan, "swing": spec.swing}
            if spec.color is not None:
                state["rgb"] = parse_color(spec.color)
            if spec.app is not None:
                if d["control"] != "streamer":
                    raise ToolError(f"'{d['name']}' isn't a Streamer, so it has no app to open.")
                apps = engine.call("GET", f"/devices/{d['uid']}/state")["features"]["apps"]
                state["app"] = app_package(apps, spec.app)
            state = {k: v for k, v in state.items() if v is not None}
            parts.append({"target": d["uid"], "state": state})
            if spec.as_now or not state:
                now.append(len(parts) - 1)
        if now:
            got = engine.call("POST", "/scenes/capture", {"targets": [parts[i]["target"] for i in now]})
            if got["failed"]:
                raise ToolError("Couldn't keep how these are now: " + "; ".join(got["failed"].values()))
            for i, part in zip(now, got["parts"]):
                parts[i] = part
        return parts

    @server.tool(title="List Scenes", annotations=READ)
    def list_scenes(include_state: bool = False) -> dict:
        """List the Scenes: each one's name and what it sets on each Device. include_state also says
        which are active right now (every Device as the Scene says), which takes a few seconds."""
        found = engine.call("GET", "/scenes")
        active = engine.call("GET", "/scenes/state") if include_state and found else {}
        return {"scenes": [scene_summary(sc, active.get(sc["uid"]) if include_state else None) for sc in found]}

    @server.tool(title="Set a Scene", annotations=SET)
    def set_scene(scene: str) -> dict:
        """Set a Scene: every Device in it goes to how the Scene says, all at once."""
        sc = lookup_scene(scene)
        body = engine.call("POST", f"/scenes/{sc['uid']}/set")
        out: dict = {"set": body["name"]}
        if body["failed"]:
            out["not_answering"] = [f["reason"] for f in body["failed"]]
        return out

    @server.tool(title="Create a Scene", annotations=CREATE)
    def create_scene(name: str, devices: list[SceneDeviceIn]) -> dict:
        """Create a Scene from Devices and Groups (by name or uid) and how each should be. A Device
        given without values (or with as_now) keeps how it is right now, so "save this as Movie night"
        is every Device the user means, with as_now. Only states: power, a light's brightness and
        colour or white, an AC's mode, temperature, fan and swing, a Streamer's app. It isn't set now;
        set_scene does that."""
        sc = engine.call("POST", "/scenes", {"name": name, "parts": scene_parts(devices), "by_assistant": True})
        return scene_summary(sc)

    @server.tool(title="Edit a Scene", annotations=SET)
    def edit_scene(scene: str, name: str | None = None, set_devices: list[SceneDeviceIn] | None = None,
                   remove: list[str] | None = None) -> dict:
        """Rename a Scene, add Devices to it or change how its Devices should be (set_devices, like
        create_scene's devices: a Device already in it is replaced), or remove Devices from it."""
        sc = lookup_scene(scene)
        if name is None and not set_devices and not remove:
            raise ToolError("Say what to change: a new name, Devices to set, or Devices to remove.")
        parts = [{"target": p["target"], "state": p["state"]} for p in sc["parts"]]
        if set_devices:
            new = scene_parts(set_devices)
            changed = {p["target"] for p in new}
            parts = [p for p in parts if p["target"] not in changed] + new
        if remove:
            known = home_devices() + engine.call("GET", "/groups")
            gone = {find(known, ref)["uid"] for ref in remove}
            parts = [p for p in parts if p["target"] not in gone]
        if not parts:
            raise ToolError(f"That would leave '{sc['name']}' empty. Use delete_scene to remove it.")
        body = {"name": name, "parts": parts if set_devices or remove else None}
        sc = engine.call("PATCH", f"/scenes/{sc['uid']}", {k: v for k, v in body.items() if v is not None})
        return scene_summary(sc)

    @server.tool(title="Delete a Scene", annotations=DELETE)
    def delete_scene(scene: str) -> dict:
        """Delete a Scene. Its Devices stay as they are; only the Scene goes."""
        sc = lookup_scene(scene)
        engine.call("DELETE", f"/scenes/{sc['uid']}")
        return {"deleted": sc["name"]}

    @server.tool(title="List Hotkeys", annotations=READ)
    def list_hotkeys() -> dict:
        """List the Hotkeys: keys on this PC that do one thing to a Device or Group, run an Automation or
        set a Scene."""
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
        - run_automation: `device` names an Automation instead, which runs skipping its Conditions
        - set_scene: `device` names a Scene instead, set like set_scene does
        Keys that type text need Ctrl, Alt or Win. The keys then reach only Control.
        The same keys can also have a double press ("Ctrl+Alt+L (double)") and a long press
        ("Ctrl+Alt+L (long)", held half a second); their single press then waits a moment for a
        second press. A sequence ("Ctrl+Alt+L, then 1") takes a second key within 2 seconds, which may
        type text, and the first keys then start only sequences."""
        if action == "run_automation":
            d, action_body = lookup_automation(device), {"do": "run"}
        elif action == "set_scene":
            d, action_body = lookup_scene(device), {"do": "set_scene"}
        else:
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

    # Automations

    def lookup_automation(ref: str) -> dict:
        found = [a | {"category": "automation"} for a in engine.call("GET", "/automations")]
        return find(found, ref, "Automation")

    def automation_body(triggers: list[TriggerIn] | None, conditions: list[ConditionIn] | None,
                        actions: list[ActionIn] | None) -> dict:
        body = {}
        if triggers is not None:
            body["triggers"] = [device_trigger(t) if t.type in DEVICE_TRIGGERS
                                else scene_part(t, "Trigger") if t.type == "scene"
                                else presence_part(t, "Trigger") if t.type in ("person", "home")
                                else pc_trigger(t) if t.type == "pc"
                                else automation_trigger(t) for t in triggers]
        if conditions is not None:
            body["conditions"] = [automation_condition(c) for c in conditions]
        if actions is not None:
            body["actions"] = [automation_action(a) for a in actions]
        return body

    def device_trigger(t: TriggerIn) -> dict:
        if not t.device:
            raise ToolError(f"A {t.type} Trigger says which Device (`device`).")
        d = controllable(lookup(t.device))
        if t.type == "state":
            if t.on is None:
                raise ToolError("A state Trigger says `on`: true (turns on) or false (turns off).")
            return {"type": "state", "target": d["uid"], "on": t.on, "minutes": t.stays_minutes}
        if t.type == "offline":
            if t.offline is None:
                raise ToolError("An offline Trigger says `offline`: true (goes Offline) or false (comes back online).")
            return {"type": "offline", "target": d["uid"], "offline": t.offline}
        if not t.app:
            raise ToolError("Say which app (`app`).")
        if d["control"] != "streamer":
            raise ToolError(f"'{d['name']}' isn't a Streamer, so it opens no apps.")
        apps = engine.call("GET", f"/devices/{d['uid']}/state")["features"]["apps"]
        return {"type": "app", "target": d["uid"], "app": app_package(apps, t.app), "minutes": t.stays_minutes}

    def pc_trigger(t: TriggerIn) -> dict:
        if not t.pc:
            raise ToolError("A pc Trigger says what happens to the PC (`pc`): starts, wakes, unlocks, locks, "
                            "sleeps or shuts_down.")
        return {"type": "pc", "event": t.pc}

    def scene_part(part: TriggerIn | ConditionIn, what: str) -> dict:
        if not part.scene:
            raise ToolError(f"A scene {what} says which Scene (`scene`).")
        out = {"type": "scene", "target": lookup_scene(part.scene)["uid"]}
        return out | ({"active": part.active} if isinstance(part, ConditionIn) else {})

    def presence_part(part: TriggerIn | ConditionIn, what: str) -> dict:
        if part.home is None:
            raise ToolError(f"A {part.type} {what} says `home`: true or false.")
        if part.type == "home":
            return {"type": "home", "occupied": part.home}
        if not part.person:
            raise ToolError(f"A person {what} says who (`person`).")
        found = [p | {"category": "person"} for p in engine.call("GET", "/people")]
        return {"type": "person", "target": find(found, part.person, "Person")["uid"], "home": part.home}

    def automation_condition(c: ConditionIn) -> dict:
        if c.type == "scene":
            return scene_part(c, "Condition")
        if c.type in ("person", "home"):
            return presence_part(c, "Condition")
        if c.type in ("state", "app"):
            if not c.device:
                raise ToolError("A state or app Condition says which Device or Group (`device`).")
            d = controllable(lookup(c.device))
            if c.type == "state":
                if c.on is None:
                    raise ToolError("A state Condition says `on`: true (on) or false (off).")
                return {"type": "state", "target": d["uid"], "on": c.on}
            if not c.app:
                raise ToolError("Say which app (`app`).")
            if d["control"] != "streamer":
                raise ToolError(f"'{d['name']}' isn't a Streamer, so it has no apps open.")
            apps = engine.call("GET", f"/devices/{d['uid']}/state")["features"]["apps"]
            return {"type": "app", "target": d["uid"], "app": app_package(apps, c.app)}
        if c.type == "time":
            return {"type": "time", "after": c.after, "before": c.before}
        if c.type == "days":
            return {"type": "days", "days": day_numbers(c.days)}
        if c.dark is None:
            raise ToolError("A sun Condition says `dark`: true (after sunset, before sunrise) or false (daylight).")
        return {"type": "sun", "is": "dark" if c.dark else "light"}

    def automation_action(a: ActionIn) -> dict:
        if a.action == "wait":
            if not a.minutes:
                raise ToolError("Say how long to wait (`minutes`, e.g. 10 or 0.5).")
            return {"do": "wait", "seconds": round(a.minutes * 60)}
        if a.action == "notify":
            return {"do": "notify", "text": a.text or ""}
        if a.action == "run_automation":
            if not a.device:
                raise ToolError("Say which Automation to run (`device`).")
            return {"do": "run", "target": lookup_automation(a.device)["uid"]}
        if a.action == "set_scene":
            if not a.device:
                raise ToolError("Say which Scene to set (`device`).")
            return {"do": "set_scene", "target": lookup_scene(a.device)["uid"]}
        if not a.device:
            raise ToolError(f"Say which Device or Group to {a.action} (`device`).")
        d = controllable(lookup(a.device))
        body = hotkey_action(d, a.action, a.step, a.button, a.app,
                             {"brightness": a.brightness, "kelvin": a.kelvin, "mode": a.mode,
                              "target_temp": a.temperature, "fan": a.fan, "color": a.color})
        return body | {"target": d["uid"]}

    @server.tool(title="List People", annotations=READ)
    def list_people() -> dict:
        """The people who live here and whether each is home now (home, away, or not known yet: Control
        just started, or hasn't seen their phone), from their phones on the home Wi-Fi."""
        found = engine.call("GET", "/people")
        where = {True: "home", False: "away", None: "not known yet"}
        return {"people": [{"name": p["name"], "uid": p["uid"], "is": where[p["home"]],
                            "phones": [ph["name"] for ph in p["phones"]]} for p in found]}

    @server.tool(title="List Automations", annotations=READ)
    def list_automations() -> dict:
        """List the Automations: each one's name, whether it's on, what it does in plain language,
        when it runs next and how its last Run went."""
        return {"automations": [automation_summary(a) for a in engine.call("GET", "/automations")]}

    @server.tool(title="Get an Automation", annotations=READ)
    def get_automation(automation: str) -> dict:
        """One Automation, by name or uid: each of its Triggers, Conditions and Actions (edit_automation
        replaces a whole list, so keep the ones that stay), and its recent Runs (newest first): what
        started each, how it ended, and what each Action did."""
        a = lookup_automation(automation)
        full = engine.call("GET", f"/automations/{a['uid']}")
        out = automation_summary(full) | {
            "triggers": [trigger_in(t) for t in full["triggers"]],
            "conditions": [condition_in(c) for c in full["conditions"]],
            "match": full["match"],
            "actions": [action_in(x) for x in full["actions"]],
        }
        out["recent_runs"] = [run_summary(run) for run in engine.call("GET", f"/automations/{a['uid']}/runs")[:10]]
        return out

    @server.tool(title="Create an Automation", annotations=CREATE)
    def create_automation(name: str, actions: list[ActionIn], triggers: list[TriggerIn] | None = None,
                          conditions: list[ConditionIn] | None = None, match: Literal["all", "any"] = "all",
                          enabled: bool = True) -> dict:
        """Create an Automation. It's active right away. Triggers (any one starts it; none: it runs
        only by hand): a time ("07:00") on some days; sunrise/sunset with an offset in minutes; a
        Device or Group turning on or off (`state`: `device`, `on`, optionally `stays_minutes` it must
        stay so first); a Streamer opening an app (`app`: `device`, `app`, optionally `stays_minutes`);
        or a Device going Offline or coming back online (`offline`: `device`, `offline`); or a Scene
        being set by anyone, the user or another Automation (`scene`: `scene`).
        Conditions (checked once when a Trigger fires; `match`: all of them, or any one): a Device or
        Group on/off, a Streamer's open app, a Scene active or not (`scene`: `scene`, `active`), a time
        window (may cross midnight), days, dark/light.
        Actions, in order: what a Hotkey can do to a Device or Group (on, off, toggle, set, step,
        press a button, open an app), set a Scene (`set_scene`, `device` naming the Scene), run another
        Automation (`run_automation`: it skips that one's Conditions, and this one goes on without
        waiting for it). They can't start each other in a loop, by running each other or by setting a
        Scene another one starts on. Or wait some minutes, or notify (a Windows notification on this PC and a notice in the app). Tell
        the user the returned `summary`."""
        body = {"name": name, "match": match, "enabled": enabled, "by_assistant": True}
        body |= automation_body(triggers or [], conditions or [], actions)
        return automation_summary(engine.call("POST", "/automations", body))

    @server.tool(title="Edit an Automation", annotations=SET)
    def edit_automation(automation: str, name: str | None = None, triggers: list[TriggerIn] | None = None,
                        conditions: list[ConditionIn] | None = None, actions: list[ActionIn] | None = None,
                        match: Literal["all", "any"] | None = None) -> dict:
        """Change an Automation. Triggers, conditions and actions, when given, replace the whole list
        (get_automation shows the current ones); an empty list of triggers makes it run only by hand."""
        a = lookup_automation(automation)
        body = automation_body(triggers, conditions, actions)
        if name is not None:
            body["name"] = name
        if match is not None:
            body["match"] = match
        if not body:
            raise ToolError("Say what to change.")
        return automation_summary(engine.call("PATCH", f"/automations/{a['uid']}", body))

    @server.tool(title="Switch an Automation on or off", annotations=SET)
    def set_automation_enabled(automation: str, enabled: bool) -> dict:
        """Switch an Automation on (its Triggers start it) or off (it runs only by hand)."""
        a = lookup_automation(automation)
        return automation_summary(engine.call("PATCH", f"/automations/{a['uid']}", {"enabled": enabled}))

    @server.tool(title="Run an Automation", annotations=PRESS)
    def run_automation(automation: str) -> dict:
        """Run an Automation now, skipping its Conditions (the user asked). A Run still going starts
        again. Answers as it starts: get_automation shows how it went."""
        a = lookup_automation(automation)
        run = engine.call("POST", f"/automations/{a['uid']}/run")
        return {"started": a["name"], "actions": [s["label"] for s in run["steps"]]}

    @server.tool(title="Delete an Automation", annotations=DELETE)
    def delete_automation(automation: str) -> dict:
        """Delete an Automation and its history."""
        a = lookup_automation(automation)
        engine.call("DELETE", f"/automations/{a['uid']}")
        return {"deleted": a["name"]}

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
                       "temperature_down", "set", "press", "open_app", "run_automation", "set_scene"]
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
