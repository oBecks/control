"""The Engine's local HTTP API. Every Client (desktop window, web UI, MCP server) goes through
it, and none of them hold device logic.

It also serves the built web UI. Listens on 127.0.0.1, and on the LAN only while Phone access is on;
`access.gate` decides who may use it (ADR 0003).
"""

import base64
import mimetypes
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..engine import code_set_finder, groups, remote_buttons, signal_library
from ..engine.connect import (
    connect_buttons,
    connect_climate,
    connect_light,
    connect_plug,
    connect_transmitter,
    control_kind,
    only_transmitter,
)
from ..engine.climate import features_from_signals
from ..engine.errors import DeviceUnreachable
from ..engine.found_device import Category
from ..engine.links import tuya_link
from ..engine.registry import Group, KnownDevice, Registry, RemoteDevice
from ..engine.scan import DEFAULT_TIMEOUT, scan_and_remember
from . import access, assistant, desktop
from .deps import registry

app = FastAPI(title="Control Engine", version=__version__)
app.middleware("http")(access.gate)
app.include_router(access.router)
app.include_router(desktop.router)
app.include_router(assistant.router)


@app.exception_handler(LookupError)
def _not_found(_: Request, exc: LookupError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValueError)
def _invalid(_: Request, exc: ValueError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(DeviceUnreachable)
def _unreachable(_: Request, exc: DeviceUnreachable):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


# --- Device views ----------------------------------------------------------


class DeviceOut(BaseModel):
    uid: str
    name: str
    category: Category
    kind: Literal["network", "remote"]
    control: Literal["light", "plug", "climate", "remote"] | None = Field(
        description="which control surface to show; null if the app can't control it yet"
    )
    brand: str
    model: str
    ip: str | None
    readiness: str
    online: bool
    is_new: bool
    note: str = Field("", description="setup hint, e.g. how to unlock a device")
    source: str | None = Field(None, description="remote devices: where the Signals came from")
    via: str | None = Field(None, description="remote devices: uid of the Hub that sends their Signals")
    group_problem: str | None = Field(
        None, description="why it can't join a Group (e.g. only a Power Toggle); null if it can"
    )


def _network_out(r: Registry, d: KnownDevice) -> DeviceOut:
    control = control_kind(r, d)
    return DeviceOut(
        uid=d.uid, name=d.name, category=d.category, kind="network", control=control,
        brand=d.brand, model=d.model, ip=d.ip, readiness=d.readiness.value, online=d.online, is_new=d.is_new,
        note=d.note, group_problem=groups.power_problem(control),
    )


def _remote_control(d: RemoteDevice) -> str | None:
    if d.signals.get("format") == "buttons":
        return "remote" if d.signals["buttons"] else None  # nothing to press until a button is learned
    return "climate"


def _remote_out(d: RemoteDevice) -> DeviceOut:
    control = _remote_control(d)
    return DeviceOut(
        uid=d.uid, name=d.name, category=d.category, kind="remote", control=control,
        brand="", model="", ip=None, readiness="ready", online=True, is_new=False, source=d.source,
        via=d.transmitter_uid, group_problem=groups.power_problem(control, d.signals.get("buttons")),
    )


def _device_out(r: Registry, uid: str) -> DeviceOut:
    if uid.startswith("remote:"):
        return _remote_out(r.resolve_remote(uid))
    d = r.get(uid)
    if d is None:
        raise LookupError(f"no device '{uid}'")
    return _network_out(r, d)


@app.get("/api/devices", response_model=list[DeviceOut])
def list_devices(r: Registry = Depends(registry)):
    return [_network_out(r, d) for d in r.all()] + [_remote_out(d) for d in r.remotes()]


@app.post("/api/devices/seen", status_code=204)
def mark_all_seen(r: Registry = Depends(registry)):
    """Clear every New flag (the user has looked at Add Devices)."""
    r.mark_seen()


@app.get("/api/devices/{uid}", response_model=DeviceOut)
def get_device(uid: str, r: Registry = Depends(registry)):
    return _device_out(r, uid)


class DevicePatch(BaseModel):
    name: str | None = Field(None, description="empty string resets to the brand's name")
    seen: bool | None = Field(None, description="true clears the New flag")


@app.patch("/api/devices/{uid}", response_model=DeviceOut)
def patch_device(uid: str, patch: DevicePatch, r: Registry = Depends(registry)):
    out = _device_out(r, uid)  # 404s early
    if patch.name is not None:
        if out.kind == "remote":
            if not patch.name:
                raise ValueError("remote devices need a name")
            r.rename_remote(uid, patch.name)
        else:
            r.rename(uid, patch.name)
    if patch.seen and out.kind == "network":
        r.mark_seen([uid])
    return _device_out(r, uid)


@app.delete("/api/devices/{uid}", status_code=204)
def forget_device(uid: str, r: Registry = Depends(registry)):
    _device_out(r, uid)
    (r.forget_remote if uid.startswith("remote:") else r.forget)(uid)


# --- Scan ------------------------------------------------------------------


class ScanOut(BaseModel):
    added: list[str]
    moved: dict[str, tuple[str, str]]
    missing: list[str]
    errors: dict[str, str]
    devices: list[DeviceOut]


@app.post("/api/scan", response_model=ScanOut)
def scan(timeout: float = DEFAULT_TIMEOUT, r: Registry = Depends(registry)):
    result, report = scan_and_remember(r, timeout)
    return ScanOut(
        added=report.added, moved=report.moved, missing=report.missing, errors=result.errors,
        devices=list_devices(r),
    )


# --- Live state & control --------------------------------------------------


class StateIn(BaseModel):
    """Desired state; send only what should change. Which fields apply depends on `control`.
    Changing any setting also turns the device on, like a physical remote."""

    on: bool | None = None
    brightness: int | None = Field(None, ge=1, le=100, description="light")
    rgb: tuple[int, int, int] | None = Field(None, description="light")
    kelvin: int | None = Field(None, description="light")
    mode: str | None = Field(None, description="climate")
    target_temp: float | None = Field(None, description="climate")
    fan: str | None = Field(None, description="climate")
    swing: str | None = Field(None, description="climate")
    press: str | None = Field(None, description="remote: name of a button to press")


def _read_state(r: Registry, out: DeviceOut, desired: StateIn | None) -> dict:
    if out.control == "light":
        _, light = connect_light(r, out.uid)
        if desired:
            _apply_light(light, desired)
        return {"control": "light", "features": asdict(light.features), "state": asdict(light.get_state())}
    if out.control == "plug":
        _, plug = connect_plug(r, out.uid)
        if desired and desired.on is not None:
            plug.turn_on() if desired.on else plug.turn_off()
        return {"control": "plug", "features": {}, "state": asdict(plug.get_state())}
    if out.control == "climate":
        remote, ac = connect_climate(r, out.uid)
        if desired:
            ac.apply(on=desired.on, mode=desired.mode, target_temp=desired.target_temp,
                     fan=desired.fan, swing=desired.swing)
            r.set_assumed_state(remote.uid, ac.state_dict())
        return {"control": "climate", "features": asdict(ac.features), "state": ac.state_dict(), "assumed": True}
    if out.control == "remote":
        remote, pad = connect_buttons(r, out.uid)
        if desired:
            if desired.press:
                pad.press(desired.press)
            elif desired.on is not None:
                pad.set_power(desired.on)
            if pad.on is not None:
                r.set_assumed_state(remote.uid, {"on": pad.on})
        # on is null for a Power Toggle: the app never claims whether it's on.
        return {"control": "remote", "features": asdict(pad.features), "state": {"on": pad.on}, "assumed": True}
    raise LookupError(f"'{out.name}' can't be controlled yet")


def _apply_light(light, s: StateIn) -> None:
    if s.on is False:
        light.turn_off()
        return
    if s.on or any(v is not None for v in (s.brightness, s.rgb, s.kelvin)):
        light.turn_on()
    if s.brightness is not None:
        light.set_brightness(s.brightness)
    if s.rgb is not None:
        light.set_rgb(*s.rgb)
    if s.kelvin is not None:
        light.set_kelvin(s.kelvin)


@app.get("/api/devices/{uid}/state")
def get_state(uid: str, r: Registry = Depends(registry)):
    """Live state read from the device (for remote devices: the Assumed State)."""
    return _read_state(r, _device_out(r, uid), None)


@app.post("/api/devices/{uid}/state")
def set_state(uid: str, desired: StateIn, r: Registry = Depends(registry)):
    return _read_state(r, _device_out(r, uid), desired)


# --- Groups ----------------------------------------------------------------


class GroupOut(BaseModel):
    uid: str
    name: str
    members: list[str] = Field(description="Device uids, in the order the user picked them")
    control: Literal["light", "climate", "power"] = Field(
        description="light or climate when every member is one; otherwise on/off only"
    )
    category: str = Field(description="the members' Category when they share one, otherwise mixed")
    made_by: Literal["user", "assistant"]


def _climate_features(r: Registry, uids: list[str]) -> list[dict]:
    """Each AC's features, from its Signals: no need to reach the ACs."""
    return [asdict(features_from_signals(r.resolve_remote(uid).signals)) for uid in uids]


def _group_out(r: Registry, g: Group) -> GroupOut:
    members = [_device_out(r, uid) for uid in g.members]
    controls = [m.control for m in members]
    climate = _climate_features(r, g.members) if set(controls) == {"climate"} else None
    return GroupOut(
        uid=g.uid, name=g.name, members=g.members, made_by=g.made_by,
        control=groups.control_of(controls, climate),
        category=groups.category_of([m.category.value for m in members]),
    )


def _check_group(r: Registry, name: str | None, members: list[str] | None) -> None:
    if name is not None:
        if not name:
            raise ValueError("give the group a name")
        if any(d.name.casefold() == name.casefold() for d in list_devices(r)):
            raise ValueError(f"a device is already called '{name}'; give the group another name")
    if members is not None:
        if not members:
            raise ValueError("pick at least one device for the group")
        for m in members:
            out = _device_out(r, m)  # 404s for an unknown Device
            if out.group_problem:
                raise ValueError(f"'{out.name}' {out.group_problem}")


@app.get("/api/groups", response_model=list[GroupOut])
def list_groups(r: Registry = Depends(registry)):
    return [_group_out(r, g) for g in r.groups()]


class GroupIn(BaseModel):
    name: str
    members: list[str] = Field(description="Device uids")
    by_assistant: bool = Field(False, description="made by the Assistant, so the app can say so")


@app.post("/api/groups", response_model=GroupOut, status_code=201)
def add_group(body: GroupIn, r: Registry = Depends(registry)):
    name = body.name.strip()
    _check_group(r, name, body.members)
    uid = r.add_group(name, body.members, "assistant" if body.by_assistant else "user")
    return _group_out(r, r.get_group(uid))


@app.get("/api/groups/{uid}", response_model=GroupOut)
def get_group(uid: str, r: Registry = Depends(registry)):
    return _group_out(r, r.get_group(uid))


class GroupPatch(BaseModel):
    name: str | None = None
    members: list[str] | None = Field(None, description="the full new list of Device uids")


@app.patch("/api/groups/{uid}", response_model=GroupOut)
def patch_group(uid: str, patch: GroupPatch, r: Registry = Depends(registry)):
    r.get_group(uid)  # 404s early
    name = patch.name.strip() if patch.name is not None else None
    _check_group(r, name, patch.members)
    r.update_group(uid, name=name, members=patch.members)
    return _group_out(r, r.get_group(uid))


@app.delete("/api/groups/{uid}", status_code=204)
def forget_group(uid: str, r: Registry = Depends(registry)):
    r.forget_group(uid)


def _member_reading(r: Registry, uid: str, desired: StateIn | None) -> dict:
    # Members are read side by side, each on its own thread and so with its own connection.
    with closing(Registry(r.path)) as own:
        return _read_state(own, _device_out(own, uid), desired)


def _group_state(r: Registry, g: Group, desired: StateIn | None) -> dict:
    """Read (or change) every member at once and merge their readings. Members that didn't answer,
    or refused the change, are listed under `failed`; only when all of them fail is it an error."""
    out = _group_out(r, g)
    members = {uid: _device_out(r, uid) for uid in g.members}
    failed: dict[str, dict] = {
        uid: {"reason": f"{m.name} {m.group_problem}", "unreachable": False}
        for uid, m in members.items() if m.group_problem
    }
    live = [uid for uid in g.members if uid not in failed]

    def one(uid: str) -> tuple[str, dict | None, Exception | None]:
        try:
            return uid, _member_reading(r, uid, desired), None
        except Exception as exc:  # one member failing, however it fails, mustn't stop the others
            return uid, None, exc

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(one, live))
    readings = {uid: reading for uid, reading, _ in results if reading is not None}
    errors = [exc for _, _, exc in results if exc is not None]
    for uid, _, exc in results:
        if exc is not None:
            failed[uid] = {"reason": f"{members[uid].name}: {exc}", "unreachable": isinstance(exc, DeviceUnreachable)}
    if not readings:
        # Nobody answered: the same error a single Device would give.
        if errors:
            raise next((e for e in errors if not isinstance(e, DeviceUnreachable)), errors[0])
        raise ValueError(f"no device in '{g.name}' can be controlled")
    merged = groups.merge(out.control, [readings[uid] for uid in g.members if uid in readings])
    return merged | {
        "on_count": sum(groups.is_on(m) for m in readings.values()),
        "total": len(g.members),
        "members": readings,
        "failed": failed,
    }


