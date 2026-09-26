"""Hotkeys (see CONTEXT.md, ADR 0007): keys on the PC that do one thing to one Device or Group.

Keys are written as text, e.g. "Ctrl+Alt+L", "F13" or "Volume Up": modifiers first, then one key.
A Trigger adds how they're pressed: "Ctrl+Alt+L (double)", "Ctrl+Alt+L (long)", or a sequence,
"Ctrl+Alt+L, then 1" (the second keys may type text: they're Control's only for a moment).
The key is also accepted by its physical name as browsers report it (`KeyboardEvent.code`, e.g.
"KeyL"), so the Window can record keys whatever the keyboard layout. Each key maps to a Windows
virtual-key code for `RegisterHotKey`; letters and digits use the same codes in every layout
Control cares about (English, Hebrew), so a Hotkey keeps working when the layout changes.

An action is one of:
    {"do": "toggle"}
    {"do": "set", "state": {...}}              any StateIn fields, e.g. {"on": true}, {"brightness": 30}
    {"do": "step", "field": "brightness" | "target_temp", "by": 10}   negative steps down
    {"do": "press", "button": "volume_up"}     a remote's or a Streamer's button
    {"do": "open_app", "app": "com.netflix.ninja"}   a Streamer's app, by package
Holding the keys repeats steps and presses; the others fire once.
"""

import re
from dataclasses import dataclass

# Modifiers, in the order they're written, with RegisterHotKey's flags.
MODIFIERS: dict[str, int] = {"Ctrl": 0x0002, "Alt": 0x0001, "Shift": 0x0004, "Win": 0x0008}
MOD_NOREPEAT = 0x4000
_MOD_ALIASES = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win", "windows": "Win",
                "meta": "Win", "super": "Win", "cmd": "Win"}


@dataclass(frozen=True)
class Key:
    code: str  # KeyboardEvent.code
    vk: int  # Windows virtual-key code
    label: str
    group: str  # for the "pick the key" list: spare, media, function, letters, numpad, other
    types: bool = False  # a key that types text: needs Ctrl, Alt or Win


