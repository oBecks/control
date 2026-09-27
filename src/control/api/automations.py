"""Automations (ADR 0006, 0012): the Engine keeps them, and its Runner starts their Runs on time or
when asked. Each Run goes on its own thread, so a Wait holds up nothing else.

The rules every Run follows (ADR 0012):
- A new Trigger (or Run button) restarts a Run that's still going: the old one ends as *restarted*.
- Never late: a timed Trigger more than LATE seconds past its time is logged as *missed*, and an
  Action that would happen more than LATE late (the PC slept through a Wait, say) is abandoned with
  the rest: the Run is *interrupted*, and a notification says what didn't happen. A Run cut short by
  Control quitting is found *running* at the next start, and handled the same way.
- A failed Action doesn't stop the others; the Run ends *partly failed* and a notification says which.
- Running by hand skips the Conditions.

Notifications go to the UI as notices, and to Windows through the Desktop App, which watches
`/api/notices/watch` like the Hotkey listener watches its Hotkeys. Anyone who may use the Engine may
set Automations up, phones included, like Groups. Device logic stays in `app.py` and `hotkeys.py`.
"""

import datetime as dt
import sys
import threading
import time
from contextlib import closing
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..engine import automations, streamer, sun
from ..engine.errors import DeviceUnreachable
from ..engine.registry import Automation, Registry, Run
from . import hotkeys as hotkeys_api
from .deps import registry
from .listening import listening

router = APIRouter()

LOCATION = "location"  # setting: {"name", "lat", "lon"}
LAST_CHECK = "automations_last_check"  # setting: when the Runner last looked for due Triggers
LATE = 60  # seconds past its time that a Trigger still fires, or an Action still happens
CHECK_AT_MOST = 300  # seconds between looks for due Triggers, so waking from sleep is noticed soon
RETRY_SECONDS = 30  # after a check for due Triggers failed
WAIT_CHUNK = 30  # a Wait looks at the clock at least this often (seconds)
WATCH_SECONDS = 25
BY_HAND = "Run by hand"


def clock() -> float:
    """The wall clock (tests replace it)."""
    return time.time()


