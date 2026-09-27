"""Scenes (see CONTEXT.md, ADR 0013): a named end state for several Devices, set in one tap.

A Scene is a list of parts, one per Device or Group: {"target": uid, "state": {...}}. A part's state
holds only what the user chose: "on", and while on, a light's "brightness" and "rgb" or "kelvin", an
AC's "mode", "target_temp", "fan" and "swing", or a Streamer's "app" (a package). Setting any of
those also turns the Device on, like Device Controls do. No button presses: they aren't states.

A Scene is active while every part matches its Device's reading (an Assumed State counts; a Device
that doesn't answer doesn't match). Nothing remembers which Scene was set last.
"""

from .streamer import app_name

# The icons a Scene's chip can have (the UI draws each one).
ICONS = ("sparkles", "clapperboard", "sun", "moon", "sofa", "utensils", "bed", "briefcase", "book", "coffee",
         "party", "leaf")
FIELDS = ("on", "brightness", "rgb", "kelvin", "mode", "target_temp", "fan", "swing", "app")
NOTHING_TO_SET = "has nothing a Scene can set: it needs separate On and Off, since a Power Toggle isn't a state"
MAX_PARTS = 50
NAME_MAX = 40

# Readings are compared with a little slack: some brands round what they're sent (Tuya's 0-1000
# scales, colours through HSV).
BRIGHTNESS_SLACK = 1
RGB_SLACK = 6
KELVIN_SLACK = 50


def settable(control: str | None, target_settable: set[str]) -> set[str]:
    """What a part may set on a target: its settable StateIn fields (a Hotkey's), plus a Streamer's app."""
    return target_settable | ({"app"} if control == "streamer" else set())


def check_state(state: dict, allowed: set[str]) -> dict:
    """A part's state cleaned up, or ValueError saying why it can't be a Scene's."""
    clean = {k: v for k, v in (state or {}).items() if v is not None}
    if unknown := set(clean) - set(FIELDS):
        raise ValueError(f"a Scene can't set {', '.join(sorted(unknown))}")
    if not clean:
        raise ValueError("say what it should be")
    if not allowed:
        raise ValueError(NOTHING_TO_SET)
    if extra := set(clean) - allowed:
        raise ValueError(f"can't be set: {', '.join(sorted(extra))}")
    if clean.get("on") is False and len(clean) > 1:
        raise ValueError("is off in this Scene, so there's nothing else to set")
    if "rgb" in clean and "kelvin" in clean:
        raise ValueError("gets either a colour or a white, not both")
    if "rgb" in clean:
        clean["rgb"] = list(clean["rgb"])
    return clean


def desired(state: dict, open_app: str | None = None) -> dict:
    """What to send for a part (StateIn fields). `open_app`: what opens its app (a link or the package)."""
    body = {k: v for k, v in state.items() if k != "app"}
    if "app" in state:
        body["open_app"] = open_app or state["app"]
    return body


def capture(reading: dict, allowed: set[str], apps: list[dict] | None = None) -> dict:
    """A part's state from how a Device or Group is now: what a Scene "from how things are now" sets.
    `apps`: a Streamer's App Shortcuts; only an app among them is kept, since it's one Control can open."""
    s, control = reading["state"], reading["control"]
    if "on" not in allowed:
        raise ValueError(NOTHING_TO_SET)
    if s.get("on") is None:
        raise ValueError("isn't known to be on or off yet: turn it on or off from Control first")
    if not s["on"]:
        return {"on": False}
    out: dict = {"on": True}
    if control == "light":
        out["brightness"] = s["brightness"]
        if s.get("mode") == "color" and s.get("rgb") and "rgb" in allowed and reading["features"].get("color"):
            out["rgb"] = list(s["rgb"])
        elif s.get("mode") == "white" and s.get("kelvin") and reading["features"].get("color_temp"):
            out["kelvin"] = s["kelvin"]
    elif control == "climate":
        out |= {k: s[k] for k in ("mode", "target_temp", "fan", "swing") if s.get(k) is not None and k in allowed}
    elif control == "streamer" and s.get("app") in {a["app"] for a in apps or []}:
        out["app"] = s["app"]
    return out


def matches(state: dict, reading: dict) -> bool:
    """Whether one Device's reading is as the part's state says."""
    s = reading["state"]
    want_on = state.get("on", True)  # setting anything else turns it on
    if s.get("on") is None or bool(s["on"]) != want_on:
        return False
    if not want_on:
        return True
    for key, value in state.items():
        if key == "on":
            continue
        if key == "brightness":
            if s.get("brightness") is None or abs(s["brightness"] - value) > BRIGHTNESS_SLACK:
                return False
        elif key == "rgb":
            if s.get("mode") != "color" or not s.get("rgb") or max(abs(a - b) for a, b in zip(s["rgb"], value)) > RGB_SLACK:
                return False
        elif key == "kelvin":
            if s.get("mode") != "white" or s.get("kelvin") is None or abs(s["kelvin"] - value) > KELVIN_SLACK:
                return False
        elif key == "target_temp":
            if s.get("target_temp") is None or abs(s["target_temp"] - value) > 0.01:
                return False
        elif s.get(key) != value:  # mode, fan, swing, app
            return False
    return True


def describe(state: dict, apps: list[dict] | None = None) -> str:
    """A part in words, e.g. "On · 20% · 2700 K" or "Netflix"."""
    if state.get("on") is False:
        return "Off"
    words = []
    if "brightness" in state:
        words.append(f"{state['brightness']}%")
    if "rgb" in state:
        words.append("#{:02x}{:02x}{:02x}".format(*state["rgb"]))
    if "kelvin" in state:
        words.append(f"{state['kelvin']} K")
    if "mode" in state:
        words.append(str(state["mode"]).capitalize())
    if "target_temp" in state:
        words.append(f"{state['target_temp']:g}°")
    if "fan" in state:
        words.append(f"fan {state['fan']}")
    if "swing" in state:
        words.append(f"swing {state['swing']}")
    if "app" in state:
        words.append(app_name(state["app"], apps or []) or state["app"])
    if set(state) - {"on"} == {"app"}:
        return words[0]  # opening the app says it's on
    return " · ".join(["On", *words])


def without(parts: list[dict], gone: set[str]) -> list[dict]:
    """The parts left once these targets are forgotten."""
    return [p for p in parts if p["target"] not in gone]