@app.get("/api/groups/{uid}/state")
def get_group_state(uid: str, r: Registry = Depends(registry)):
    """Every member's state, merged into one, plus each member's own reading under `members`."""
    return _group_state(r, r.get_group(uid), None)


@app.post("/api/groups/{uid}/state")
def set_group_state(uid: str, desired: StateIn, r: Registry = Depends(registry)):
    """Send the same change to every member (e.g. {"on": false} turns them all off)."""
    g = r.get_group(uid)
    control = _group_out(r, g).control
    asked = {k for k, v in desired.model_dump().items() if v is not None}
    if not asked:
        raise ValueError("say what to change")
    if extra := asked - groups.SETTABLE[control]:
        what = {"light": "lights", "climate": "ACs", "power": "devices"}[control]
        raise ValueError(f"'{g.name}' groups {what}, which can't all take {', '.join(sorted(extra))}")
    if control == "climate":
        # Checked for all ACs first, so a value one of them lacks never changes only the others.
        groups.check_climate(groups.shared_climate(_climate_features(r, g.members)), desired.model_dump())
    return _group_state(r, g, desired)


# --- Remote Devices & Signal Library ---------------------------------------


@app.get("/api/signal-library/{domain}")
def search_code_sets(domain: str, brand: str):
    """domain: climate | media_player | fan"""
    return [asdict(s) for s in signal_library.search(domain, brand)]


