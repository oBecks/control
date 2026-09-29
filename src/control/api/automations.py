"""Automations (ADR 0006, 0012): the Engine keeps them, and its Runner starts their Runs on time or
when asked. Each Run goes on its own thread, so a Wait holds up nothing else.

The rules every Run follows (ADR 0012):
- A new Trigger (or Run button) restarts a Run that's still going: the old one ends as *restarted*.
- Never late: a timed Trigger more than LATE seconds past its time is logged as *missed*, and an
  Action that would happen more than LATE late (the PC slept through a Wait, say) is abandoned with
  the rest: the Run is *interrupted*, and a notification says what didn't happen. A Run cut short by
  Control quitting is found *running* at the next start, and handled the same way.
- A failed Action doesn't stop the others; the Run ends *partly failed* and a notification says which.
- Running by hand skips the Conditions, and so does a Run another Automation starts (chaining). A
  Scene being set is a Trigger like any other: its Runs check their Conditions.
- The loop guard: a chain of Automations starting each other, by an Action, by setting a Scene
  another one's Trigger is, or by changing a Device another one listens to, stops after
  `listening.MAX_HOPS`, and the one it stopped keeps a skipped Run.

Notifications go to the UI as notices, and to Windows through the Desktop App, which watches
`/api/notices/watch` like the Hotkey listener watches its Hotkeys. Anyone who may use the Engine may
set Automations up, phones included, like Groups. Device logic stays in `app.py` and `hotkeys.py`.
"""

import datetime as dt
import hmac
import secrets
import sys
import threading
import time
from contextlib import closing
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from ..engine import automations, scenes, streamer, sun
from ..engine.errors import DeviceUnreachable
from ..engine.registry import Automation, Registry, Run, Undo
from . import hotkeys as hotkeys_api
from . import lan
from . import listening as listening_api
from . import people as people_api
from . import scenes as scenes_api
from .deps import registry
from .listening import listening

router = APIRouter()

