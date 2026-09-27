"""Listening to Devices for Automations' Device Triggers (ADR 0011): a Device or Group turns on or
off (and stays so for N minutes), a Streamer opens an app, a Device goes Offline or comes back online.

Only the Devices named by a Device Trigger of an enabled Automation are listened to (a Group's
members when it names a Group), and nothing at all when there are none. Each brand pushes changes
over a connection it keeps open (`connect.watch`); Remote Devices change only when Control sends
them a Signal, so `app.py` reports those (`controlled`). Everything is handled in order on one
thread, which sleeps while nothing happens.

Rules decided with the user (2026-09-27):
- Only changes count. The first reading after listening starts (Control starting, an Automation
  switched on) fires nothing, but "stays on for 30 min" counts from then if it's already on.
- A Device counts as Offline after OFFLINE_AFTER seconds without an answer; any answer brings it back.
- A Streamer's screensaver isn't leaving the app: Netflix, screensaver, Netflix opens Netflix once.
- The loop guard (ADR 0012): an Automation's own changes never trigger it; a chain of Automations
  triggering each other stops after MAX_HOPS; one triggered more than MAX_PER_MINUTE times in a minute
  by Devices is switched off. Each says so in a notice.
"""

import queue
import sys
import threading
import time
from collections import deque
from contextlib import closing

from ..engine import automations, connect, streamer
from ..engine.registry import Automation, Registry

MINUTE = 60  # seconds (tests shorten it)
OFFLINE_AFTER = 60  # seconds without an answer
BY_AUTOMATION = 10  # seconds a change on a Device an Automation just controlled counts as its doing
MAX_HOPS = 5  # Automations triggering each other in a row
MAX_PER_MINUTE = 10  # Runs of one Automation started by Devices


def _automations_api():
    from . import automations as automations_api

    return automations_api


def _on(state: dict | None) -> bool | None:
    return None if state is None else state.get("on")