def _keys() -> list[Key]:
    keys = [Key(f"F{n}", 0x7B + n - 12, f"F{n}", "spare" if n > 12 else "function") for n in range(13, 25)]
    keys += [Key(f"F{n}", 0x6F + n, f"F{n}", "function") for n in range(1, 13)]
    keys += [
        Key("AudioVolumeMute", 0xAD, "Mute", "media"),
        Key("AudioVolumeDown", 0xAE, "Volume Down", "media"),
        Key("AudioVolumeUp", 0xAF, "Volume Up", "media"),
        Key("MediaPlayPause", 0xB3, "Play/Pause", "media"),
        Key("MediaTrackNext", 0xB0, "Next Track", "media"),
        Key("MediaTrackPrevious", 0xB1, "Previous Track", "media"),
        Key("MediaStop", 0xB2, "Stop", "media"),
        Key("LaunchMail", 0xB4, "Mail", "media"),
        Key("LaunchMediaPlayer", 0xB5, "Media", "media"),
        Key("LaunchApp1", 0xB6, "App 1", "media"),
        Key("LaunchApp2", 0xB7, "App 2", "media"),
        Key("BrowserHome", 0xAC, "Browser Home", "media"),
        Key("BrowserSearch", 0xAA, "Browser Search", "media"),
        Key("BrowserFavorites", 0xAB, "Favorites", "media"),
        Key("BrowserBack", 0xA6, "Browser Back", "media"),
        Key("BrowserForward", 0xA7, "Browser Forward", "media"),
        Key("BrowserRefresh", 0xA8, "Browser Refresh", "media"),
        Key("BrowserStop", 0xA9, "Browser Stop", "media"),
        Key("Pause", 0x13, "Pause", "spare"),
        Key("ScrollLock", 0x91, "Scroll Lock", "spare"),
    ]
    keys += [Key(f"Key{c}", ord(c), c, "letters", types=True) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
    keys += [Key(f"Digit{n}", 0x30 + n, str(n), "letters", types=True) for n in range(10)]
    keys += [Key(f"Numpad{n}", 0x60 + n, f"Num {n}", "numpad", types=True) for n in range(10)]
    keys += [
        Key("NumpadMultiply", 0x6A, "Num *", "numpad", types=True),
        Key("NumpadAdd", 0x6B, "Num Plus", "numpad", types=True),
        Key("NumpadSubtract", 0x6D, "Num Minus", "numpad", types=True),
        Key("NumpadDecimal", 0x6E, "Num .", "numpad", types=True),
        Key("NumpadDivide", 0x6F, "Num /", "numpad", types=True),
        Key("Space", 0x20, "Space", "other", types=True),
        Key("Enter", 0x0D, "Enter", "other", types=True),
        Key("Tab", 0x09, "Tab", "other", types=True),
        Key("Escape", 0x1B, "Esc", "other", types=True),
        Key("Backspace", 0x08, "Backspace", "other", types=True),
        Key("Insert", 0x2D, "Insert", "other", types=True),
        Key("Delete", 0x2E, "Delete", "other", types=True),
        Key("Home", 0x24, "Home", "other", types=True),
        Key("End", 0x23, "End", "other", types=True),
        Key("PageUp", 0x21, "Page Up", "other", types=True),
        Key("PageDown", 0x22, "Page Down", "other", types=True),
        Key("ArrowUp", 0x26, "Up", "other", types=True),
        Key("ArrowDown", 0x28, "Down", "other", types=True),
        Key("ArrowLeft", 0x25, "Left", "other", types=True),
        Key("ArrowRight", 0x27, "Right", "other", types=True),
        Key("ContextMenu", 0x5D, "Menu", "other", types=True),
        Key("PrintScreen", 0x2C, "Print Screen", "other", types=True),
        Key("Minus", 0xBD, "-", "other", types=True),
        Key("Equal", 0xBB, "=", "other", types=True),
        Key("BracketLeft", 0xDB, "[", "other", types=True),
        Key("BracketRight", 0xDD, "]", "other", types=True),
        Key("Backslash", 0xDC, "\\", "other", types=True),
        Key("Semicolon", 0xBA, ";", "other", types=True),
        Key("Quote", 0xDE, "'", "other", types=True),
        Key("Comma", 0xBC, ",", "other", types=True),
        Key("Period", 0xBE, ".", "other", types=True),
        Key("Slash", 0xBF, "/", "other", types=True),
        Key("Backquote", 0xC0, "`", "other", types=True),
    ]
    return keys


KEYS: list[Key] = _keys()
_BY_NAME: dict[str, Key] = {k.code.casefold(): k for k in KEYS} | {k.label.casefold(): k for k in KEYS}
_BY_NAME |= {"esc": _BY_NAME["esc"], "return": _BY_NAME["enter"],
             "volume mute": _BY_NAME["mute"], "play pause": _BY_NAME["play/pause"], "playpause": _BY_NAME["play/pause"]}


@dataclass(frozen=True)
class Keys:
    mods: tuple[str, ...]  # in MODIFIERS order
    key: Key

    @property
    def label(self) -> str:
        return "+".join([*self.mods, self.key.label])

    @property
    def mod_flags(self) -> int:
        flags = 0
        for m in self.mods:
            flags |= MODIFIERS[m]
        return flags


def parse(text: str) -> Keys:
    """"Ctrl+Alt+L", "ctrl + alt + KeyL", "F13", "Volume Up" → Keys. Raises ValueError."""
    parts = [p.strip() for p in text.split("+")]
    if not text.strip() or any(not p for p in parts):
        raise ValueError(f"'{text}' isn't a key; write it like Ctrl+Alt+L or F13")
    *mod_names, key_name = parts
    mods = set()
    for m in mod_names:
        mod = _MOD_ALIASES.get(m.casefold())
        if mod is None:
            raise ValueError(f"'{m}' isn't Ctrl, Alt, Shift or Win")
        mods.add(mod)
    if key_name.casefold() in _MOD_ALIASES:
        raise ValueError("add a key after the modifiers, e.g. Ctrl+Alt+L")
    key = _BY_NAME.get(key_name.casefold())
    if key is None:
        raise ValueError(f"Control doesn't know the key '{key_name}'")
    return Keys(tuple(m for m in MODIFIERS if m in mods), key)


# How keys are pressed. A double press waits DOUBLE_WITHIN after the first release for the second;
# a long press fires once the keys are held LONG_AFTER. A sequence's second keys are Control's for
# SEQUENCE_SECONDS after the first.
PRESSES = ("once", "double", "long")
DOUBLE_WITHIN = 0.4
LONG_AFTER = 0.5
SEQUENCE_SECONDS = 2.0
_PRESS_WORDS = {"double": "double", "twice": "double", "x2": "double", "×2": "double", "long": "long", "hold": "long"}
_PRESS_SUFFIX = re.compile(r"\s*\(?\s*(double|twice|x2|×2|long|hold)(?:[\s-]*press)?\s*\)?\s*$", re.IGNORECASE)
_THEN = re.compile(r",\s+(?:then\s+)?|\s+then\s+", re.IGNORECASE)  # "Ctrl+," keeps its comma


@dataclass(frozen=True)
class Trigger:
    """A Hotkey's keys and how they're pressed."""

    keys: Keys  # the only keys, or a sequence's first
    press: str = "once"  # once, double or long
    then: Keys | None = None  # a sequence's second keys

    @property
    def label(self) -> str:
        if self.then:
            return f"{self.keys.label}, then {self.then.label}"
        return self.keys.label if self.press == "once" else f"{self.keys.label} ({self.press})"


def parse_trigger(text: str) -> Trigger:
    """"Ctrl+Alt+L", "Ctrl+Alt+L double", "ctrl+alt+l (long press)", "Ctrl+Alt+L, then 1",
    "Ctrl+Alt+L then 1" → Trigger. Raises ValueError."""
    parts = _THEN.split(text.strip())
    if len(parts) > 2:
        raise ValueError("a sequence is two keys, e.g. Ctrl+Alt+L, then 1")
    if len(parts) == 2:
        if _PRESS_SUFFIX.search(parts[0]) or _PRESS_SUFFIX.search(parts[1]):
            raise ValueError("a sequence's keys are pressed once each")
        return Trigger(parse(parts[0]), "once", parse(parts[1]))
    press = "once"
    if m := _PRESS_SUFFIX.search(text):
        press = _PRESS_WORDS[m.group(1).casefold()]
        text = text[: m.start()]
    return Trigger(parse(text), press)


def problem(trigger: Trigger | Keys) -> str | None:
    """Why these keys can't be a Hotkey, or None."""
    keys = trigger.keys if isinstance(trigger, Trigger) else trigger
    if keys.key.types and not {"Ctrl", "Alt", "Win"} & set(keys.mods):
        return f"{keys.label} is used for typing: add Ctrl, Alt or Win"
    if isinstance(trigger, Trigger) and trigger.then:
        if trigger.then.key.code == "Escape" and not trigger.then.mods:
            return "Esc cancels a sequence: pick another second key"
        if trigger.then == trigger.keys:
            return "a sequence's second keys must differ from its first"
    return None


def warning(trigger: Trigger | Keys) -> str | None:
    """What the user gives up with these keys: they reach only Control (ADR 0007)."""
    keys = trigger.keys if isinstance(trigger, Trigger) else trigger
    if isinstance(trigger, Trigger) and trigger.then and not trigger.then.mods:
        return f"For {SEQUENCE_SECONDS:g} s after {keys.label}, {trigger.then.label} reaches only Control."
    if keys.mods:
        return None
    if keys.key.group == "media":
        return f"While this Hotkey exists, {keys.label} works only for Control, not for Windows or other apps."
    if keys.key.group == "function":
        return f"Apps won't get {keys.label} while this Hotkey exists."
    return None


def clash(trigger: Trigger, repeats: bool, others: list[tuple[Trigger, bool]]) -> str | None:
    """Why this Trigger can't sit beside the other Hotkeys' (each with whether its action repeats),
    or None. The same keys can have a single, a double and a long press, but a sequence's first keys
    start only sequences, and a long press can't share keys with a single press that repeats."""
    for other, other_repeats in others:
        if other.label.casefold() == trigger.label.casefold():
            return f"{trigger.label} is already a Hotkey"
        if trigger.then:
            if not other.then and other.keys == trigger.keys:
                return f"{trigger.keys.label} is a Hotkey of its own, so it can't start a sequence"
            if not other.then and other.keys == trigger.then:
                return f"{trigger.then.label} is a Hotkey of its own, so it can't end a sequence"
            # Keys that start sequences are always registered, so they can't be another's second key.
            if other.then and other.keys == trigger.then:
                return f"{trigger.then.label} starts sequences ({other.label}), so it can't end one"
            if other.then and other.then == trigger.keys:
                return f"{trigger.keys.label} ends a sequence ({other.label}), so it can't start one"
            continue
        if other.then and other.keys == trigger.keys:
            return f"{trigger.keys.label} starts sequences ({other.label}), so it can't be a Hotkey of its own"
        if other.then and other.then == trigger.keys:
            return f"{trigger.keys.label} ends a sequence ({other.label}), so it can't be a Hotkey of its own"
        if other.keys == trigger.keys and {trigger.press, other.press} == {"once", "long"}:
            if (repeats if trigger.press == "once" else other_repeats):
                return (f"holding {trigger.keys.label} already repeats its single press, "
                        "so it can't also have a long press")
    return None


# --- Actions -----------------------------------------------------------------------

STEP_FIELDS = {"brightness": "light", "target_temp": "climate"}
DEFAULT_STEP = {"brightness": 10, "target_temp": 1}
REPEATS = {"step", "press"}  # held keys repeat these; the rest fire once


def repeats(action: dict) -> bool:
    return action.get("do") in REPEATS


def check_action(action: dict, control: str | None, settable: set[str], buttons: dict[str, str],
                 apps: list[dict], is_group: bool) -> dict:
    """The action cleaned up, or ValueError saying why the target can't do it.
    `settable`: the StateIn fields the target takes; `buttons`: its buttons (name → label)."""
    do = action.get("do")
    if do == "toggle":
        if "on" not in settable and "power" not in buttons:
            raise ValueError("it has no power to toggle")
        return {"do": "toggle"}
    if do == "set":
        state = {k: v for k, v in (action.get("state") or {}).items() if v is not None}
        if not state:
            raise ValueError("say what to set")
        if extra := set(state) - settable:
            raise ValueError(f"it can't be set: {', '.join(sorted(extra))}")
        return {"do": "set", "state": state}
    if do == "step":
        field = action.get("field")
        if field not in STEP_FIELDS:
            raise ValueError("a step changes brightness or target_temp")
        if field not in settable:
            what = "a light" if field == "brightness" else "an AC"
            raise ValueError(f"only {what} steps its {'brightness' if field == 'brightness' else 'temperature'}")
        by = action.get("by", DEFAULT_STEP[field])
        if isinstance(by, int | float) and field == "brightness":
            by = round(by)  # whole percents
        if not isinstance(by, int | float) or isinstance(by, bool) or by == 0 or abs(by) > (50 if field == "brightness" else 5):
            raise ValueError("step by a small amount, e.g. 10 (%) or 1 (°); negative steps down")
        return {"do": "step", "field": field, "by": int(by) if field == "brightness" else by}
    if do == "press":
        if is_group:
            raise ValueError("a Group has no buttons")
        button = action.get("button")
        if button not in buttons:
            listed = ", ".join(buttons.values()) or "none"
            raise ValueError(f"it has no '{button}' button (its buttons: {listed})")
        return {"do": "press", "button": button}
    if do == "open_app":
        if control != "streamer":
            raise ValueError("only a Streamer opens apps")
        app = action.get("app")
        if not isinstance(app, str) or not app:
            raise ValueError("say which app")
        return {"do": "open_app", "app": app}
    raise ValueError("the action is toggle, set, step, press or open_app")


def describe(action: dict, buttons: dict[str, str], app_names: dict[str, str]) -> str:
    """What the action does, e.g. "Toggle", "Brightness up 10%", "Press Volume +", "Open Netflix"."""
    do = action["do"]
    if do == "toggle":
        return "Toggle"
    if do == "step":
        by, field = action["by"], action["field"]
        direction = "up" if by > 0 else "down"
        if field == "brightness":
            return f"Brightness {direction} {abs(by)}%"
        return f"Temperature {direction} {abs(by):g}°"
    if do == "press":
        return f"Press {buttons.get(action['button'], action['button'])}"
    if do == "open_app":
        return f"Open {app_names.get(action['app'], action['app'])}"
    state = action["state"]
    parts = []
    if state.get("on") is not None and len(state) == 1:
        return "Turn on" if state["on"] else "Turn off"
    for k, v in state.items():
        if k == "on":
            continue
        if k == "brightness":
            parts.append(f"brightness {v}%")
        elif k == "rgb":
            parts.append("colour #{:02x}{:02x}{:02x}".format(*v))
        elif k == "kelvin":
            parts.append(f"white {v}K")
        elif k == "target_temp":
            parts.append(f"{v:g}°")
        elif k == "mode":
            parts.append(str(v))
        else:
            parts.append(f"{k} {v}")
    text = "Set " + ", ".join(parts)
    return text + " (turns it off)" if state.get("on") is False else text


def step(current: float, by: float, low: float, high: float) -> float:
    return min(high, max(low, current + by))


def result_text(reading: dict, action: dict, press_label: str | None = None, app_name: str | None = None) -> tuple[str, float | None]:
    """What the overlay says after an action, and the level (0-1) to show as a bar, if any."""
    s = reading["state"]
    do = action["do"]
    if do == "press":
        return press_label or action["button"], None
    if do == "open_app":
        return app_name or "App opened", None
    control = reading["control"]
    on = s.get("on")
    if control == "light" and on:
        return f"Brightness {s['brightness']}%", s["brightness"] / 100
    if control == "climate" and on:
        f = reading["features"]
        span = f["max_temp"] - f["min_temp"]
        level = (s["target_temp"] - f["min_temp"]) / span if span else None
        return f"{s['mode'].capitalize()} {s['target_temp']:g}°", level
    if on is None:
        return "Power pressed", None
    return ("On" if on else "Off"), None
