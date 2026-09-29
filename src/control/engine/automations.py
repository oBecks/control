"""Automations (see CONTEXT.md, ADR 0006, 0011, 0012): When (Triggers) → Only if (Conditions) → Then
(Actions). The Engine runs them; this module holds their shape, checks and plain-language labels,
and the time arithmetic. Running them, and anything that reaches a Device, is in `api/automations.py`.

Times are the PC's local time, "HH:MM". Days are weekday numbers, Monday 0 to Sunday 6; a Trigger or
Condition without `days` means every day.

A Trigger is one of:
    {"type": "time", "at": "07:00", "days": [0, 1, 2, 3, 4]}
    {"type": "sun", "event": "sunrise" | "sunset", "offset": -30, "days": [...]}   offset in minutes
    {"type": "state", "target": uid, "on": true, "minutes": 30}   turns on (a Group: its first member),
                                                  and stays on for 30 min first; 0: at once
    {"type": "app", "target": uid, "app": "com.netflix.ninja", "minutes": 5}   a Streamer opens that
                                                  app, and keeps it open 5 min first; 0: at once
    {"type": "offline", "target": uid, "offline": true}   a Device goes Offline (false: comes back online)
    {"type": "scene", "target": "scene:…"}       a Scene is set, by anyone: the app, a Hotkey, the
                                                  Assistant or an Automation (ADR 0013)
    {"type": "person", "target": "person:…", "home": true}   a Person arrives home (false: leaves)
    {"type": "home", "occupied": true}           the first person arrives home (false: the last leaves)
    {"type": "pc", "event": "wakes"}             something happens to this PC (PC_EVENTS, ADR 0015)
    {"type": "web", "token": "…"}                its web link is opened (ADR 0016); the Engine makes the
                                                  secret `token`, at most one per Automation
State, app and offline are Device Triggers: the Engine listens to the Devices they name (ADR 0011,
`api/listening.py`). Person and home are Presence Triggers (ADR 0014, `api/people.py`). A PC Trigger
fires when Control starts, or when the Desktop App hears Windows say the PC woke, went to sleep, was
locked or unlocked, or is shutting down (`api/automations.py`, `desktop/events.py`).

A Condition is one of:
    {"type": "state", "target": uid, "on": true}          a Device or Group is on (a Group: any member)
    {"type": "app", "target": uid, "app": "com.netflix.ninja"}   a Streamer has that app open
    {"type": "time", "after": "22:00", "before": "06:00"}  may cross midnight
    {"type": "days", "days": [5, 6]}
    {"type": "sun", "is": "dark" | "light"}               dark: between sunset and sunrise
    {"type": "scene", "target": "scene:…", "active": true}   a Scene is active (false: isn't)
    {"type": "person", "target": "person:…", "home": true}   a Person is home (false: away)
    {"type": "home", "occupied": true}                   someone is home (false: nobody is)
Conditions are checked once, when a Trigger fires: all of them, or any one (`match`).

An Action is one of:
    {"do": "toggle" | "set" | "step" | "press" | "open_app", "target": uid, ...}   a Hotkey's action
        a toggle, set or step on one Device may add "undo": {"after": 10} (put it back to how it was
        after 10 min) or {"while": true} (put it back once the Only if stops holding), ADR 0017
    {"do": "run", "target": "automation:…"}   another Automation's Run (chaining): it skips that one's
                                              Only if, and this Run goes on without waiting for it
    {"do": "set_scene", "target": "scene:…"}  a Scene, every part at once; it sets off the Automations
                                              whose Trigger is that Scene
    {"do": "wait", "seconds": 600}
    {"do": "notify", "text": "The AC is off"}
An Automation never starts itself, even through others (`loop`), by running them or by setting a
Scene that is their Trigger; the loop guard stops the rest.
"""

import datetime as dt
import re
from collections.abc import Iterator

