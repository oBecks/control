"""Hotkeys (ADR 0007): the Engine keeps them and runs their actions; the Desktop App registers their
keys with Windows and calls `/run` when they're pressed, like any other Client.

The Desktop App's listener asks `/watch` for the Hotkeys (it answers when they change) and reports
which keys Windows refused, since another app had them. While the Window records keys, `/recording`
asks it to let go of every Hotkey, so pressing an existing one reaches the Window instead of firing.

Only the computer running Control sets Hotkeys up; phones can't. Device logic stays in `app.py`,
imported lazily: `app.py` includes this router.
"""

import threading
import time
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..engine import groups, hotkeys, remote_buttons, streamer
from ..engine.climate import features_from_signals
from ..engine.registry import Hotkey, Registry
from .deps import registry

router = APIRouter(prefix="/api/hotkeys")

WATCH_SECONDS = 25  # a watch answers after this long even when nothing changed
LISTENER_GONE = 5  # seconds without a watch before the listener counts as gone
RECORDING_SECONDS = 60  # the Window gets the keys back at most this long
LEVEL_CACHE = 2.0  # seconds a stepped value is trusted without reading the Device again


class Listener:
    """The Desktop App's hotkey listener, as the Engine sees it."""

    def __init__(self):
        self._cond = threading.Condition()
        self.revision = 1  # bumped whenever the listener must register again
        self.watching = 0
        self.last_contact = 0.0
        self.reported = 0  # the revision it last registered
        self.taken: set[str] = set()  # Hotkeys whose keys Windows refused
        self.recording_until = 0.0
        self.closing = False  # the Engine is stopping: answer watches now, or they hold up its exit

    def bump(self) -> int:
        with self._cond:
            self.revision += 1
            self._cond.notify_all()
            return self.revision

    @property
    def recording(self) -> bool:
        return time.monotonic() < self.recording_until

    @property
    def alive(self) -> bool:
        return self.watching > 0 or time.monotonic() - self.last_contact < LISTENER_GONE

    def watch(self, revision: int, recording: bool, timeout: float) -> None:
        """Wait until the Hotkeys change, or recording starts or ends."""
        with self._cond:
            self.watching += 1
            self.last_contact = time.monotonic()
        try:
            deadline = time.monotonic() + timeout
            with self._cond:
                while (self.revision == revision and self.recording == recording and not self.closing
                       and (left := deadline - time.monotonic()) > 0):
                    # Changes notify; only recording running out needs a timed wake. Sleeping
                    # otherwise keeps the idle Engine from waking twice a second. Keyed on what the
                    # caller saw, so recording running out just now still ends the wait at once.
                    if recording:
                        left = min(left, self.recording_until - time.monotonic())
                    self._cond.wait(max(left, 0))
        finally:
            with self._cond:
                self.watching -= 1
                self.last_contact = time.monotonic()

    def close(self) -> None:
        with self._cond:
            self.closing = True
            self._cond.notify_all()

    def report(self, revision: int, taken: set[str]) -> None:
        with self._cond:
            self.reported, self.taken = revision, taken
            self.last_contact = time.monotonic()
            self._cond.notify_all()

    def wait_registered(self, revision: int, timeout: float = 2.0) -> None:
        """After a change: give the listener a moment to register, so the answer says whether it worked."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while self.alive and self.reported < revision and (left := deadline - time.monotonic()) > 0:
                self._cond.wait(left)

    def status(self, uid: str) -> str:
        if not self.alive:
            return "off"
        if self.reported < self.revision:
            return "pending"
        return "taken" if uid in self.taken else "active"


listener = Listener()
_levels: dict[tuple[str, str], tuple[float, float]] = {}  # (target, field) -> (value, when)


def _api():
    from . import app

    return app


def _local_only(request: Request) -> None:
    if not request.state.local:
        raise HTTPException(403, "Hotkeys are set up on the computer running Control")


# --- Targets -------------------------------------------------------------------------


class Target(BaseModel):
    uid: str
    name: str
    control: str | None
    is_group: bool
    settable: set[str]
    buttons: dict[str, str]  # name -> label
    apps: list[dict]


_SETTABLE = {
    "light": {"on", "brightness", "rgb", "kelvin"},
    "plug": {"on"},
    "climate": {"on", "mode", "target_temp", "fan", "swing"},
    "streamer": {"on"},
}


def target(r: Registry, uid: str) -> Target:
    """What a Device or Group can do, read from the Registry: nothing is asked of the Device."""
    api = _api()
    if uid.startswith("group:"):
        g = api._group_out(r, r.get_group(uid))
        return Target(uid=uid, name=g.name, control=g.control, is_group=True,
                      settable=groups.SETTABLE[g.control], buttons={}, apps=[])
    out = api._device_out(r, uid)
    buttons: dict[str, str] = {}
    apps: list[dict] = []
    settable = _SETTABLE.get(out.control or "", set())
    if out.control == "remote":
        names = r.resolve_remote(uid).signals["buttons"]
        buttons = {n: remote_buttons.label(n) for n in names}
        settable = {"on"} if {"power_on", "power_off"} <= set(names) else set()
    elif out.control == "streamer":
        buttons = {n: label for n, (label, _) in streamer.BUTTONS.items()}
        apps = streamer.with_links((r.streamer(uid) or {"apps": []})["apps"])
    return Target(uid=uid, name=out.name, control=out.control, is_group=False, settable=settable,
                  buttons=buttons, apps=apps)


def _climate_shared(r: Registry, t: Target) -> dict | None:
    if t.control != "climate":
        return None
    members = r.get_group(t.uid).members if t.is_group else [t.uid]
    return groups.shared_climate([asdict(features_from_signals(r.resolve_remote(m).signals)) for m in members])


def check_action(r: Registry, t: Target, action: dict) -> dict:
    if t.control is None:
        raise ValueError(f"'{t.name}' can't be controlled yet")
    try:
        clean = hotkeys.check_action(action, t.control, t.settable, t.buttons, t.apps, t.is_group)
    except ValueError as exc:
        raise ValueError(f"'{t.name}': {exc}") from None
    if clean["do"] == "set":
        _api().StateIn(**clean["state"])  # ranges, e.g. brightness 1-100
        if shared := _climate_shared(r, t):
            groups.check_climate(shared, clean["state"])
    return clean


def _app_names(t: Target) -> dict[str, str]:
    """Package -> name, for the target's apps and the apps Control knows."""
    return {a["app"]: a["name"] for a in [*streamer.CATALOGUE, *t.apps]}


