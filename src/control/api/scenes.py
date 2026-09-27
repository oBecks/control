"""Scenes (ADR 0013): a named end state for several Devices, set in one tap.

Each part is checked like a Hotkey's "set" action on its Device or Group, so a Scene takes exactly
what Device Controls can set. Setting a Scene sends every part at once; the parts that fail are
listed, and never stop the others.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..engine import scenes, streamer
from ..engine.errors import DeviceUnreachable
from ..engine.registry import Registry, Scene
from . import hotkeys as hotkeys_api
from .deps import registry

router = APIRouter(prefix="/api/scenes")


def _api():
    from . import app

    return app


class PartIO(BaseModel):
    target: str = Field(description="a Device's or Group's uid")
    state: dict = Field(description='what it should be, e.g. {"on": true, "brightness": 20, "kelvin": 2700}, '
                                    '{"on": false}, {"mode": "cool", "target_temp": 24} or {"app": "com.netflix.ninja"}')


class PartOut(PartIO):
    target_name: str
    label: str = Field(description='the state in words, e.g. "On · 20% · 2700 K"')


class SceneOut(BaseModel):
    uid: str
    name: str
    icon: str
    parts: list[PartOut]
    attention: str | None = Field(description="why it needs looking at, e.g. nothing is left in it")
    made_by: str


def _target(r: Registry, uid: str) -> hotkeys_api.Target:
    if uid.startswith(("automation:", "scene:")):
        raise ValueError("a Scene holds Devices and Groups")
    return hotkeys_api.target(r, uid)


def _out(r: Registry, sc: Scene) -> SceneOut:
    parts = []
    for p in sc.parts:
        try:
            t = _target(r, p["target"])
            name, apps = t.name, t.apps
        except LookupError:  # forgetting a target trims its part, so only a race gets here
            name, apps = "(forgotten)", []
        parts.append(PartOut(target=p["target"], state=p["state"], target_name=name,
                             label=scenes.describe(p["state"], apps)))
    return SceneOut(uid=sc.uid, name=sc.name, icon=sc.icon, parts=parts, attention=sc.attention, made_by=sc.made_by)


def _name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("give the Scene a name")
    if len(name) > scenes.NAME_MAX:
        raise ValueError(f"keep the name under {scenes.NAME_MAX} characters")
    return name


def _icon(icon: str) -> str:
    if icon not in scenes.ICONS:
        raise ValueError(f"the icon is one of: {', '.join(scenes.ICONS)}")
    return icon


def _check_part(r: Registry, target: str, state: dict) -> dict:
    t = _target(r, target)
    if t.control is None:
        raise ValueError(f"'{t.name}' can't be controlled yet")
    try:
        clean = scenes.check_state(state, scenes.settable(t.control, t.settable))
    except ValueError as exc:
        raise ValueError(f"'{t.name}' {exc}") from None
    rest = {k: v for k, v in clean.items() if k != "app"}
    if rest:
        hotkeys_api.check_action(r, t, {"do": "set", "state": rest})  # ranges, an AC's modes
    return clean


def _parts(r: Registry, parts: list[PartIO]) -> list[dict]:
    if not parts:
        raise ValueError("pick at least one device for the Scene")
    if len(parts) > scenes.MAX_PARTS:
        raise ValueError(f"a Scene holds up to {scenes.MAX_PARTS} devices")
    uids = [p.target for p in parts]
    if len(set(uids)) != len(uids):
        raise ValueError("each device is in a Scene once")
    for g in r.groups():
        if g.uid in uids and (inside := [m for m in g.members if m in uids]):
            name = hotkeys_api.target(r, inside[0]).name
            raise ValueError(f"'{name}' is also in '{g.name}' in this Scene: keep one of them")
    return [{"target": p.target, "state": _check_part(r, p.target, p.state)} for p in parts]


@router.get("", response_model=list[SceneOut])
def list_scenes(r: Registry = Depends(registry)):
    return [_out(r, sc) for sc in r.scenes()]


class SceneIn(BaseModel):
    name: str
    icon: str = "sparkles"
    parts: list[PartIO]
    by_assistant: bool = Field(False, description="made by the Assistant, so the app can say so")


@router.post("", response_model=SceneOut, status_code=201)
def add_scene(body: SceneIn, r: Registry = Depends(registry)):
    uid = r.add_scene(_name(body.name), _parts(r, body.parts), _icon(body.icon),
                      "assistant" if body.by_assistant else "user")
    return _out(r, r.get_scene(uid))


class CaptureIn(BaseModel):
    targets: list[str] = Field(description="Device and Group uids")


class CaptureOut(BaseModel):
    parts: list[PartIO]
    failed: dict[str, str] = Field(description="uid -> why its state couldn't be read or kept")


@router.post("/capture", response_model=CaptureOut)
def capture(body: CaptureIn, r: Registry = Depends(registry)):
    """Each Device's or Group's state as it is now, as a Scene's part ("from how things are now").
    Nothing is saved."""
    targets = list(dict.fromkeys(body.targets))
    readings = _read(r, targets)
    parts, failed = [], {}
    for uid in targets:
        t = _target(r, uid)
        reading = readings[uid]
        try:
            if isinstance(reading, Exception):
                raise reading
            state = scenes.capture(reading, scenes.settable(t.control, t.settable), t.apps)
            parts.append(PartIO(target=uid, state=_check_part(r, uid, state)))
        except (ValueError, LookupError, DeviceUnreachable) as exc:
            failed[uid] = f"{t.name}: {exc}"
    return CaptureOut(parts=parts, failed=failed)


class OrderIn(BaseModel):
    uids: list[str]


@router.put("/order", status_code=204)
def order_scenes(body: OrderIn, r: Registry = Depends(registry)):
    r.order_scenes(body.uids)


class ActiveOut(BaseModel):
    active: bool
    parts: list[bool] = Field(description="whether each part matches, in order")


@router.get("/state", response_model=dict[str, ActiveOut])
def scenes_state(r: Registry = Depends(registry)):
    """Which Scenes are active: every part matches its Device (an Assumed State counts; a Device that
    doesn't answer doesn't match). Reads each Device once, so it takes a moment."""
    all_scenes = r.scenes()
    readings = _read(r, list(dict.fromkeys(p["target"] for sc in all_scenes for p in sc.parts)))
    out = {}
    for sc in all_scenes:
        matched = [_matches(p["state"], readings[p["target"]]) for p in sc.parts]
        out[sc.uid] = ActiveOut(active=bool(matched) and all(matched), parts=matched)
    return out


@router.get("/{uid}", response_model=SceneOut)
def get_scene(uid: str, r: Registry = Depends(registry)):
    return _out(r, r.get_scene(uid))


class ScenePatch(BaseModel):
    name: str | None = None
    icon: str | None = None
    parts: list[PartIO] | None = Field(None, description="the full new list")


@router.patch("/{uid}", response_model=SceneOut)
def patch_scene(uid: str, patch: ScenePatch, r: Registry = Depends(registry)):
    r.get_scene(uid)  # 404s early
    r.update_scene(
        uid,
        name=_name(patch.name) if patch.name is not None else None,
        icon=_icon(patch.icon) if patch.icon is not None else None,
        parts=_parts(r, patch.parts) if patch.parts is not None else None,
    )
    return _out(r, r.get_scene(uid))


@router.delete("/{uid}", status_code=204)
def forget_scene(uid: str, r: Registry = Depends(registry)):
    r.forget_scene(uid)


class Failure(BaseModel):
    target: str
    reason: str
    unreachable: bool


class SetOut(BaseModel):
    name: str
    failed: list[Failure] = Field(description="the parts (or a Group's members) that didn't take it")
    readings: dict[str, dict] = Field(description="each Device's or Group's reading afterwards, by uid")


@router.post("/{uid}/set", response_model=SetOut)
def set_scene(uid: str, r: Registry = Depends(registry)):
    """Send every part at once. Parts that fail are listed; the others are set anyway."""
    sc = r.get_scene(uid)
    if not sc.parts:
        raise ValueError(f"nothing is left in '{sc.name}': add devices to it first")

    def one(part: dict) -> tuple[dict, dict | Exception]:
        try:
            with closing(Registry(r.path)) as own:  # each on its own thread, so its own connection
                return part, _send(own, part)
        except Exception as exc:  # one part failing, however it fails, mustn't stop the others
            return part, exc

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(one, sc.parts))
    failed, readings = [], {}
    for part, result in results:
        uid_ = part["target"]
        if isinstance(result, Exception):
            name = _name_of(r, uid_)
            failed.append(Failure(target=uid_, reason=f"{name}: {result}",
                                  unreachable=isinstance(result, DeviceUnreachable)))
            continue
        readings[uid_] = result
        for member, f in (result.get("failed") or {}).items():  # a Group's members
            failed.append(Failure(target=member, reason=f["reason"], unreachable=f["unreachable"]))
    return SetOut(name=sc.name, failed=failed, readings=readings)


def _send(r: Registry, part: dict) -> dict:
    api = _api()
    t = _target(r, part["target"])
    state = _check_part(r, t.uid, part["state"])  # again: the target may have changed since
    open_app = streamer.find_shortcut(state["app"], t.apps) if "app" in state else None
    desired = api.StateIn(**scenes.desired(state, open_app))
    if t.is_group:
        return api._group_state(r, r.get_group(t.uid), desired)
    return api._read_state(r, api._device_out(r, t.uid), desired)


def _name_of(r: Registry, uid: str) -> str:
    try:
        return hotkeys_api.target(r, uid).name
    except LookupError:
        return uid


def _read(r: Registry, uids: list[str]) -> dict[str, dict | Exception]:
    """Each Device's or Group's reading, side by side (an Exception for one that failed)."""
    api = _api()

    def one(uid: str) -> tuple[str, dict | Exception]:
        try:
            with closing(Registry(r.path)) as own:
                if uid.startswith("group:"):
                    return uid, api._group_state(own, own.get_group(uid), None)
                return uid, api._read_state(own, api._device_out(own, uid), None)
        except Exception as exc:
            return uid, exc

    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(pool.map(one, uids))


def _matches(state: dict, reading: dict | Exception) -> bool:
    """A Device's reading, or every member of a Group's (one that didn't answer doesn't match)."""
    if isinstance(reading, Exception):
        return False
    if "members" in reading:
        return not reading["failed"] and all(scenes.matches(state, m) for m in reading["members"].values())
    return scenes.matches(state, reading)