from . import hotkeys, sun

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
EVERY_DAY = list(range(7))
TRIGGERS = ("time", "sun", "state", "app", "offline", "scene", "person", "home", "pc", "web")
DEVICE_TRIGGERS = ("state", "app", "offline")
PRESENCE = ("person", "home")  # Presence Triggers and Conditions (ADR 0014)
CONDITIONS = ("state", "app", "time", "days", "sun", "scene", "person", "home")
PC_EVENTS = {
    "starts": "Control starts",
    "wakes": "The PC wakes from sleep",
    "unlocks": "You unlock the PC or sign in",
    "locks": "The PC is locked",
    "sleeps": "The PC goes to sleep",
    "shuts_down": "The PC shuts down or you sign out",
}
CONTROL = ("toggle", "set", "step", "press", "open_app")
UNDOABLE = ("toggle", "set", "step")  # the Actions that can be put back: they change a state
MAX_UNDO = 24 * 60  # minutes an Action can ask to be put back after
MAX_WAIT = 24 * 3600
MAX_STAYS = 24 * 60  # minutes a state Trigger can ask it to stay so
MAX_OFFSET = 180  # minutes before or after sunrise or sunset
MAX_TEXT = 200
MAX_PARTS = 30  # Triggers, Conditions or Actions in one Automation
OUTCOMES = ("running", "succeeded", "partly_failed", "skipped", "missed", "interrupted", "restarted")

_HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def parse_time(text) -> dt.time:
    m = _HHMM.match(str(text).strip()) if text is not None else None
    if not m:
        raise ValueError(f"'{text}' isn't a time; write it like 07:30 or 22:00")
    return dt.time(int(m[1]), int(m[2]))


def _hhmm(t: dt.time) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def _days(value) -> list[int]:
    if value is None:
        return EVERY_DAY
    if not isinstance(value, list) or not value or any(
        not isinstance(d, int) or isinstance(d, bool) or not 0 <= d <= 6 for d in value
    ):
        raise ValueError("days are weekday numbers, Monday 0 to Sunday 6, and at least one")
    return sorted(set(value))


def _offset(value) -> int:
    value = 0 if value is None else value
    if not isinstance(value, int | float) or isinstance(value, bool) or abs(value) > MAX_OFFSET:
        raise ValueError(f"the offset is minutes, at most {MAX_OFFSET} before (negative) or after")
    return int(value)


# --- Checking (the shape; `api/automations.py` checks what a Device can do) ------------


def check_trigger(t: dict, location: sun.Location | None) -> dict:
    kind = t.get("type")
    if kind == "time":
        return {"type": "time", "at": _hhmm(parse_time(t.get("at"))), "days": _days(t.get("days"))}
    if kind == "sun":
        if t.get("event") not in sun.EVENTS:
            raise ValueError("a sun Trigger is at sunrise or sunset")
        if location is None:
            raise ValueError("set your location first, so Control knows when the sun rises and sets")
        return {"type": "sun", "event": t["event"], "offset": _offset(t.get("offset")), "days": _days(t.get("days"))}
    if kind == "state":
        if not isinstance(t.get("on"), bool):
            raise ValueError("a state Trigger says turns on (true) or off (false)")
        return {"type": "state", "target": _target(t), "on": t["on"], "minutes": _stays(t)}
    if kind == "app":
        if not isinstance(t.get("app"), str) or not t["app"]:
            raise ValueError("say which app")
        return {"type": "app", "target": _target(t), "app": t["app"], "minutes": _stays(t)}
    if kind == "offline":
        if not isinstance(t.get("offline"), bool):
            raise ValueError("an Offline Trigger says goes Offline (true) or comes back online (false)")
        return {"type": "offline", "target": _target(t), "offline": t["offline"]}
    if kind == "scene":
        return {"type": "scene", "target": _target(t)}
    if kind in PRESENCE:
        return _presence(t, "Trigger")
    if kind == "pc":
        if t.get("event") not in PC_EVENTS:
            raise ValueError(f"a PC Trigger is one of: {', '.join(PC_EVENTS)}")
        return {"type": "pc", "event": t["event"]}
    if kind == "web":
        return {"type": "web"}  # its secret is the Engine's to make (`api/automations.py`)
    raise ValueError(f"a Trigger is one of: {', '.join(TRIGGERS)}")


def _presence(part: dict, what: str) -> dict:
    if part["type"] == "person":
        if not isinstance(part.get("home"), bool):
            raise ValueError(f"a Person {what} says home (true) or away (false)")
        target = part.get("target")
        if not isinstance(target, str) or not target:
            raise ValueError("say who")
        return {"type": "person", "target": target, "home": part["home"]}
    if not isinstance(part.get("occupied"), bool):
        raise ValueError(f"a home {what} says someone is home (true) or nobody is (false)")
    return {"type": "home", "occupied": part["occupied"]}