# --- Views -----------------------------------------------------------------------------


class HotkeyOut(BaseModel):
    uid: str
    keys: str = Field(description='e.g. "Ctrl+Alt+L"')
    target: str = Field(description="the Device's or Group's uid")
    target_name: str
    action: dict
    action_label: str = Field(description='e.g. "Toggle", "Brightness up 10%"')
    repeats: bool = Field(description="holding the keys repeats it")
    made_by: str
    status: str = Field(description="active, taken (by another app), pending, or off (the Desktop App isn't running)")


def _out(r: Registry, hk: Hotkey) -> HotkeyOut:
    try:
        t = target(r, hk.target)
    except LookupError:  # forgetting a target deletes its Hotkeys, so only a race gets here
        t = Target(uid=hk.target, name="(forgotten)", control=None, is_group=False, settable=set(), buttons={}, apps=[])
    label = hotkeys.describe(hk.action, t.buttons, _app_names(t))
    return HotkeyOut(uid=hk.uid, keys=hk.keys, target=hk.target, target_name=t.name, action=hk.action,
                     action_label=label, repeats=hotkeys.repeats(hk.action), made_by=hk.made_by,
                     status=listener.status(hk.uid))


class HotkeysOut(BaseModel):
    hotkeys: list[HotkeyOut]
    listening: bool = Field(description="the Desktop App is running, so Hotkeys work")
    can_change: bool = Field(description="only the computer running Control sets Hotkeys up")
    recording: bool


@router.get("", response_model=HotkeysOut)
def list_hotkeys(request: Request, r: Registry = Depends(registry)):
    return HotkeysOut(hotkeys=[_out(r, hk) for hk in r.hotkeys()], listening=listener.alive,
                      can_change=request.state.local, recording=listener.recording)


@router.get("/keys")
def pickable_keys():
    """Keys to pick from when the Window can't see a key being pressed (e.g. another app has it)."""
    return [{"code": k.code, "label": k.label, "group": k.group, "types": k.types} for k in hotkeys.KEYS]


class CheckIn(BaseModel):
    keys: str
    uid: str | None = Field(None, description="the Hotkey being edited, whose own keys are fine")
    action: dict | None = Field(None, description="what it will do, if known: a long press can't share "
                                                  "keys with a single press that repeats")