class RemoteIn(BaseModel):
    name: str
    code_set: int
    via: str | None = Field(None, description="transmitter uid; default: the only one")
    probe_temp: int | None = Field(
        None, description="if this code set was found by a probe: the temperature it sent, so the Assumed State matches"
    )


@app.post("/api/remote-devices", response_model=DeviceOut, status_code=201)
def add_remote(body: RemoteIn, r: Registry = Depends(registry)):
    if not body.name.strip():
        raise ValueError("give the device a name")
    via = r.resolve(body.via) if body.via else only_transmitter(r)
    signals = signal_library.load_climate(body.code_set)
    uid = r.add_remote(body.name.strip(), Category.CLIMATE, via.uid, f"smartir:climate:{body.code_set}", signals)
    if body.probe_temp is not None:
        r.set_assumed_state(uid, asdict(code_set_finder.probe_state(signals, body.probe_temp)))
    return _device_out(r, uid)


class ProbeIn(BaseModel):
    code_sets: list[int] = Field(min_length=1, max_length=15)
    via: str | None = None


@app.post("/api/remote-devices/probe")
def probe_code_sets(body: ProbeIn, r: Registry = Depends(registry)):
    """Code Set Finder: send "on" from each code set with its own temperature. The temperature the AC
    then shows identifies the working code set. Codes in `skipped` need another round."""
    via = r.resolve(body.via) if body.via else only_transmitter(r)
    _, transmitter = connect_transmitter(r, via.uid)
    sets = {c: signal_library.load_climate(c) for c in body.code_sets}
    assignment, skipped = code_set_finder.plan(sets)
    code_set_finder.run(transmitter, sets, assignment)
    return {"assignment": {str(c): t for c, t in assignment.items()}, "skipped": skipped}