class Listening:
    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._watches: dict[str, connect.Watch | None] = {}  # None: a Remote Device, reported by app.py
        self._states: dict[str, dict] = {}  # uid -> {"on", "app"?} as last heard
        self._online: dict[str, bool] = {}
        self._lost: dict[str, threading.Timer] = {}  # counting to Offline
        self._stays: dict[tuple, threading.Timer] = {}  # (automation, index, trigger) -> counting "stays so"
        self._by: dict[str, tuple[str, int, float]] = {}  # device -> (automation, hops, until) it just controlled
        self._fired: dict[str, deque] = {}  # automation -> when Devices last started it
        self._automations: list[Automation] = []
        self._groups: dict[str, list[str]] = {}

    # --- From any thread ----------------------------------------------------------------------

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="listening", daemon=True)
            self._thread.start()
        self.sync()

    def stop(self) -> None:
        if self._thread is not None:
            self._queue.put(None)
            self._thread.join(timeout=5)
            self._thread = None

    def sync(self) -> None:
        """Automations, Groups or Devices changed: listen to what they name now."""
        if self._thread is not None:
            self._queue.put(("sync",))

    def seen(self, uid: str, state: dict | None) -> None:
        """A Device answered with its state, or (None) can't be reached."""
        self._queue.put(("seen", uid, state))

    def controlled(self, uid: str, state: dict) -> None:
        """Control sent a Remote Device a Signal: its Assumed State."""
        if self._thread is not None:
            self._queue.put(("seen", uid, state))

    def acting(self, uids: list[str], automation: str, hops: int) -> None:
        """An Automation's Run is about to control these Devices: changes they report are its doing."""
        if self._thread is not None:
            self._queue.put(("acting", uids, automation, hops))

    def idle(self) -> None:
        """Wait until everything so far is handled (tests)."""
        self._queue.join()

    def listened(self) -> set[str]:
        return set(self._watches)

    # --- The listening thread -------------------------------------------------------------------

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    self._close_all()
                    return
                getattr(self, f"_{item[0]}")(*item[1:])
            except Exception as exc:  # one bad event mustn't stop listening
                print(f"Listening: {item[0]} failed: {exc!r}", file=sys.stderr)
            finally:
                self._queue.task_done()

    def _later(self, seconds: float, *item) -> threading.Timer:
        timer = threading.Timer(seconds, self._queue.put, args=(item,))
        timer.daemon = True
        timer.start()
        return timer

    def _close_all(self) -> None:
        for w in self._watches.values():
            if w is not None:
                w.close()
        for timer in [*self._lost.values(), *self._stays.values()]:
            timer.cancel()
        self._watches.clear()
        self._lost.clear()
        self._stays.clear()

    def _sync(self) -> None:
        with closing(Registry()) as r:
            self._groups = {g.uid: list(g.members) for g in r.groups()}
            self._automations = [a for a in r.automations() if a.enabled and automations.listened(a)]
            wanted = {m for a in self._automations for target in automations.listened(a)
                      for m in self._groups.get(target, [target])}
            for uid in [u for u in self._watches if u not in wanted]:
                self._unwatch(uid)
            for uid in wanted - set(self._watches):
                self._watch(r, uid)
            for uid in self._watches:
                device = r.get(uid)
                if device is not None and self._online.get(uid) and uid not in self._lost and not device.online:
                    r.mark_online(uid)  # a Scan missed it, but it's answering us
        keys = {self._stay_key(a, i, t) for a in self._automations for i, t in enumerate(a.triggers)}
        for key in [k for k in self._stays if k not in keys]:
            self._stays.pop(key).cancel()
        # Count "stays so" from now for what's already so (a Device already heard, or a Remote Device).
        for a in self._automations:
            for i, t in enumerate(a.triggers):
                if t["type"] == "state" and t["minutes"] and self._value(t["target"]) == t["on"]:
                    self._stay(a, i, t, t["target"], restart=False)

    def _watch(self, r: Registry, uid: str) -> None:
        if uid.startswith("remote:"):
            try:
                assumed = r.resolve_remote(uid).assumed_state or {}
            except LookupError:
                return
            self._watches[uid] = None
            if assumed.get("on") is not None:
                self._states[uid] = {"on": assumed["on"]}
            return
        device = r.get(uid)
        if device is None:
            return
        self._online[uid] = device.online
        self._watches[uid] = connect.watch(r, device, self.seen)

    def _unwatch(self, uid: str) -> None:
        w = self._watches.pop(uid)
        if w is not None:
            w.close()
        if timer := self._lost.pop(uid, None):
            timer.cancel()
        self._states.pop(uid, None)
        self._online.pop(uid, None)

    def _acting(self, uids: list[str], automation: str, hops: int) -> None:
        until = time.monotonic() + BY_AUTOMATION
        for uid in uids:
            self._by[uid] = (automation, hops, until)

    def _seen(self, uid: str, state: dict | None) -> None:
        if uid not in self._watches:
            return  # no longer listened to
        if state is None:
            if uid not in self._lost and self._online.get(uid, True):
                self._lost[uid] = self._later(OFFLINE_AFTER, "offline", uid)
            return
        if timer := self._lost.pop(uid, None):
            timer.cancel()
        if self._online.get(uid) is False:
            self._online[uid] = True
            with closing(Registry()) as r:
                r.mark_online(uid)
            self._connection(uid, offline=False)
        self._online[uid] = True
        old = self._states.get(uid)
        if state.get("app") in streamer.SCREENSAVERS:
            state = state | {"app": old.get("app") if old else None}
        if state == old:
            return
        groups = [g for g, members in self._groups.items() if uid in members]
        before = {g: self._value(g) for g in groups}
        self._states[uid] = state
        after = {g: self._value(g) for g in groups}
        for a in list(self._automations):
            for i, t in enumerate(a.triggers):
                target = t.get("target")
                if t["type"] == "state" and target == uid:
                    was = _on(old)
                    if was is None and self._watches[uid] is None:
                        was = not _on(state)  # Control just set a Remote Device for the first time: a change
                    self._state_changed(a, i, t, was, _on(state), uid)
                elif t["type"] == "state" and target in before:
                    self._state_changed(a, i, t, before[target], after[target], uid)
                elif t["type"] == "app" and target == uid and old is not None:
                    if state.get("app") == t["app"] and old.get("app") != t["app"]:
                        self._fire(a, t, uid)

    def _offline(self, uid: str) -> None:
        if self._lost.pop(uid, None) is None or uid not in self._watches:
            return  # it answered meanwhile
        if self._online.get(uid) is False:
            return
        self._online[uid] = False
        with closing(Registry()) as r:
            r.mark_offline(uid)
        self._connection(uid, offline=True)

    def _connection(self, uid: str, offline: bool) -> None:
        for a in list(self._automations):
            for t in a.triggers:
                if t["type"] == "offline" and t["target"] == uid and t["offline"] == offline:
                    self._fire(a, t, uid)

    # --- State Triggers -------------------------------------------------------------------------

    def _value(self, target: str) -> bool | None:
        """Whether a Device or Group is on; None while not known. A Group is on while any member is;
        it's known once every member is, leaving out members that are Offline or never set."""
        if target not in self._groups:
            return _on(self._states.get(target))
        values = []
        for m in self._groups[target]:
            value = _on(self._states.get(m))
            if value is None and (self._watches.get(m) is None or self._online.get(m) is False):
                continue  # a Remote Device Control hasn't set yet, or an Offline Device
            if value is None:
                return None
            values.append(value)
        return any(values) if values else None

    def _state_changed(self, a: Automation, i: int, t: dict, was: bool | None, now: bool | None, uid: str) -> None:
        key = self._stay_key(a, i, t)
        if now != t["on"]:
            if timer := self._stays.pop(key, None):
                timer.cancel()
            return
        if was is None:  # the first reading: nothing changed, but "stays so" counts from now
            if t["minutes"]:
                self._stay(a, i, t, uid, restart=False)
            return
        if was == now:
            return
        if t["minutes"]:
            self._stay(a, i, t, uid, restart=True)
        else:
            self._fire(a, t, uid)

    @staticmethod
    def _stay_key(a: Automation, i: int, t: dict) -> tuple:
        return a.uid, i, repr(sorted(t.items()))

    def _stay(self, a: Automation, i: int, t: dict, uid: str, restart: bool) -> None:
        key = self._stay_key(a, i, t)
        if key in self._stays:
            if not restart:
                return
            self._stays.pop(key).cancel()
        self._stays[key] = self._later(t["minutes"] * MINUTE, "stayed", key, uid)

    def _stayed(self, key: tuple, uid: str) -> None:
        if self._stays.pop(key, None) is None:
            return  # cancelled meanwhile
        a = next((a for a in self._automations if a.uid == key[0]), None)
        if a is None or key[1] >= len(a.triggers):
            return
        t = a.triggers[key[1]]
        if self._value(t["target"]) == t["on"]:
            self._fire(a, t, uid)

    # --- Starting Runs, with the loop guard -------------------------------------------------------

    def _fire(self, a: Automation, t: dict, uid: str) -> None:
        api = _automations_api()
        now = time.monotonic()
        hops = 0
        by = self._by.get(uid)
        if by and by[2] > now:
            if by[0] == a.uid:
                return  # its own change
            hops = by[1] + 1
        with closing(Registry()) as r:
            label = automations.trigger_label(t, api._names(r), api._app_names(r, t.get("target")))
            if hops > MAX_HOPS:
                api.runner.notify(r, a.name, f"Didn't run on \"{label}\": {MAX_HOPS} Automations had already "
                                  "set each other off in a row, so it may be a loop", a.uid)
                return
            fired = self._fired.setdefault(a.uid, deque())
            while fired and now - fired[0] > MINUTE:
                fired.popleft()
            fired.append(now)
            if len(fired) > MAX_PER_MINUTE:
                r.switch_off(a.uid, f"Switched off: its Devices set it off more than {MAX_PER_MINUTE} times in a "
                                    "minute, so it may be in a loop with another Automation")
                api.runner.notify(r, a.name, "Switched off: it kept being set off, maybe in a loop", a.uid)
                self._fired.pop(a.uid, None)
                self._automations = [x for x in self._automations if x.uid != a.uid]
                api.runner.changed()
                return
            api.runner.run(r, a.uid, label, hops=hops)


listening = Listening()