LOCATION = "location"  # setting: {"name", "lat", "lon"}
LAST_CHECK = "automations_last_check"  # setting: when the Runner last looked for due Triggers
NEW = "automation:new"  # an Automation not saved yet, for the loop check
LATE = 60  # seconds past its time that a Trigger still fires, or an Action still happens
CHECK_AT_MOST = 300  # seconds between looks for due Triggers, so waking from sleep is noticed soon
RETRY_SECONDS = 30  # after a check for due Triggers failed
WAIT_CHUNK = 30  # a Wait looks at the clock at least this often (seconds)
WATCH_SECONDS = 25
BY_HAND = "Run by hand"
HOOKS = "/api/hooks/"  # a web link is this and its secret (ADR 0016)
LOCAL_URL = "http://127.0.0.1:8321"  # where a web link points while phone access is off
WHILE_EVERY = 60  # seconds between looks at the Only if of Devices waiting to be put back
UNDO_TRIES = 5  # a put-back that fails is tried again every RETRY_SECONDS, this many times
GUESSES = (20, 60)  # a client gets this many wrong web links in this many seconds before it's held off


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
    hops: int = 0  # started by another Automation (an Action, or a change it made), and so on (ADR 0012)
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
        self._while_at = 0.0  # when the Undos waiting on an Only if were last looked at
        self._undo_retry: dict[int, float] = {}  # Undo id -> not before, after a put-back failed
        self._undo_tries: dict[int, int] = {}

    # The scheduler

    def start(self) -> None:
        self._closing = False
        with closing(Registry()) as r:
            self.recover(r)
            self._last_notice = max((n.id for n in r.notices()), default=0)
            self.pc_event(r, "starts")
        self._thread = threading.Thread(target=self._loop, name="automations", daemon=True)
        self._thread.start()
        listening.start()  # Device Triggers (ADR 0011)
        people_api.presence.start()  # Presence Triggers (ADR 0014)

    def stop(self) -> None:
        """Control is quitting: Runs still going end as interrupted (and say so)."""
        with self._cond:
            self._closing = True
            self._cond.notify_all()
            active = list(self._active.values())
        listening.stop()
        people_api.presence.stop()
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
                    self.undo_check(r, now)
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
        return min([*times, *self.undo_due(r)], default=None)

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
            elif action["do"] in ("run", "set_scene"):
                chain = self._chain if action["do"] == "run" else self._set_scene
                problem = chain(r, action["target"], active)
                step["result"] = "failed" if problem else "done"
                if problem:
                    step["detail"] = problem
                    failed.append(f"{step['label']} failed: {problem}")
            else:
                undo = action.get("undo")
                before = _remember(r, action["target"]) if undo else None
                problem = _control(r, action, a.uid, active.hops)
                step["result"] = "failed" if problem else "done"
                if problem:
                    step["detail"] = problem
                    failed.append(f"{step['label']} failed: {problem}")
                elif undo:
                    step["undo"] = self._schedule_undo(r, active, i, action, undo, before)
            r.update_run(active.run_id, steps)
        if failed:
            r.update_run(active.run_id, steps, "partly_failed")
            self.notify(r, a.name, "; ".join(failed), a.uid)
        else:
            r.update_run(active.run_id, steps, "succeeded")

    # Putting Devices back (ADR 0017)

    def _schedule_undo(self, r: Registry, active: _Active, index: int, action: dict, undo: dict,
                       before: tuple[dict | None, str]) -> str:
        """Remember how the Device was and how the Action left it, to put it back when due; what the
        Run's step says about it."""
        state, why = before
        if state is None:
            return f"Can't be put back: couldn't tell how it was ({why})"
        try:
            t = hotkeys_api.target(r, action["target"])
            reading = _reading(r, action["target"])
            after = scenes.capture(reading, scenes.settable(t.control, t.settable), t.apps)
        except Exception as exc:
            return f"Can't be put back: couldn't tell how it ended up ({exc})"
        if scenes.matches(state, reading):
            return "Nothing to put back: it was already like that"
        due = clock() + undo["after"] * 60 if "after" in undo else None
        r.add_undo(active.automation.uid, active.run_id, index, action["target"], state, after, due)
        with self._cond:
            self._revision += 1  # the scheduler works out when to look again
            self._cond.notify_all()
        return f"Will be put back after {automations.duration_label(undo['after'] * 60)}" if due else (
            "Will be put back when the Only if stops holding")

    def undo_check(self, r: Registry, now: float) -> None:
        """Put back what's due: an Action's Device after its minutes, or once its Automation's Only if
        stops holding (looked at every WHILE_EVERY, since that reads Devices)."""
        watch = now - self._while_at >= WHILE_EVERY - 1
        for u in r.undos():
            if self._closing:
                return
            if self._undo_retry.get(u.id, 0.0) > now:
                continue
            if u.due is not None:
                if u.due <= now:
                    self._put_back(r, u, now)
            elif watch and self._conditions_stopped(r, u):
                self._put_back(r, u, now)
        if watch:
            self._while_at = now

    def _conditions_stopped(self, r: Registry, u: Undo) -> bool:
        """Whether the Only if of an Undo's Automation is known not to hold any more (not while it can't
        be told: a Device that doesn't answer, someone whose phone isn't found yet)."""
        try:
            a = r.get_automation(u.automation)
        except LookupError:
            r.delete_undo(u.id)
            return False
        counts: dict[str, int] = {}
        if _unmet(r, a, counts) is None:
            return False
        return counts["no"] > 0 if a.match == "all" else counts["no"] == len(a.conditions)

    def _put_back(self, r: Registry, u: Undo, now: float) -> None:
        """Put a Device back to how it was, unless someone changed it since the Action did."""
        try:
            reading = _reading(r, u.target)
            if not scenes.matches(u.expected, reading):
                self._undone(r, u, "Left as it is: it had been changed since")
                return
            listening.acting([u.target], u.automation, 0)  # its own change never triggers it
            problem = scenes_api._send(r, {"target": u.target, "state": u.restore})
        except LookupError:
            self._undone(r, u, "Can't be put back: it was forgotten")
            return
        except Exception as exc:
            self._retry_undo(r, u, now, str(exc))
            return
        if problem.get("failed"):
            self._retry_undo(r, u, now, "; ".join(f["reason"] for f in problem["failed"].values()))
            return
        self._undone(r, u, "Put back to how it was")

    def _retry_undo(self, r: Registry, u: Undo, now: float, why: str) -> None:
        tries = self._undo_tries[u.id] = self._undo_tries.get(u.id, 0) + 1
        if tries < UNDO_TRIES:
            self._undo_retry[u.id] = now + RETRY_SECONDS
            return
        try:
            name = r.get_automation(u.automation).name
            self.notify(r, name, f"Couldn't put {scenes_api.name_of(r, u.target)} back: {why}", u.automation)
        except LookupError:
            pass
        self._undone(r, u, f"Couldn't be put back: {why}")

    def _undone(self, r: Registry, u: Undo, text: str) -> None:
        """Done with an Undo: forget it, and say what became of it on the step of the Run that made it."""
        r.delete_undo(u.id)
        self._undo_retry.pop(u.id, None)
        self._undo_tries.pop(u.id, None)
        run = next((x for x in r.runs(u.automation) if x.id == u.run), None)
        if run and u.step < len(run.steps):
            run.steps[u.step]["undo"] = text
            r.set_run_steps(run.id, run.steps)

    def undo_due(self, r: Registry) -> list[float]:
        """When to look at the Undos next: their times, and (for those waiting on an Only if) soon."""
        out = []
        for u in r.undos():
            retry = self._undo_retry.get(u.id, 0.0)
            out.append(max(retry, u.due) if u.due is not None else max(retry, self._while_at + WHILE_EVERY))
        return out

    def _chain(self, r: Registry, uid: str, active: _Active) -> str | None:
        """Start another Automation's Run, skipping its Conditions like a Run by hand, without waiting
        for it; what went wrong, or None."""
        if self._closing:  # stop() has already gathered the Runs to end
            return "Control quit"
        try:
            other = r.get_automation(uid)
        except LookupError:
            return "that Automation was deleted"
        cause = f"Run by {active.automation.name}"
        if self.stopped_loop(r, other, cause, active.hops + 1):
            return "stopped, since it may be a loop"
        self.run(r, uid, cause, by_hand=True, hops=active.hops + 1)
        return None

    def _set_scene(self, r: Registry, uid: str, active: _Active) -> str | None:
        """Set a Scene, which starts the Automations whose Trigger it is, one hop further down the
        chain; what went wrong, or None."""
        if self._closing:
            return "Control quit"
        try:
            sc = r.get_scene(uid)
            devices = [m for p in sc.parts
                       for m in (r.get_group(p["target"]).members if p["target"].startswith("group:") else [p["target"]])]
            listening.acting(devices, active.automation.uid, active.hops)
            out = scenes_api.apply(r, uid, hops=active.hops + 1)
        except LookupError:
            return "that Scene was deleted"
        except ValueError as exc:
            return str(exc)
        return "; ".join(f.reason for f in out.failed) or None

    def scene_set(self, r: Registry, scene: str, hops: int = 0) -> None:
        """A Scene was set (from anywhere): start the Runs of the Automations whose Trigger it is.
        `hops`: how far down a chain of Automations it was set (0: by a person)."""
        if self._closing:
            return
        names = _names(r)
        for a in r.automations():
            t = next((t for t in a.triggers if t["type"] == "scene" and t["target"] == scene), None)
            if not a.enabled or t is None:
                continue
            label = automations.trigger_label(t, names)
            if not self.stopped_loop(r, a, label, hops):
                self.run(r, a.uid, label, hops=hops)

    def pc_event(self, r: Registry, event: str) -> list[str]:
        """Something happened to this PC (`automations.PC_EVENTS`): start the Runs of the enabled
        Automations whose Trigger it is; their uids."""
        if self._closing:
            return []
        started = []
        for a in r.automations():
            t = next((t for t in a.triggers if t["type"] == "pc" and t["event"] == event), None)
            if a.enabled and t is not None:
                self.run(r, a.uid, automations.trigger_label(t, {}))
                started.append(a.uid)
        return started

    def stopped_loop(self, r: Registry, a: Automation, cause: str, hops: int) -> bool:
        """The loop guard (ADR 0012): a Run `hops` Automations down a chain, past MAX_HOPS, doesn't
        start. It's kept in the Automation's history as skipped, and a notice says so."""
        if hops <= listening_api.MAX_HOPS:
            return False
        why = f"{listening_api.MAX_HOPS} Automations had already set each other off in a row, so it may be a loop"
        steps = _not_run(r, a)
        r.update_run(r.add_run(a.uid, cause, outcome="skipped", steps=steps), steps, "skipped", why)
        self.notify(r, a.name, f"Didn't run on \"{cause}\": {why}", a.uid)
        return True

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