def _keys_problem(r: Registry, trigger: hotkeys.Trigger, uid: str | None, repeats: bool = False) -> str | None:
    if p := hotkeys.problem(trigger):
        return p
    others = [hk for hk in r.hotkeys() if hk.uid != uid]
    parsed = [(hotkeys.parse_trigger(hk.keys), hotkeys.repeats(hk.action)) for hk in others]
    if clash := hotkeys.clash(trigger, repeats, parsed):
        same = next((hk for hk, (t, _) in zip(others, parsed, strict=True)
                     if t.label.casefold() == trigger.label.casefold()), None)
        if same:
            other = _out(r, same)
            return f"{trigger.label} is already the Hotkey for {other.target_name} ({other.action_label})"
        return clash[0].upper() + clash[1:]
    from ..desktop import hotkeys as desktop_hotkeys

    # Keys Control registers already (this Hotkey's, or another press of them) are Control's.
    mine = {hotkeys.parse_trigger(hk.keys).keys for hk in r.hotkeys()}
    for keys in (trigger.keys, trigger.then):
        if keys and keys not in mine and desktop_hotkeys.can_register(keys) is False:
            return f"Another app uses {keys.label}"
    return None


@router.post("/check")
def check_keys(body: CheckIn, request: Request, r: Registry = Depends(registry)):
    """Whether keys can be a Hotkey: `problem` says why not, `warning` what they'd take from other apps."""
    _local_only(request)
    try:
        trigger = hotkeys.parse_trigger(body.keys)
    except ValueError as exc:
        return {"keys": body.keys, "problem": str(exc), "warning": None}
    repeats = hotkeys.repeats(body.action or {})
    return {"keys": trigger.label, "problem": _keys_problem(r, trigger, body.uid, repeats),
            "warning": hotkeys.warning(trigger)}


# --- The Desktop App's listener ------------------------------------------------------


@router.get("/watch")
def watch(request: Request, revision: int = 0, recording: bool = False, r: Registry = Depends(registry)):
    """The listener's long poll: answers when the Hotkeys differ from `revision` (or recording
    starts or ends), else after WATCH_SECONDS. While recording, it's told to register nothing."""
    _local_only(request)
    listener.watch(revision, recording, WATCH_SECONDS)
    return {"revision": listener.revision, "recording": listener.recording,
            "keys": [] if listener.recording else _registrations(r)}


def _keys_out(keys: hotkeys.Keys) -> dict:
    return {"vk": keys.key.vk, "mods": keys.mod_flags, "label": keys.label}


def _registrations(r: Registry) -> list[dict]:
    """What the listener registers: one entry per keys, with the Hotkey for each way of pressing
    them (once, double, long) or the sequences they start (`then`, each with its second keys)."""
    entries: dict[hotkeys.Keys, dict] = {}
    for hk in r.hotkeys():
        trigger = hotkeys.parse_trigger(hk.keys)
        out = _out(r, hk)
        about = {"uid": hk.uid, "repeats": out.repeats, "name": out.target_name, "does": out.action_label}
        entry = entries.setdefault(trigger.keys, _keys_out(trigger.keys) | {"then": []})
        if trigger.then:
            entry["then"].append(_keys_out(trigger.then) | {"hotkey": about})
        else:
            entry[trigger.press] = about
    return list(entries.values())


class RegisteredIn(BaseModel):
    revision: int
    taken: list[str] = Field(default_factory=list, description="Hotkeys whose keys Windows refused")


@router.put("/registered", status_code=204)
def registered(body: RegisteredIn, request: Request):
    _local_only(request)
    listener.report(body.revision, set(body.taken))


class RecordingIn(BaseModel):
    on: bool


@router.put("/recording", status_code=204)
def recording(body: RecordingIn, request: Request):
    """The Window is recording keys: the listener lets go of every Hotkey for up to a minute."""
    _local_only(request)
    listener.recording_until = time.monotonic() + RECORDING_SECONDS if body.on else 0.0
    listener.bump()


# --- Setting up ------------------------------------------------------------------------


class HotkeyIn(BaseModel):
    keys: str = Field(description='e.g. "Ctrl+Alt+L", "F13", "Volume Up"')
    target: str = Field(description="a Device's or Group's uid")
    action: dict = Field(description='e.g. {"do": "toggle"}; see engine/hotkeys.py')
    by_assistant: bool = Field(False, description="made by the Assistant, so the app can say so")


def _checked_keys(r: Registry, text: str, uid: str | None, action: dict) -> str:
    trigger = hotkeys.parse_trigger(text)
    if p := _keys_problem(r, trigger, uid, hotkeys.repeats(action)):
        raise ValueError(p)
    return trigger.label


@router.post("", response_model=HotkeyOut, status_code=201)
def add_hotkey(body: HotkeyIn, request: Request, r: Registry = Depends(registry)):
    _local_only(request)
    action = check_action(r, target(r, body.target), body.action)
    keys = _checked_keys(r, body.keys, None, action)
    uid = r.add_hotkey(keys, body.target, action, "assistant" if body.by_assistant else "user")
    listener.wait_registered(listener.bump())
    return _out(r, r.get_hotkey(uid))


class HotkeyPatch(BaseModel):
    keys: str | None = None
    target: str | None = None
    action: dict | None = None