class TestIn(BaseModel):
    code_set: int
    temp: int
    via: str | None = None


@app.post("/api/remote-devices/test")
def test_code_set(body: TestIn, r: Registry = Depends(registry)):
    """Send one code set's "on" at `temp`, to confirm a Code Set Finder answer."""
    via = r.resolve(body.via) if body.via else only_transmitter(r)
    _, transmitter = connect_transmitter(r, via.uid)
    signals = signal_library.load_climate(body.code_set)
    code_set_finder.run(transmitter, {body.code_set: signals}, {body.code_set: body.temp})
    return {"sent": True}


class CodeSetIn(BaseModel):
    code_set: int


@app.put("/api/remote-devices/{uid}/code-set", response_model=DeviceOut)
def switch_code_set(uid: str, body: CodeSetIn, r: Registry = Depends(registry)):
    remote = r.resolve_remote(uid)
    r.set_remote_signals(remote.uid, f"smartir:climate:{body.code_set}", signal_library.load_climate(body.code_set))
    return _device_out(r, uid)


# --- Button Remote Devices (TVs, fans, other) & Learning ---------------------


class ButtonRemoteIn(BaseModel):
    name: str
    kind: Literal["tv", "fan", "other"]
    via: str | None = Field(None, description="transmitter uid; default: the only one")
    code_set: int | None = Field(None, description="start from a Signal Library code set instead of empty")