def _remember(r: Registry, uid: str) -> tuple[dict | None, str]:
    """How a Device is now, as a Scene part's state, before an Action changes it: (state, "") or
    (None, why not)."""
    try:
        t = hotkeys_api.target(r, uid)
        return scenes.capture(_reading(r, uid), scenes.settable(t.control, t.settable), t.apps), ""
    except Exception as exc:
        return None, str(exc)


def _unmet(r: Registry, a: Automation, counts: dict[str, int] | None = None) -> str | None:
    """None when the Conditions hold (all of them, or any one); otherwise which didn't, for the Run.
    `counts` gets how many were "no" and how many couldn't be told, for what waits on them."""
    counts = {} if counts is None else counts
    counts.update(no=0, unsure=0)
    now = _local(clock())
    where = location(r)
    names = _names(r)
    unmet = []
    for c in a.conditions:
        label = automations.condition_label(c, names, _app_names(r, c.get("target")))
        if c["type"] in automations.PRESENCE:
            holds = people_api.holds(c)
            if holds is None:
                counts["unsure"] += 1
                unmet.append(f"{label}: couldn't tell yet (Control is still looking for the phones)")
                continue
        elif c["type"] == "scene":
            try:
                holds = scenes_api.is_active(r, c["target"]) == c["active"]
            except Exception as exc:
                counts["unsure"] += 1
                unmet.append(f"{label}: couldn't tell ({exc})")
                continue
        elif c["type"] in ("state", "app"):
            try:
                state = _reading(r, c["target"])["state"]
            except Exception as exc:  # a Device that doesn't answer can't be said to be on
                counts["unsure"] += 1
                unmet.append(f"{label}: couldn't tell ({exc})")
                continue
            holds = bool(state.get("on")) == c["on"] if c["type"] == "state" else (
                bool(state.get("on")) and state.get("app") == c["app"])
        else:
            holds = automations.time_condition(c, now, where)
        if holds and a.match == "any":
            return None
        if not holds:
            counts["no"] += 1
            unmet.append(f"{label}: no")
    if not unmet:
        return None
    return "Only if " + ("none held: " if a.match == "any" else "") + "; ".join(unmet)


