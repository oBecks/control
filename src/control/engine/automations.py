"""Automations (see CONTEXT.md, ADR 0006, 0011, 0012): When (Triggers) → Only if (Conditions) → Then
(Actions). The Engine runs them; this module holds their shape, checks and plain-language labels,
and the time arithmetic. Running them, and anything that reaches a Device, is in `api/automations.py`.

Times are the PC's local time, "HH:MM". Days are weekday numbers, Monday 0 to Sunday 6; a Trigger or
Condition without `days` means every day.

A Trigger is one of:
    {"type": "time", "at": "07:00", "days": [0, 1, 2, 3, 4]}
    {"type": "sun", "event": "sunrise" | "sunset", "offset": -30, "days": [...]}   offset in minutes
(Triggers on a Device's state or going Offline come with listening, ADR 0011.)

A Condition is one of:
    {"type": "state", "target": uid, "on": true}          a Device or Group is on (a Group: any member)
    {"type": "app", "target": uid, "app": "com.netflix.ninja"}   a Streamer has that app open
    {"type": "time", "after": "22:00", "before": "06:00"}  may cross midnight
    {"type": "days", "days": [5, 6]}
    {"type": "sun", "is": "dark" | "light"}               dark: between sunset and sunrise
Conditions are checked once, when a Trigger fires: all of them, or any one (`match`).

An Action is one of:
    {"do": "toggle" | "set" | "step" | "press" | "open_app", "target": uid, ...}   a Hotkey's action
    {"do": "wait", "seconds": 600}
    {"do": "notify", "text": "The AC is off"}
"""

import datetime as dt
import re
from collections.abc import Iterator

from . import hotkeys, sun

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
EVERY_DAY = list(range(7))
TRIGGERS = ("time", "sun")
CONDITIONS = ("state", "app", "time", "days", "sun")
CONTROL = ("toggle", "set", "step", "press", "open_app")
MAX_WAIT = 24 * 3600
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
    raise ValueError(f"a Trigger is one of: {', '.join(TRIGGERS)}")


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
    if do in CONTROL:
        _target(a)
        return a
    raise ValueError(f"an Action is one of: {', '.join(CONTROL + ('wait', 'notify'))}")


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


def trigger_label(t: dict, names: dict[str, str]) -> str:
    if t["type"] == "time":
        return f"At {t['at']}, {days_label(t['days'])}"
    if t["type"] == "sun":
        return f"{_offset_label(t['offset'], t['event'])}, {days_label(t['days'])}"
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
    return kind


def wait_label(seconds: int) -> str:
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    parts = [f"{h} h" if h else "", f"{m} min" if m else "", f"{s} s" if s else ""]
    return "Wait " + " ".join(p for p in parts if p)


def action_label(a: dict, name: str, buttons: dict[str, str], app_names: dict[str, str]) -> str:
    """"Turn on Bulb 1", "Set AC to 24°, cool", "Wait 10 min", "Notify: The AC is off"."""
    do = a["do"]
    if do == "wait":
        return wait_label(a["seconds"])
    if do == "notify":
        return f"Notify: {a['text']}"
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