@app.post("/api/remote-devices/buttons", response_model=DeviceOut, status_code=201)
def add_button_remote(body: ButtonRemoteIn, r: Registry = Depends(registry)):
    if not body.name.strip():
        raise ValueError("give the device a name")
    via = r.resolve(body.via) if body.via else only_transmitter(r)
    if body.code_set is not None:
        domain = "media_player" if body.kind == "tv" else "fan"
        signals = remote_buttons.from_code_set(domain, signal_library.load(domain, body.code_set))
        source = f"smartir:{domain}:{body.code_set}"
    else:
        signals, source = remote_buttons.empty(body.kind), "learned"
    uid = r.add_remote(body.name.strip(), remote_buttons.CATEGORY[body.kind], via.uid, source, signals)
    return _device_out(r, uid)


@app.get("/api/remote-devices/suggested-buttons/{kind}")
def suggested_buttons(kind: Literal["tv", "fan", "other"]):
    """The buttons Learning asks for, in order (each can be skipped)."""
    return [{"name": n, "label": l} for n, l in remote_buttons.SUGGESTED[kind]]


class SignalIn(BaseModel):
    signal: str = Field(description="base64")


@app.put("/api/remote-devices/{uid}/buttons/{button}", response_model=DeviceOut)
def save_button(uid: str, button: str, body: SignalIn, r: Registry = Depends(registry)):
    base64.b64decode(body.signal + "=" * (-len(body.signal) % 4), validate=True)
    r.set_remote_button(uid, button, body.signal)
    return _device_out(r, uid)


@app.delete("/api/remote-devices/{uid}/buttons/{button}", response_model=DeviceOut)
def delete_button(uid: str, button: str, r: Registry = Depends(registry)):
    r.set_remote_button(uid, button, None)
    return _device_out(r, uid)


@app.post("/api/hubs/{uid}/learn")
def learn(uid: str, timeout: float = 20, r: Registry = Depends(registry)):
    """Learning: blocks until a button is pressed on a remote pointed at the Hub, or `timeout`."""
    _, transmitter = connect_transmitter(r, uid)
    signal = transmitter.learn(min(timeout, 30))
    if signal is None:
        raise HTTPException(408, "No signal received. Point the remote at the Broadlink and press the button.")
    return {"signal": base64.b64encode(signal).decode()}


@app.post("/api/hubs/{uid}/send")
def send_signal(uid: str, body: SignalIn, r: Registry = Depends(registry)):
    """Send a raw Signal, e.g. to test a just-learned button before saving it."""
    _, transmitter = connect_transmitter(r, uid)
    transmitter.send(base64.b64decode(body.signal + "=" * (-len(body.signal) % 4)))
    return {"sent": True}


