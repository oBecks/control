"""Groups: a named set of Devices controlled as one (see CONTEXT.md).

A Group's Device Controls show only what every member supports: all lights → a light's controls
(colour only if every light has colour, the white range they share), all ACs → an AC's controls
(the modes, fans and temperatures they share), anything else → on/off. Its power is "on" while any
member is on, so a tap turns everything off, and otherwise everything on.
"""

from typing import Literal

GroupControl = Literal["light", "climate", "power"]

# Which fields of a desired state each kind of Group accepts.
SETTABLE: dict[str, set[str]] = {
    "light": {"on", "brightness", "rgb", "kelvin"},
    "climate": {"on", "mode", "target_temp", "fan", "swing"},
    "power": {"on"},
}


def control_of(member_controls: list[str | None]) -> GroupControl:
    """The control surface a Group gets from its members' (e.g. ["light", "light"] → "light")."""
    kinds = set(member_controls)
    if kinds == {"light"}:
        return "light"
    if kinds == {"climate"}:
        return "climate"
    return "power"


def category_of(member_categories: list[str]) -> str:
    """The members' Category when they share one (for the Tile's icon), otherwise "mixed"."""
    kinds = set(member_categories)
    return kinds.pop() if len(kinds) == 1 else "mixed"


def power_problem(control: str | None, buttons: dict | None = None) -> str | None:
    """Why a Device can't be a member, or None. `buttons`: a button Remote Device's buttons."""
    if control is None:
        return "can't be controlled yet"
    if control == "remote":
        names = set(buttons or {})
        if {"power_on", "power_off"} <= names:
            return None
        if "power" in names:
            return "only has a Power Toggle, so a Group couldn't be sure to turn it off"
        return "has no On and Off buttons"
    return None


def is_on(reading: dict) -> bool:
    # A remote's power can be None (not set by Control yet): it isn't claimed to be on.
    return bool(reading["state"].get("on"))


def merge(control: GroupControl, readings: list[dict]) -> dict:
    """One Group reading from its members' readings (those that answered), in member order."""
    if not readings:
        raise ValueError("no member answered")
    lead = next((m for m in readings if is_on(m)), readings[0])  # its colour/mode stands for the Group
    on = any(is_on(m) for m in readings)
    assumed = any(m.get("assumed") for m in readings)
    if control == "light":
        features = _light_features([m["features"] for m in readings])
        return {"control": "light", "features": features, "state": {**lead["state"], "on": on}, "assumed": assumed}
    if control == "climate":
        features = _climate_features([m["features"] for m in readings])
        if features is not None:
            return {"control": "climate", "features": features, "state": {**lead["state"], "on": on}, "assumed": True}
    return {"control": "power", "features": {}, "state": {"on": on}, "assumed": assumed}


def _light_features(all_features: list[dict]) -> dict:
    lo = max(f["min_kelvin"] for f in all_features)
    hi = min(f["max_kelvin"] for f in all_features)
    color_temp = all(f["color_temp"] for f in all_features) and lo < hi
    return {
        "color": all(f["color"] for f in all_features),
        "color_temp": color_temp,
        "min_kelvin": lo if color_temp else 0,
        "max_kelvin": hi if color_temp else 0,
    }


def _shared(lists: list[list[str]]) -> list[str]:
    """Values in every list, in the first one's order."""
    return [v for v in lists[0] if all(v in other for other in lists[1:])]


def _climate_features(all_features: list[dict]) -> dict | None:
    """What every AC accepts; None when they share no mode or temperature (the Group is on/off only)."""
    modes = _shared([f["modes"] for f in all_features])
    lo = max(f["min_temp"] for f in all_features)
    hi = min(f["max_temp"] for f in all_features)
    if not modes or lo > hi:
        return None
    return {
        "modes": modes,
        # An AC without fan speeds (or swing) ignores them, so only those that have them count.
        "fan_modes": _shared([f["fan_modes"] for f in all_features if f["fan_modes"]] or [[]]),
        "swing_modes": _shared([f["swing_modes"] for f in all_features if f["swing_modes"]] or [[]]),
        "min_temp": lo,
        "max_temp": hi,
        "step": max(f["step"] for f in all_features),
    }