def _stays(t: dict) -> int:
    """Minutes a state or app Trigger waits for it to stay so; 0: at once."""
    minutes = 0 if t.get("minutes") is None else t["minutes"]
    if (not isinstance(minutes, int | float) or isinstance(minutes, bool) or minutes != int(minutes)
            or not 0 <= minutes <= MAX_STAYS):
        raise ValueError("it stays so for whole minutes, 0 (at once) up to 24 hours")
    return int(minutes)


def check_condition(c: dict, location: sun.Location | None) -> dict:
    """The shape of a Condition; a state or app Condition's target is checked by the caller."""
    kind = c.get("type")
    if kind == "state":
        if not isinstance(c.get("on"), bool):
            raise ValueError("a state Condition says on (true) or off (false)")
        return {"type": "state", "target": _target(c), "on": c["on"]}
    if kind == "app":
        if not isinstance(c.get("app"), str) or not c["app"]:
            raise ValueError("say which app")
        return {"type": "app", "target": _target(c), "app": c["app"]}
    if kind == "time":
        after, before = parse_time(c.get("after")), parse_time(c.get("before"))
        if after == before:
            raise ValueError("a time window needs two different times")
        return {"type": "time", "after": _hhmm(after), "before": _hhmm(before)}
    if kind == "days":
        return {"type": "days", "days": _days(c.get("days"))}
    if kind == "sun":
        if c.get("is") not in ("dark", "light"):
            raise ValueError("a sun Condition is dark (between sunset and sunrise) or light")
        if location is None:
            raise ValueError("set your location first, so Control knows when the sun rises and sets")
        return {"type": "sun", "is": c["is"]}
    if kind == "scene":
        active = True if c.get("active") is None else c["active"]
        if not isinstance(active, bool):
            raise ValueError("a Scene Condition says active (true) or not (false)")
        return {"type": "scene", "target": _target(c), "active": active}
    if kind in PRESENCE:
        return _presence(c, "Condition")
    raise ValueError(f"a Condition is one of: {', '.join(CONDITIONS)}")


def check_step(a: dict) -> dict:
    """A wait or notify Action cleaned up; a control Action is checked by the caller."""
    do = a.get("do")
    if do == "wait":
        s = a.get("seconds")
        if not isinstance(s, int | float) or isinstance(s, bool) or not 1 <= s <= MAX_WAIT:
            raise ValueError("wait between 1 second and 24 hours")
        return {"do": "wait", "seconds": int(s)}
    if do == "notify":
        text = a.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("say what the notification says")
        return {"do": "notify", "text": text.strip()[:MAX_TEXT]}
    if do in CONTROL or do in ("run", "set_scene"):
        _target(a)
        return a
    raise ValueError(f"an Action is one of: {', '.join(CONTROL + ('run', 'set_scene', 'wait', 'notify'))}")


def check_undo(undo, do: str) -> dict:
    """An Action's "put it back" cleaned up. Whether its Device can be put back, and that "while" has
    an Only if to follow, is for `api/automations.py` to say."""
    if do not in UNDOABLE:
        raise ValueError(f"only a {', '.join(UNDOABLE)} can be put back, not a {do}")
    if not isinstance(undo, dict) or set(undo) not in ({"after"}, {"while"}):
        raise ValueError('put it back "after" some minutes, or "while" the Only if holds')
    if "while" in undo:
        if undo["while"] is not True:
            raise ValueError('"while" is true, or leave it out')
        return {"while": True}
    minutes = undo["after"]
    if (not isinstance(minutes, int | float) or isinstance(minutes, bool) or minutes != int(minutes)
            or not 1 <= minutes <= MAX_UNDO):
        raise ValueError("put it back after whole minutes, 1 up to 24 hours")
    return {"after": int(minutes)}


def _target(part: dict) -> str:
    target = part.get("target")
    if not isinstance(target, str) or not target:
        raise ValueError("say which Device or Group")
    return target


def check_counts(triggers: list, conditions: list, actions: list) -> None:
    for parts, what in ((triggers, "Triggers"), (conditions, "Conditions"), (actions, "Actions")):
        if len(parts) > MAX_PARTS:
            raise ValueError(f"at most {MAX_PARTS} {what}")
    if not actions:
        raise ValueError("an Automation needs at least one Action")


def targets_of(automation) -> set[str]:
    """Every Device or Group an Automation names."""
    parts = [*automation.triggers, *automation.conditions, *automation.actions]
    return {p["target"] for p in parts if "target" in p}