# --- Labels ------------------------------------------------------------------------------


def _names(r: Registry) -> dict[str, str]:
    names = {d.uid: d.name for d in r.all()}
    names |= {d.uid: d.name for d in r.remotes()}
    names |= {g.uid: g.name for g in r.groups()}
    names |= {a.uid: a.name for a in r.automations()}
    names |= {sc.uid: sc.name for sc in r.scenes()}
    names |= {p.uid: p.name for p in r.people()}
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
    """What `hotkeys_api` takes: the Action without the Device it's for or what happens afterwards."""
    return {k: v for k, v in action.items() if k not in ("target", "undo")}


# --- Checking ---------------------------------------------------------------------------


def _checked_target(r: Registry, uid: str) -> hotkeys_api.Target:
    if uid.startswith(("automation:", "scene:", "person:")):  # only a run Action, or a Scene part, names one
        raise ValueError(f"there's no Device or Group '{uid}'")
    try:
        return hotkeys_api.target(r, uid)
    except LookupError:
        raise ValueError(f"there's no Device or Group '{uid}'") from None


def _check_on_off(t: hotkeys_api.Target) -> None:
    if "on" not in t.settable:
        why = "only has a Power Toggle, so Control can't tell" if t.buttons.get("power") else "can't say"
        raise ValueError(f"'{t.name}' {why} whether it's on")