def _local(ts: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(ts)


def location(r: Registry) -> sun.Location | None:
    saved = r.setting(LOCATION)
    return sun.Location(**saved) if saved else None


def _api():
    from . import app

    return app


# --- Running --------------------------------------------------------------------------


@dataclass
class _Active:
    run_id: int
    automation: Automation  # as it was when the Run started: an edit meanwhile doesn't change it
    steps: list[dict]
    hops: int = 0  # started by a change another Automation made, and so on (the loop guard, ADR 0012)
    cancel: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class Runner:
    """Starts Runs: on time from its own thread, and when asked (the Run button, the Assistant)."""

    def __init__(self):
        self._cond = threading.Condition()
        self._revision = 0
        self._active: dict[str, _Active] = {}
        self._thread: threading.Thread | None = None
        self._closing = False
        self._last_notice = 0

    # The scheduler

    def start(self) -> None:
        self._closing = False
        with closing(Registry()) as r:
            self.recover(r)
            self._last_notice = max((n.id for n in r.notices()), default=0)
        self._thread = threading.Thread(target=self._loop, name="automations", daemon=True)
        self._thread.start()
        listening.start()  # Device Triggers (ADR 0011)

    def stop(self) -> None:
        """Control is quitting: Runs still going end as interrupted (and say so)."""
        with self._cond:
            self._closing = True
            self._cond.notify_all()
            active = list(self._active.values())
        listening.stop()
        for a in active:
            a.cancel.set()
        for a in active:
            if a.thread:
                a.thread.join(timeout=5)

    def changed(self) -> None:
        """Automations, Groups or the location changed: work out the next due time again, and what to
        listen to."""
        with self._cond:
            self._revision += 1
            self._cond.notify_all()
        listening.sync()

    def _loop(self) -> None:
        with closing(Registry()) as r:
            last = r.setting(LAST_CHECK) or clock()
            while not self._closing:
                with self._cond:
                    revision = self._revision
                now = clock()
                try:
                    self.check(r, last, now)
                    last = now
                    r.set_setting(LAST_CHECK, now)
                    due = self.next_due(r, now)
                except Exception as exc:  # e.g. the database was locked: one bad pass mustn't stop every Automation
                    print(f"Automations: checking for due Triggers failed, trying again soon: {exc!r}", file=sys.stderr)
                    due = clock() + RETRY_SECONDS
                with self._cond:
                    if self._revision == revision and not self._closing:
                        # Nothing due: sleep until something changes. Otherwise wake at least every
                        # CHECK_AT_MOST, so a PC waking from sleep (or a changed clock) is noticed soon.
                        self._cond.wait(None if due is None else min(max(due - clock(), 0), CHECK_AT_MOST))

    def check(self, r: Registry, last: float, now: float) -> None:
        """Start the Runs whose timed Triggers came due in (last, now]; log those more than LATE ago as missed."""
        if now < last:  # the clock went back
            return
        last = max(last, now - 8 * 24 * 3600)  # a week off leaves one missed Run per Automation anyway
        where = location(r)
        for a in r.automations():
            if not a.enabled:
                continue
            since = max(last, a.armed)
            if since >= now:
                continue
            due: tuple[float, dict] | None = None
            missed: tuple[float, dict] | None = None
            for t in a.triggers:
                for at in automations.occurrences(t, _local(since), _local(now), where):
                    ts = at.timestamp()
                    if now - ts <= LATE:
                        due = due if due and due[0] >= ts else (ts, t)
                    else:
                        missed = missed if missed and missed[0] >= ts else (ts, t)
            if missed:
                label = automations.trigger_label(missed[1], {})  # timed Triggers name nothing
                r.add_run(a.uid, label, outcome="missed", started=missed[0], steps=_not_run(r, a))
            if due:
                self.run(r, a.uid, automations.trigger_label(due[1], {}))

    def next_due(self, r: Registry, now: float) -> float | None:
        where = location(r)
        times = [
            at.timestamp()
            for a in r.automations() if a.enabled
            for t in a.triggers
            if (at := automations.next_occurrence(t, _local(max(now, a.armed)), where)) is not None
        ]
        return min(times, default=None)

    def recover(self, r: Registry) -> None:
        """Runs left running when Control last stopped (it quit, or the PC turned off) were interrupted."""
        for run in r.runs(outcome="running", limit=1000):
            r.update_run(run.id, run.steps, "interrupted", "Control stopped")
            if text := _didnt_run(run.steps):
                try:
                    name = r.get_automation(run.automation).name
                except LookupError:
                    continue
                self.notify(r, name, text, run.automation)

    # Runs

    def run(self, r: Registry, uid: str, cause: str, by_hand: bool = False, hops: int = 0) -> int:
        """Start a Run of an Automation; returns its id. One still going is restarted."""
        a = r.get_automation(uid)
        with self._cond:
            old = self._active.pop(uid, None)
            if old:
                old.cancel.set()
            steps = _not_run(r, a)
            active = _Active(r.add_run(uid, cause, steps=steps), a, steps, hops)
            self._active[uid] = active
            active.thread = threading.Thread(target=self._go, args=(active, by_hand), name=f"run-{uid}", daemon=True)
            active.thread.start()
        return active.run_id

    def running(self, uid: str) -> bool:
        with self._cond:
            return uid in self._active

    def join(self, uid: str, timeout: float = 5) -> None:
        """Wait for an Automation's Run to end (for tests)."""
        with self._cond:
            active = self._active.get(uid)
        if active and active.thread:
            active.thread.join(timeout)

    def _go(self, active: _Active, by_hand: bool) -> None:
        with closing(Registry()) as r:
            try:
                self._steps(r, active, by_hand)
            except Exception as exc:  # a bug mustn't leave the Run running forever
                r.update_run(active.run_id, active.steps, "partly_failed", f"Control failed: {exc!r}")
            finally:
                with self._cond:
                    if self._active.get(active.automation.uid) is active:
                        del self._active[active.automation.uid]

    def _steps(self, r: Registry, active: _Active, by_hand: bool) -> None:
        a = active.automation
        steps = active.steps
        if not by_hand and a.conditions:
            unmet = _unmet(r, a)
            if unmet is not None:
                r.update_run(active.run_id, steps, "skipped", unmet)
                return
        failed: list[str] = []
        for i, action in enumerate(a.actions):
            if active.cancel.is_set():
                self._cut_short(r, a, active, steps)
                return
            step = steps[i]
            if action["do"] == "wait":
                until = clock() + action["seconds"]
                while (left := until - clock()) > 0 and not active.cancel.wait(min(left, WAIT_CHUNK)):
                    pass
                if active.cancel.is_set():
                    self._cut_short(r, a, active, steps)
                    return
                if clock() - until > LATE and i < len(a.actions) - 1:
                    # The PC slept through the Wait (or Control froze): the rest would be late.
                    step["result"] = "done"
                    r.update_run(active.run_id, steps, "interrupted", "The PC slept, or Control was stopped")
                    if text := _didnt_run(steps):
                        self.notify(r, a.name, text, a.uid)
                    return
                step["result"] = "done"
            elif action["do"] == "notify":
                self.notify(r, a.name, action["text"], a.uid)
                step["result"] = "done"
            else:
                problem = _control(r, action, a.uid, active.hops)
                step["result"] = "failed" if problem else "done"
                if problem:
                    step["detail"] = problem
                    failed.append(f"{step['label']} failed: {problem}")
            r.update_run(active.run_id, steps)
        if failed:
            r.update_run(active.run_id, steps, "partly_failed")
            self.notify(r, a.name, "; ".join(failed), a.uid)
        else:
            r.update_run(active.run_id, steps, "succeeded")

    def _cut_short(self, r: Registry, a: Automation, active: _Active, steps: list[dict]) -> None:
        if self._closing:
            r.update_run(active.run_id, steps, "interrupted", "Control quit")
            if text := _didnt_run(steps):
                self.notify(r, a.name, text, a.uid)
        else:
            r.update_run(active.run_id, steps, "restarted", "Started again by a new Trigger")

    # Notices

    def notify(self, r: Registry, title: str, text: str, automation: str | None = None) -> int:
        notice = r.add_notice(title, text, automation)
        with self._cond:
            self._last_notice = max(self._last_notice, notice)
            self._cond.notify_all()
        return notice

    def watch_notices(self, after: int, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._last_notice <= after and not self._closing and (left := deadline - time.monotonic()) > 0:
                self._cond.wait(left)

    def close_watches(self) -> None:
        with self._cond:
            self._closing = True
            self._cond.notify_all()


runner = Runner()


def _not_run(r: Registry, a: Automation) -> list[dict]:
    names = _names(r)
    return [{"label": _action_label(r, x, names), "result": "not_run"} | ({"wait": True} if x["do"] == "wait" else {})
            for x in a.actions]


def _didnt_run(steps: list[dict]) -> str | None:
    """What a notification says about Actions that didn't happen; None when they were only Waits."""
    labels = [s["label"] for s in steps if s["result"] == "not_run" and not s.get("wait")]
    return f"{', '.join(labels)} didn't run" if labels else None


def _control(r: Registry, action: dict, automation: str, hops: int) -> str | None:
    """Do a control Action; what went wrong, or None."""
    try:
        t = hotkeys_api.target(r, action["target"])
        listening.acting(r.get_group(t.uid).members if t.is_group else [t.uid], automation, hops)
        clean = hotkeys_api.check_action(r, t, _without_target(action))
        reading = hotkeys_api.run(r, t, clean)
    except (LookupError, ValueError, DeviceUnreachable) as exc:
        return str(exc)
    except Exception as exc:  # a brand library failing its own way
        return f"{type(exc).__name__}: {exc}"
    if reading.get("failed"):
        return "; ".join(f["reason"] for f in reading["failed"].values())
    return None


def _reading(r: Registry, uid: str) -> dict:
    api = _api()
    if uid.startswith("group:"):
        return api._group_state(r, r.get_group(uid), None)
    return api._read_state(r, api._device_out(r, uid), None)


def _unmet(r: Registry, a: Automation) -> str | None:
    """None when the Conditions hold (all of them, or any one); otherwise which didn't, for the Run."""
    now = _local(clock())
    where = location(r)
    names = _names(r)
    unmet = []
    for c in a.conditions:
        label = automations.condition_label(c, names, _app_names(r, c.get("target")))
        if c["type"] in ("state", "app"):
            try:
                state = _reading(r, c["target"])["state"]
            except Exception as exc:  # a Device that doesn't answer can't be said to be on
                unmet.append(f"{label}: couldn't tell ({exc})")
                continue
            holds = bool(state.get("on")) == c["on"] if c["type"] == "state" else (
                bool(state.get("on")) and state.get("app") == c["app"])
        else:
            holds = automations.time_condition(c, now, where)
        if holds and a.match == "any":
            return None
        if not holds:
            unmet.append(f"{label}: no")
    if not unmet:
        return None
    return "Only if " + ("none held: " if a.match == "any" else "") + "; ".join(unmet)


# --- Labels ------------------------------------------------------------------------------


def _names(r: Registry) -> dict[str, str]:
    names = {d.uid: d.name for d in r.all()}
    names |= {d.uid: d.name for d in r.remotes()}
    names |= {g.uid: g.name for g in r.groups()}
    return names


def _target_info(r: Registry, uid: str | None) -> hotkeys_api.Target | None:
    if uid is None:
        return None
    try:
        return hotkeys_api.target(r, uid)
    except LookupError:
        return None


def _app_names(r: Registry, uid: str | None) -> dict[str, str]:
    """Package -> name, for the Streamer's apps and the apps Control knows."""
    t = _target_info(r, uid)
    return {x["app"]: x["name"] for x in [*streamer.CATALOGUE, *(t.apps if t else [])]}


def _action_label(r: Registry, action: dict, names: dict[str, str]) -> str:
    if "target" not in action:
        return automations.action_label(action, "", {}, {})
    t = _target_info(r, action["target"])
    name = names.get(action["target"], "(removed)")
    return automations.action_label(action, name, t.buttons if t else {}, _app_names(r, action["target"]))


def _without_target(action: dict) -> dict:
    return {k: v for k, v in action.items() if k != "target"}


# --- Checking ---------------------------------------------------------------------------


def _checked_target(r: Registry, uid: str) -> hotkeys_api.Target:
    if uid.startswith("automation:"):  # a Hotkey's target, not yet an Automation's (chaining comes later)
        raise ValueError(f"there's no Device or Group '{uid}'")
    try:
        return hotkeys_api.target(r, uid)
    except LookupError:
        raise ValueError(f"there's no Device or Group '{uid}'") from None


def _check_on_off(t: hotkeys_api.Target) -> None:
    if "on" not in t.settable:
        why = "only has a Power Toggle, so Control can't tell" if t.buttons.get("power") else "can't say"
        raise ValueError(f"'{t.name}' {why} whether it's on")


def _check_trigger(r: Registry, t: dict, where) -> dict:
    clean = automations.check_trigger(t, where)
    if clean["type"] == "state":
        _check_on_off(_checked_target(r, clean["target"]))
    if clean["type"] == "app":
        _check_streamer(_checked_target(r, clean["target"]))
    if clean["type"] == "offline":
        target = _checked_target(r, clean["target"])
        if target.control is None:
            raise ValueError(f"'{target.name}' can't be controlled yet, so Control can't listen to it")
        if target.is_group or target.control not in ("light", "plug", "streamer"):
            raise ValueError(f"only a light, plug or Streamer can go Offline, and '{target.name}' isn't one: "
                             "an AC, TV or fan has no connection of its own")
    return clean


def _check_streamer(t: hotkeys_api.Target) -> None:
    if t.control != "streamer":
        raise ValueError(f"only a Streamer has apps open, and '{t.name}' isn't one")


def _check_condition(r: Registry, c: dict, where) -> dict:
    clean = automations.check_condition(c, where)
    if clean["type"] == "state":
        _check_on_off(_checked_target(r, clean["target"]))
    if clean["type"] == "app":
        _check_streamer(_checked_target(r, clean["target"]))
    return clean


def _check_action(r: Registry, a: dict) -> dict:
    clean = automations.check_step(a)
    if clean["do"] in automations.CONTROL:
        t = _checked_target(r, a["target"])
        return hotkeys_api.check_action(r, t, _without_target(a)) | {"target": t.uid}
    return clean


def _numbered(what: str, parts: list[dict], check) -> list[dict]:
    out = []
    for i, part in enumerate(parts, 1):
        if not isinstance(part, dict):
            raise ValueError(f"{what} {i} isn't an object")
        try:
            out.append(check(part))
        except ValueError as exc:
            raise ValueError(f"{what} {i}: {exc}") from None
    return out


def check(r: Registry, triggers: list, conditions: list, actions: list, whole: bool = True) -> tuple[list, list, list]:
    """The parts cleaned up, or ValueError naming the first one that's wrong. `whole`: it's to be
    saved, so it needs an Action."""
    where = location(r)
    triggers = _numbered("Trigger", triggers, lambda t: _check_trigger(r, t, where))
    conditions = _numbered("Condition", conditions, lambda c: _check_condition(r, c, where))
    actions = _numbered("Action", actions, lambda a: _check_action(r, a))
    if whole:
        automations.check_counts(triggers, conditions, actions)
    return triggers, conditions, actions


def _name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("give the Automation a name")
    return name


# --- Views -------------------------------------------------------------------------------


class RunOut(BaseModel):
    id: int
    cause: str = Field(description='what started it, e.g. "At 07:00, every day" or "Run by hand"')
    started: float
    ended: float | None
    outcome: str = Field(description="running, succeeded, partly_failed, skipped (by its Conditions), missed, "
                                     "interrupted or restarted")
    steps: list[dict] = Field(description='each Action: {"label", "result": done|failed|not_run, "detail"?}')
    note: str = Field(description="e.g. which Condition wasn't met")


def _run_out(run: Run) -> RunOut:
    return RunOut(id=run.id, cause=run.cause, started=run.started, ended=run.ended, outcome=run.outcome,
                  steps=run.steps, note=run.note)


class AutomationOut(BaseModel):
    uid: str
    name: str
    enabled: bool
    match: str = Field(description="the Conditions: all must hold, or any one")
    triggers: list[dict] = Field(description="each with a plain-language `label`")
    conditions: list[dict]
    actions: list[dict]
    summary: str = Field(description="the whole Automation in plain language")
    attention: str | None = Field(description="why it switched itself off, e.g. a Device it used was forgotten")
    made_by: str
    running: bool
    last_run: RunOut | None
    next_run: float | None = Field(description="when a Trigger fires next, if it's on and has a timed Trigger")


def _labelled(r: Registry, triggers: list[dict], conditions: list[dict], actions: list[dict]):
    names = _names(r)
    return (
        [t | {"label": automations.trigger_label(t, names, _app_names(r, t.get("target")))} for t in triggers],
        [c | {"label": automations.condition_label(c, names, _app_names(r, c.get("target")))} for c in conditions],
        [x | {"label": _action_label(r, x, names)} for x in actions],
    )


def _out(r: Registry, a: Automation, last: Run | None = None, now: float | None = None) -> AutomationOut:
    triggers, conditions, actions = _labelled(r, a.triggers, a.conditions, a.actions)
    next_run = None
    if a.enabled:
        where, now = location(r), now or clock()
        times = [at.timestamp() for t in a.triggers
                 if (at := automations.next_occurrence(t, _local(max(now, a.armed)), where)) is not None]
        next_run = min(times, default=None)
    return AutomationOut(
        uid=a.uid, name=a.name, enabled=a.enabled, match=a.match, triggers=triggers, conditions=conditions,
        actions=actions, summary=_summary(a.match, triggers, conditions, actions), attention=a.attention,
        made_by=a.made_by, running=runner.running(a.uid), last_run=_run_out(last) if last else None,
        next_run=next_run,
    )


def _mid_sentence(label: str) -> str:
    """A part's label inside the summary: "At 07:00" becomes "at 07:00", but a Device's name keeps its case."""
    first, _, rest = label.partition(" ")
    return f"{first.lower()} {rest}" if first in ("At", "Between", "It's") else label


def _summary(match: str, triggers: list[dict], conditions: list[dict], actions: list[dict]) -> str:
    when = " or ".join(_mid_sentence(t["label"]) for t in triggers) or "only when run by hand"
    text = f"When: {when}."
    if conditions:
        joiner = " and " if match == "all" else " or "
        text += " Only if " + joiner.join(_mid_sentence(c["label"]) for c in conditions) + "."
    return text + " Then: " + (", then ".join(a["label"] for a in actions) or "nothing yet") + "."


class PreviewIn(BaseModel):
    triggers: list[dict] = Field(default_factory=list)
    conditions: list[dict] = Field(default_factory=list)
    match: str = "all"
    actions: list[dict] = Field(default_factory=list)


@router.post("/api/automations/preview")
def preview_automation(body: PreviewIn, r: Registry = Depends(registry)):
    """The builder's draft, checked and in plain language, without saving it: each part with its
    `label`, and the `summary`. A part that's wrong answers 422, naming it ("Action 2: …")."""
    triggers, conditions, actions = _labelled(r, *check(r, body.triggers, body.conditions, body.actions, whole=False))
    return {"triggers": triggers, "conditions": conditions, "actions": actions,
            "summary": _summary(_match(body.match), triggers, conditions, actions)}


@router.get("/api/automations", response_model=list[AutomationOut])
def list_automations(r: Registry = Depends(registry)):
    last = r.last_runs()
    return [_out(r, a, last.get(a.uid)) for a in r.automations()]


class AutomationIn(BaseModel):
    name: str
    triggers: list[dict] = Field(default_factory=list, description="none: it runs only by hand")
    conditions: list[dict] = Field(default_factory=list)
    match: str = Field("all", description="the Conditions: all or any")
    actions: list[dict]
    enabled: bool = True
    by_assistant: bool = Field(False, description="made by the Assistant, so the app can say so")


def _match(match: str) -> str:
    if match not in ("all", "any"):
        raise ValueError("match is all or any")
    return match


@router.post("/api/automations", response_model=AutomationOut, status_code=201)
def add_automation(body: AutomationIn, r: Registry = Depends(registry)):
    triggers, conditions, actions = check(r, body.triggers, body.conditions, body.actions)
    uid = r.add_automation(_name(body.name), triggers, conditions, actions, _match(body.match), body.enabled,
                           "assistant" if body.by_assistant else "user")
    runner.changed()
    return _out(r, r.get_automation(uid))


@router.get("/api/automations/{uid}", response_model=AutomationOut)
def get_automation(uid: str, r: Registry = Depends(registry)):
    a = r.get_automation(uid)
    runs = r.runs(uid, limit=1)
    return _out(r, a, runs[0] if runs else None)


@router.get("/api/automations/{uid}/runs", response_model=list[RunOut])
def automation_runs(uid: str, r: Registry = Depends(registry)):
    """The last Runs, newest first."""
    r.get_automation(uid)
    return [_run_out(run) for run in r.runs(uid)]


class AutomationPatch(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    match: str | None = None
    triggers: list[dict] | None = Field(None, description="the full new list")
    conditions: list[dict] | None = None
    actions: list[dict] | None = None


@router.patch("/api/automations/{uid}", response_model=AutomationOut)
def patch_automation(uid: str, patch: AutomationPatch, r: Registry = Depends(registry)):
    a = r.get_automation(uid)
    triggers, conditions, actions = check(
        r,
        a.triggers if patch.triggers is None else patch.triggers,
        a.conditions if patch.conditions is None else patch.conditions,
        a.actions if patch.actions is None else patch.actions,
    )
    r.update_automation(
        uid,
        name=_name(patch.name) if patch.name is not None else None,
        enabled=patch.enabled,
        match=_match(patch.match) if patch.match is not None else None,
        triggers=triggers if patch.triggers is not None else None,
        conditions=conditions if patch.conditions is not None else None,
        actions=actions if patch.actions is not None else None,
    )
    runner.changed()
    return get_automation(uid, r)


@router.delete("/api/automations/{uid}", status_code=204)
def delete_automation(uid: str, r: Registry = Depends(registry)):
    r.forget_automation(uid)
    runner.changed()


@router.post("/api/automations/{uid}/run", response_model=RunOut, status_code=202)
def run_automation(uid: str, r: Registry = Depends(registry)):
    """Run it now, skipping its Conditions (the person asked). Answers at once: a Wait may take long."""
    run_id = runner.run(r, uid, BY_HAND, by_hand=True)
    return _run_out(next(run for run in r.runs(uid, limit=5) if run.id == run_id))


# --- Location ------------------------------------------------------------------------------


class LocationIO(BaseModel):
    name: str | None = Field(None, description="a city from /api/location/cities, or left out for coordinates")
    lat: float
    lon: float


def _location_out(r: Registry):
    where = location(r)
    if where is None:
        return None
    today = _local(clock()).date()
    times = {e: sun.event_at(where, today, e) for e in sun.EVENTS}
    return {"name": where.name, "lat": where.lat, "lon": where.lon,
            **{e: t.strftime("%H:%M") if t else None for e, t in times.items()}}


@router.get("/api/location")
def get_location(r: Registry = Depends(registry)):
    """Where the home is, for sunrise and sunset, with today's times; null until it's set."""
    return _location_out(r)


@router.put("/api/location")
def set_location(body: LocationIO, r: Registry = Depends(registry)):
    where = sun.check(body.name, body.lat, body.lon)
    r.set_setting(LOCATION, {"name": where.name, "lat": where.lat, "lon": where.lon})
    runner.changed()
    return _location_out(r)


@router.get("/api/location/cities")
def find_cities(q: str = ""):
    """Cities matching `q`, from the list bundled with Control (no internet)."""
    return [{"name": c.name, "lat": c.lat, "lon": c.lon} for c in sun.find_cities(q)]


# --- Notices --------------------------------------------------------------------------------


class NoticeOut(BaseModel):
    id: int
    time: float
    title: str = Field(description="the Automation's name")
    text: str
    automation: str | None
    seen: bool


@router.get("/api/notices", response_model=list[NoticeOut])
def list_notices(unseen: bool = True, r: Registry = Depends(registry)):
    return [NoticeOut(**vars(n)) for n in r.notices(unseen=unseen)]


class SeenIn(BaseModel):
    ids: list[int] | None = Field(None, description="left out: all of them")


@router.post("/api/notices/seen", status_code=204)
def notices_seen(body: SeenIn, r: Registry = Depends(registry)):
    r.mark_notices_seen(body.ids)


@router.get("/api/notices/watch", response_model=list[NoticeOut])
def watch_notices(request: Request, after: int = 0, r: Registry = Depends(registry)):
    """The Desktop App's long poll for Windows notifications: answers with the notices after `after`
    once there are any, or empty after WATCH_SECONDS."""
    if not request.state.local:
        return JSONResponse(status_code=403, content={"detail": "only the computer running Control"})
    runner.watch_notices(after, WATCH_SECONDS)
    return [NoticeOut(**vars(n)) for n in r.notices(after=after)]