def set_off_by(automations: dict[str, list[dict]]) -> dict[str, list[str]]:
    """Scene uid -> the Automations whose Trigger is that Scene being set (`automations`: uid -> Triggers)."""
    out: dict[str, list[str]] = {}
    for uid, triggers in automations.items():
        for t in triggers:
            if t["type"] == "scene" and uid not in out.setdefault(t["target"], []):
                out[t["target"]].append(uid)
    return out


def starts(action: dict, set_off: dict[str, list[str]]) -> list[str]:
    """The Automations one Action starts: the one it runs, or those whose Trigger is the Scene it sets."""
    if action["do"] == "run":
        return [action["target"]]
    if action["do"] == "set_scene":
        return set_off.get(action["target"], [])
    return []


def loop(uid: str, actions: list[dict], others: dict[str, list[dict]],
         set_off: dict[str, list[str]] | None = None) -> list[str] | None:
    """The uids from `uid` back to itself if its `actions` would start it again, through the other
    Automations' Actions (`others`: uid -> actions), by running them or by setting a Scene that
    `set_off` says starts them (see `set_off_by`); None when they don't."""
    set_off = set_off or {}
    path: list[str] = [uid]
    seen: set[str] = set()

    def via(actions: list[dict]) -> bool:
        for nxt in (n for a in actions for n in starts(a, set_off)):
            if nxt == uid:
                path.append(uid)
                return True
            if nxt in seen:
                continue
            seen.add(nxt)
            path.append(nxt)
            if via(others.get(nxt, [])):
                return True
            path.pop()
        return False

    return path if via(actions) else None


def listened(automation) -> set[str]:
    """The Devices and Groups an Automation's Device Triggers name: what the Engine listens to while
    it's on (ADR 0011)."""
    return {t["target"] for t in automation.triggers if t["type"] in DEVICE_TRIGGERS}


def without(triggers: list, conditions: list, actions: list, gone: set[str]) -> tuple[list, list, list]:
    """The parts that don't name a forgotten Device or deleted Group (ADR 0012)."""
    keep = lambda parts: [p for p in parts if p.get("target") not in gone]  # noqa: E731
    return keep(triggers), keep(conditions), keep(actions)


# --- Plain language ----------------------------------------------------------------


def days_label(days: list[int]) -> str:
    if len(days) == 7:
        return "every day"
    if days == [0, 1, 2, 3, 4]:
        return "Monday to Friday"
    if days == [0, 1, 2, 3, 6]:
        return "Sunday to Thursday"
    return "on " + ", ".join(DAYS[d] for d in days)


def _offset_label(minutes: int, event: str) -> str:
    if not minutes:
        return f"At {event}"
    return f"{abs(minutes)} min {'before' if minutes < 0 else 'after'} {event}"


def trigger_label(t: dict, names: dict[str, str], app_names: dict[str, str] | None = None) -> str:
    if t["type"] == "time":
        return f"At {t['at']}, {days_label(t['days'])}"
    if t["type"] == "sun":
        return f"{_offset_label(t['offset'], t['event'])}, {days_label(t['days'])}"
    name = names.get(t.get("target", ""), t.get("target", ""))
    if t["type"] == "state":
        word = "on" if t["on"] else "off"
        stays = f" and stays {word} for {duration_label(t['minutes'] * 60)}" if t["minutes"] else ""
        return f"{name} turns {word}{stays}"
    if t["type"] == "app":
        minutes = t.get("minutes", 0)
        stays = f" and keeps it open for {duration_label(minutes * 60)}" if minutes else ""
        return f"{name} opens {(app_names or {}).get(t['app'], t['app'])}{stays}"
    if t["type"] == "offline":
        return f"{name} goes Offline" if t["offline"] else f"{name} comes back online"
    if t["type"] == "scene":
        return f"{name} is set"
    if t["type"] == "person":
        return f"{name} {'arrives home' if t['home'] else 'leaves home'}"
    if t["type"] == "home":
        return "The first person arrives home" if t["occupied"] else "The last person leaves home"
    if t["type"] == "pc":
        return PC_EVENTS[t["event"]]
    if t["type"] == "web":
        return "The web link is opened"
    return t["type"]