def _check_scene(r: Registry, uid: str) -> None:
    if not uid.startswith("scene:"):
        raise ValueError("pick a Scene")
    try:
        r.get_scene(uid)
    except LookupError:
        raise ValueError(f"there's no Scene '{uid}'") from None


def _check_presence(r: Registry, part: dict) -> None:
    """A Presence Trigger or Condition needs a Person with a phone: nobody else is ever home."""
    people = r.people()
    if part["type"] == "person":
        person = next((p for p in people if p.uid == part["target"]), None)
        if person is None:
            raise ValueError(f"there's no Person '{part['target']}'")
        if not person.phones:
            raise ValueError(f"mark {person.name}'s phone first (Settings → People), so Control can tell when "
                             "they're home")
    elif not any(p.phones for p in people):
        raise ValueError("add the people who live here and their phones first (Settings → People)")


def _check_trigger(r: Registry, t: dict, where) -> dict:
    clean = automations.check_trigger(t, where)
    if clean["type"] in automations.PRESENCE:
        _check_presence(r, clean)
    if clean["type"] == "scene":
        _check_scene(r, clean["target"])
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
    if clean["type"] in automations.PRESENCE:
        _check_presence(r, clean)
    if clean["type"] == "scene":
        _check_scene(r, clean["target"])
    if clean["type"] == "state":
        _check_on_off(_checked_target(r, clean["target"]))
    if clean["type"] == "app":
        _check_streamer(_checked_target(r, clean["target"]))
    return clean


def _check_action(r: Registry, a: dict) -> dict:
    clean = automations.check_step(a)
    if a.get("undo") is not None and clean["do"] not in automations.UNDOABLE:
        automations.check_undo(a["undo"], clean["do"])  # says what can't be put back
    if clean["do"] == "run":
        uid = clean["target"]
        if not uid.startswith("automation:"):
            raise ValueError("only an Automation runs; pick one")
        try:
            r.get_automation(uid)
        except LookupError:
            raise ValueError(f"there's no Automation '{uid}'") from None
        return {"do": "run", "target": uid}
    if clean["do"] == "set_scene":
        _check_scene(r, clean["target"])
        return {"do": "set_scene", "target": clean["target"]}
    if clean["do"] in automations.CONTROL:
        t = _checked_target(r, a["target"])
        out = hotkeys_api.check_action(r, t, _without_target(a)) | {"target": t.uid}
        if a.get("undo") is not None:
            undo = automations.check_undo(a["undo"], clean["do"])
            if t.is_group:
                raise ValueError(f"'{t.name}' is a Group: only one device at a time can be put back")
            if "on" not in t.settable:
                _check_on_off(t)  # says why: only a Power Toggle, so Control can't tell how it was
            out["undo"] = undo
        return out
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


def check(r: Registry, triggers: list, conditions: list, actions: list, whole: bool = True,
          uid: str | None = None) -> tuple[list, list, list]:
    """The parts cleaned up, or ValueError naming the first one that's wrong. `whole`: it's to be
    saved, so it needs an Action. `uid`: the Automation they're for (none: a new one), which mustn't end
    up starting itself."""
    where = location(r)
    triggers = _numbered("Trigger", triggers, lambda t: _check_trigger(r, t, where))
    triggers = _with_link(r, triggers, uid)
    conditions = _numbered("Condition", conditions, lambda c: _check_condition(r, c, where))
    actions = _numbered("Action", actions, lambda a: _check_action(r, a))
    _check_loop(r, uid or NEW, triggers, actions)
    if whole:
        automations.check_counts(triggers, conditions, actions)
        if not conditions and (i := next((i for i, x in enumerate(actions, 1) if "while" in x.get("undo", {})), None)):
            raise ValueError(f"Action {i}: it can only be put back while the Only if holds if there is an Only if")
    return triggers, conditions, actions