@router.patch("/{uid}", response_model=HotkeyOut)
def patch_hotkey(uid: str, patch: HotkeyPatch, request: Request, r: Registry = Depends(registry)):
    _local_only(request)
    hk = r.get_hotkey(uid)
    action = None
    if patch.target is not None or patch.action is not None:
        # A new target must be able to do the action, old or new.
        action = check_action(r, target(r, patch.target or hk.target), patch.action or hk.action)
    # Checked again even when they stay: a new action may repeat, which a long press on them rules out.
    keys = _checked_keys(r, patch.keys if patch.keys is not None else hk.keys, uid, action or hk.action)
    r.update_hotkey(uid, keys=keys if patch.keys is not None else None, target=patch.target, action=action)
    listener.wait_registered(listener.bump())
    return _out(r, r.get_hotkey(uid))


@router.delete("/{uid}", status_code=204)
def delete_hotkey(uid: str, request: Request, r: Registry = Depends(registry)):
    _local_only(request)
    r.forget_hotkey(uid)
    listener.bump()


# --- Running ---------------------------------------------------------------------------


@router.post("/{uid}/run")
def run_hotkey(uid: str, r: Registry = Depends(registry)):
    """Do a Hotkey's action. Answers what the overlay shows: the target's name, what happened, and
    a level (0-1) for a bar when it changed brightness or temperature."""
    hk = r.get_hotkey(uid)
    t = target(r, hk.target)
    # Checked again: its target may have changed since (a learned button deleted, a Group's members).
    action = check_action(r, t, hk.action)
    reading = run(r, t, action)
    text, level = hotkeys.result_text(
        reading, action,
        press_label=t.buttons.get(action.get("button", "")),
        app_name=_app_names(t).get(action.get("app", "")),
    )
    return {"name": t.name, "text": text, "level": level}


def run(r: Registry, t: Target, action: dict) -> dict:
    """Do an action on a Device or Group; returns its reading afterwards."""
    api = _api()
    g = r.get_group(t.uid) if t.is_group else None

    def change(**desired) -> dict:
        state = api.StateIn(**desired)
        return api._group_state(r, g, state) if g else api._read_state(r, api._device_out(r, t.uid), state)

    def read() -> dict:
        return api._group_state(r, g, None) if g else api._read_state(r, api._device_out(r, t.uid), None)

    do = action["do"]
    if do == "toggle":
        if "on" not in t.settable:  # only a Power Toggle
            return change(press="power")
        return change(on=not read()["state"]["on"])
    if do == "set":
        return change(**action["state"])
    if do == "press":
        return change(press=action["button"])
    if do == "open_app":
        return change(open_app=streamer.find_shortcut(action["app"], t.apps))
    if do == "step":
        return _step(r, t, action, read, change)
    raise ValueError(f"unknown action '{do}'")


def _step(r: Registry, t: Target, action: dict, read, change) -> dict:
    field, by = action["field"], action["by"]
    key = (t.uid, field)
    cached = _levels.get(key)
    if field == "brightness" and not t.is_group:
        return _step_light(r, t, by, cached)
    reading = read()
    s, f = reading["state"], reading["features"]
    if field == "brightness":
        current = s["brightness"] if s["on"] else 0
        if cached and time.monotonic() - cached[1] < LEVEL_CACHE:
            current = cached[0]
        if current == 0 and by < 0:
            return reading  # off stays off
        new = hotkeys.step(current, by, 1, 100)
    else:
        current = cached[0] if cached and time.monotonic() - cached[1] < LEVEL_CACHE else s["target_temp"]
        new = hotkeys.step(current, by, f["min_temp"], f["max_temp"])
    _levels[key] = (new, time.monotonic())
    return change(**{field: new})


def _step_light(r: Registry, t: Target, by: int, cached: tuple[float, float] | None) -> dict:
    """One light, lean: bulbs rate-limit requests, and holding the keys steps several times a second.
    Reads the light only when nothing recent is known, and doesn't read it back."""
    api = _api()
    _, light = api.connect_light(r, t.uid)
    if cached and time.monotonic() - cached[1] < LEVEL_CACHE:
        current = cached[0]
    else:
        s = light.get_state()
        current = s.brightness if s.on else 0
    state = {"on": current > 0, "brightness": int(current or 1), "mode": "white", "rgb": None, "kelvin": None}
    reading = {"control": "light", "features": asdict(light.features), "state": state}
    if current == 0 and by < 0:
        return reading  # off stays off
    new = int(hotkeys.step(current, by, 1, 100))
    if current == 0:
        light.turn_on()
    light.set_brightness(new)
    _levels[(t.uid, "brightness")] = (new, time.monotonic())
    return reading | {"state": state | {"on": True, "brightness": new}}