def condition_label(c: dict, names: dict[str, str], app_names: dict[str, str]) -> str:
    kind = c["type"]
    if kind == "state":
        return f"{names.get(c['target'], c['target'])} is {'on' if c['on'] else 'off'}"
    if kind == "app":
        return f"{names.get(c['target'], c['target'])} has {app_names.get(c['app'], c['app'])} open"
    if kind == "time":
        return f"Between {c['after']} and {c['before']}"
    if kind == "days":
        return "It's " + (days_label(c["days"]).removeprefix("on ") if len(c["days"]) < 7 else "any day")
    if kind == "sun":
        return "It's dark (after sunset, before sunrise)" if c["is"] == "dark" else "It's light (after sunrise, before sunset)"
    if kind == "scene":
        return f"{names.get(c['target'], c['target'])} is {'active' if c['active'] else 'not active'}"
    if kind == "person":
        return f"{names.get(c['target'], c['target'])} is {'home' if c['home'] else 'away'}"
    if kind == "home":
        return "Someone is home" if c["occupied"] else "Nobody is home"
    return kind


def duration_label(seconds: int) -> str:
    """"1 h 5 min", "30 s"."""
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    parts = [f"{h} h" if h else "", f"{m} min" if m else "", f"{s} s" if s else ""]
    return " ".join(p for p in parts if p)


def wait_label(seconds: int) -> str:
    return "Wait " + duration_label(seconds)


def action_label(a: dict, name: str, buttons: dict[str, str], app_names: dict[str, str]) -> str:
    """"Turn on Bulb 1", "Set AC to 24°, cool", "Run Evening", "Set Movie night", "Wait 10 min",
    "Notify: The AC is off"."""
    return _action_label(a, name, buttons, app_names) + undo_label(a.get("undo"))


def undo_label(undo: dict | None) -> str:
    """", then put it back after 10 min" or ", then put it back when the Only if stops holding"."""
    if not undo:
        return ""
    if "while" in undo:
        return ", then put it back when the Only if stops holding"
    return f", then put it back after {duration_label(undo['after'] * 60)}"


def _action_label(a: dict, name: str, buttons: dict[str, str], app_names: dict[str, str]) -> str:
    do = a["do"]
    if do == "wait":
        return wait_label(a["seconds"])
    if do == "notify":
        return f"Notify: {a['text']}"
    if do == "run":
        return f"Run {name}"
    if do == "set_scene":
        return f"Set {name}"
    text = hotkeys.describe(a, buttons, app_names)
    if do == "toggle":
        return f"Toggle {name}"
    if do == "set":
        if text in ("Turn on", "Turn off"):
            return f"{text} {name}"
        return f"Set {name} to {text.removeprefix('Set ')}"
    if do == "press":
        return f"{text} on {name}"
    if do == "open_app":
        return f"{text} on {name}"
    return f"{name}: {text[0].lower()}{text[1:]}"  # a step: "Bulb 1: brightness up 10%"


# --- Time ----------------------------------------------------------------------------


def occurrences(t: dict, start: dt.datetime, end: dt.datetime, location: sun.Location | None) -> Iterator[dt.datetime]:
    """When a timed Trigger fires in (start, end], in order (local, naive datetimes)."""
    day = start.date() - dt.timedelta(days=1)  # a sunrise offset can move a time across midnight
    while day <= end.date() + dt.timedelta(days=1):
        at = _at(t, day, location)
        if at is not None and start < at <= end and day.weekday() in t["days"]:
            yield at
        day += dt.timedelta(days=1)


def _at(t: dict, day: dt.date, location: sun.Location | None) -> dt.datetime | None:
    if t["type"] == "time":
        return dt.datetime.combine(day, parse_time(t["at"]))
    if t["type"] == "sun" and location is not None:
        event = sun.event_at(location, day, t["event"])
        if event is None:
            return None
        return (event + dt.timedelta(minutes=t["offset"])).replace(second=0, microsecond=0)
    return None


def next_occurrence(t: dict, after: dt.datetime, location: sun.Location | None) -> dt.datetime | None:
    """The next time a timed Trigger fires after `after`, looking a week and a day ahead."""
    return next(occurrences(t, after, after + dt.timedelta(days=8), location), None)


def time_condition(c: dict, now: dt.datetime, location: sun.Location | None) -> bool:
    """A time, days or sun Condition, now."""
    if c["type"] == "days":
        return now.weekday() in c["days"]
    if c["type"] == "time":
        after, before, t = parse_time(c["after"]), parse_time(c["before"]), now.time()
        return after <= t < before if after < before else (t >= after or t < before)
    if c["type"] == "sun":
        if location is None:
            return False
        return sun.is_dark(location, now) == (c["is"] == "dark")
    raise ValueError(f"'{c['type']}' isn't a time Condition")