def _with_link(r: Registry, triggers: list[dict], uid: str | None) -> list[dict]:
    """A web Trigger gets its secret: the Automation's own if it has one, else a new one (ADR 0016).
    At most one per Automation, since the link is what opens it."""
    webs = [i for i, t in enumerate(triggers) if t["type"] == "web"]
    if not webs:
        return triggers
    if len(webs) > 1:
        raise ValueError(f"Trigger {webs[1] + 1}: an Automation has one web link")
    token = None
    if uid:
        try:
            token = next((t["token"] for t in r.get_automation(uid).triggers if t["type"] == "web"), None)
        except LookupError:
            pass
    return [t | {"token": token or secrets.token_urlsafe(32)} if t["type"] == "web" else t for t in triggers]


def _check_loop(r: Registry, uid: str, triggers: list[dict], actions: list[dict]) -> None:
    """ValueError when the Actions would start this Automation again, itself or through others: by
    running them, or by setting a Scene that is their Trigger."""
    others = {a.uid: a for a in r.automations() if a.uid != uid}
    set_off = automations.set_off_by({u: a.triggers for u, a in others.items()} | {uid: triggers})
    path = automations.loop(uid, actions, {u: a.actions for u, a in others.items()}, set_off)
    if path is None:
        return
    i, first = next((i, x) for i, x in enumerate(actions, 1) if path[1] in automations.starts(x, set_off))
    names = _names(r)
    if len(path) == 2:
        if first["do"] == "run":
            raise ValueError(f"Action {i}: an Automation can't run itself")
        raise ValueError(f"Action {i}: setting {names.get(first['target'], first['target'])} starts this "
                         "Automation again, since that's one of its Triggers")
    chain = " → ".join(names.get(x, x) for x in path[1:-1])
    runs_only = all(
        nxt in [a["target"] for a in (actions if x == uid else others[x].actions) if a["do"] == "run"]
        for x, nxt in zip(path, path[1:])
    )
    if runs_only:
        raise ValueError(f"Action {i}: {chain} runs this one again, so they'd run each other in a loop")
    raise ValueError(f"Action {i}: {chain} starts this one again, by running it or setting a Scene it "
                     "starts on, so they'd start each other in a loop")


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
    web_link: str | None = Field(description="the address that starts it, when it has a web Trigger; anyone on the "
                                             "home network who has it can start the Automation")
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
        made_by=a.made_by, web_link=_web_link(a), running=runner.running(a.uid), last_run=_run_out(last) if last else None,
        next_run=next_run,
    )


def _web_link(a: Automation) -> str | None:
    token = next((t["token"] for t in a.triggers if t["type"] == "web"), None)
    if token is None:
        return None
    return f"{lan.listener.url or LOCAL_URL}{HOOKS}{token}"


def _mid_sentence(label: str) -> str:
    """A part's label inside the summary: "At 07:00" becomes "at 07:00", but a Device's name keeps its case."""
    first, _, rest = label.partition(" ")
    return f"{first.lower()} {rest}" if first in ("At", "Between", "It's", "The", "Someone", "Nobody", "You") else label


def _summary(match: str, triggers: list[dict], conditions: list[dict], actions: list[dict]) -> str:
    when = " or ".join(_mid_sentence(t["label"]) for t in triggers) or "only when run by hand"
    text = f"When: {when}."
    if conditions:
        joiner = " and " if match == "all" else " or "
        text += " Only if " + joiner.join(_mid_sentence(c["label"]) for c in conditions) + "."
    return text + " Then: " + (", then ".join(a["label"] for a in actions) or "nothing yet") + "."


class PreviewIn(BaseModel):
    uid: str | None = Field(None, description="the Automation being edited, so it isn't made to run itself")
    triggers: list[dict] = Field(default_factory=list)
    conditions: list[dict] = Field(default_factory=list)
    match: str = "all"
    actions: list[dict] = Field(default_factory=list)


@router.post("/api/automations/preview")
def preview_automation(body: PreviewIn, r: Registry = Depends(registry)):
    """The builder's draft, checked and in plain language, without saving it: each part with its
    `label`, and the `summary`. A part that's wrong answers 422, naming it ("Action 2: …")."""
    triggers, conditions, actions = _labelled(r, *check(r, body.triggers, body.conditions, body.actions,
                                                                 whole=False, uid=body.uid))
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
        uid=uid,
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


# --- The PC ---------------------------------------------------------------------------------

PC_WAIT_AT_MOST = 3  # seconds a PC going to sleep or shutting down waits for its Runs