class TryButtonIn(BaseModel):
    domain: Literal["media_player", "fan"]
    code_set: int
    button: str | None = Field(None, description="default: the most visible button (TV Off/Power, a fan speed…)")
    via: str | None = None


# Tried in order: the most visible reaction first, so the user can tell whether the code set matches.
# TVs: the user turns the TV on first, so a matching Off (or Power) switches it off.
_TRY_ORDER = {
    "media_player": ["power_off", "power", "power_on", "mute", "volume_up"],
    "fan": ["speed:", "oscillate", "power_off"],
}


@app.post("/api/signal-library/try-button")
def try_library_button(body: TryButtonIn, r: Registry = Depends(registry)):
    """Press one button from a library code set, to check whether it matches the device."""
    via = r.resolve(body.via) if body.via else only_transmitter(r)
    _, transmitter = connect_transmitter(r, via.uid)
    buttons = remote_buttons.from_code_set(body.domain, signal_library.load(body.domain, body.code_set))["buttons"]
    name = body.button or next(
        (b for pref in _TRY_ORDER[body.domain] for b in buttons if b == pref or (pref.endswith(":") and b.startswith(pref))),
        None,
    )
    if name is None or name not in buttons:
        raise ValueError(f"code set {body.code_set} has no usable test signal")
    sig = buttons[name]
    transmitter.send(base64.b64decode(sig + "=" * (-len(sig) % 4)))
    return {"sent": True, "button": name, "label": remote_buttons.label(name)}


# --- Tuya Link -------------------------------------------------------------

# token -> user code, for logins in progress (memory only; a restart just means scanning again).
_pending_tuya: dict[str, str] = {}


class TuyaStartIn(BaseModel):
    user_code: str


@app.post("/api/links/tuya")
def tuya_start(body: TuyaStartIn):
    try:
        token, qr_content = tuya_link.start(body.user_code)
    except tuya_link.LinkError as exc:
        raise HTTPException(422, str(exc))
    _pending_tuya[token] = body.user_code
    return {"token": token, "qr_content": qr_content}


@app.get("/api/links/tuya/{token}")
def tuya_poll(token: str, r: Registry = Depends(registry)):
    """Poll until status is "linked". The Client renders `qr_content` as a QR code meanwhile."""
    user_code = _pending_tuya.get(token)
    if user_code is None:
        raise LookupError("unknown or finished login; start again")
    info = tuya_link.check_login(token, user_code)
    if info is None:
        return {"status": "pending"}
    linked = tuya_link.fetch_devices(info, user_code)
    for d in linked:
        r.save_link(d.uid, d.name, d.category, {"local_key": d.local_key},
                    {"tuya_category": d.tuya_category, "product_name": d.product_name, **d.extra})
    del _pending_tuya[token]
    return {"status": "linked", "devices": [{"uid": d.uid, "name": d.name, "category": d.category} for d in linked]}


# --- Web UI ------------------------------------------------------------------

# `npm run build` in web/ writes here. Every path that isn't a file gets the SPA shell.
UI_DIR = Path(os.environ.get("CONTROL_UI_DIR") or Path(__file__).resolve().parents[3] / "web" / "build")

# Windows' registry can map .js to text/plain, which browsers refuse to run as a module.
for _type, _ext in (("text/javascript", ".js"), ("text/css", ".css"), ("application/manifest+json", ".webmanifest")):
    mimetypes.add_type(_type, _ext)


@app.get("/{path:path}", include_in_schema=False)
def web_ui(path: str):
    if path == "api" or path.startswith("api/"):
        raise LookupError(f"no API route '/{path}'")
    root = UI_DIR.resolve()
    file = (root / path).resolve()
    if path and file.is_file() and file.is_relative_to(root):
        immutable = path.startswith("_app/immutable/")
        return FileResponse(file, headers={"cache-control": "public, max-age=31536000, immutable"} if immutable else None)
    if Path(path).suffix:
        raise LookupError(f"no file '/{path}'")  # a missing file, not a page of the app
    index = root / "index.html"
    if not index.is_file():
        return HTMLResponse("<p>The web UI isn't built yet. Run <code>npm run build</code> in <code>web/</code>.</p>", 503)
    return FileResponse(index, headers={"cache-control": "no-cache"})