class PcEventIn(BaseModel):
    event: str = Field(description="wakes, unlocks, locks, sleeps or shuts_down (`starts` is Control's own)")
    wait: float = Field(0, description="seconds to hold the answer for the Runs it starts, at most "
                                       f"{PC_WAIT_AT_MOST}: Windows gives a PC going to sleep or shutting down "
                                       "only a moment")


@router.post("/api/pc-events", status_code=202)
def pc_event(body: PcEventIn, request: Request, r: Registry = Depends(registry)):
    """The Desktop App says Windows did something to the PC: starts the Automations whose Trigger it
    is. Only the computer running Control can say so."""
    if not request.state.local:
        raise HTTPException(status_code=403, detail="only the computer running Control")
    if body.event not in automations.PC_EVENTS or body.event == "starts":
        raise HTTPException(status_code=422, detail=f"a PC event is one of: "
                            f"{', '.join(e for e in automations.PC_EVENTS if e != 'starts')}")
    started = runner.pc_event(r, body.event)
    deadline = time.monotonic() + min(max(body.wait, 0), PC_WAIT_AT_MOST)
    for uid in started:
        runner.join(uid, max(deadline - time.monotonic(), 0))
    return {"started": started}


# --- Web links ------------------------------------------------------------------------------

_guesses: dict[str, list[float]] = {}


def _held_off(ip: str) -> bool:
    now = time.monotonic()
    recent = [t for t in _guesses.get(ip, []) if now - t < GUESSES[1]]
    _guesses[ip] = recent
    return len(recent) >= GUESSES[0]


def _guessed(ip: str) -> None:
    _guesses.setdefault(ip, []).append(time.monotonic())
    if len(_guesses) > 1000:  # a scan from many addresses mustn't grow this for ever
        for k in [k for k, v in _guesses.items() if time.monotonic() - max(v, default=0) > GUESSES[1]]:
            del _guesses[k]


@router.api_route(HOOKS + "{token}", methods=["GET", "POST"], include_in_schema=False)
def open_web_link(token: str, request: Request, r: Registry = Depends(registry)):
    """A web link (ADR 0016): starts the Automation whose web Trigger has this secret, checking its
    Conditions like any Trigger. Open to anyone on the home network who has the secret, no Approved
    Browser needed, so a bookmark, an NFC tag or a Shortcut can use it. A browser (Accept: text/html)
    gets a small page, anything else JSON."""
    ip = request.client.host if request.client else ""
    if _held_off(ip):
        return _link_answer(request, 429, "Too many wrong links. Try again in a minute.")
    found = next((a for a in r.automations()
                  if any(t["type"] == "web" and hmac.compare_digest(t["token"], token) for t in a.triggers)), None)
    if found is None:
        _guessed(ip)
        return _link_answer(request, 404, "There's no such link. It may have been renewed or deleted.")
    if not found.enabled:
        return _link_answer(request, 409, f"{found.name} is switched off.")
    runner.run(r, found.uid, automations.trigger_label({"type": "web"}, {}))
    return _link_answer(request, 202, f"Started {found.name}.", found.name)


def _link_answer(request: Request, status: int, message: str, automation: str | None = None):
    if "text/html" in request.headers.get("accept", ""):
        from html import escape

        page = (f'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                f'<title>Control</title><body style="font:20px system-ui;margin:3rem 1.5rem;text-align:center">'
                f"<p>{escape(message)}</p>")
        return HTMLResponse(page, status_code=status)
    return JSONResponse(status_code=status, content={"detail" if status >= 400 else "started": automation or message})


@router.post("/api/automations/{uid}/web-link/renew", response_model=AutomationOut)
def renew_web_link(uid: str, r: Registry = Depends(registry)):
    """A new secret: the old link stops working."""
    a = r.get_automation(uid)
    if not any(t["type"] == "web" for t in a.triggers):
        raise ValueError("this Automation has no web link")
    r.update_automation(uid, triggers=[t | {"token": secrets.token_urlsafe(32)} if t["type"] == "web" else t
                                       for t in a.triggers])
    return get_automation(uid, r)


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
