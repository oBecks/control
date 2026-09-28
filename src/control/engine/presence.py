"""Presence (ADR 0014): which People are home, from their phones answering on the home network.

A Person is home while one of their phones was seen in the last AWAY_AFTER seconds, and away once
none has been for that long. Until then (Control just started, a phone was just marked) they're
unknown, and leaving unknown fires nothing: only changes count, as with listening (ADR 0011). Time
is the PC's awake time, so sleeping doesn't make everyone leave.

Everyone together: someone is home while any Person is; nobody is home once every Person is away;
otherwise it's unknown.

This module only keeps the count. Looking for the phones is `neighbors`; the thread that does it and
starts the Automations is `api/people.py`.
"""

from dataclasses import dataclass

AWAY_AFTER = 10 * 60  # seconds without a phone answering


@dataclass(frozen=True)
class Change:
    """A Person arrived (home True) or left; person None: the first arrived or the last left."""

    person: str | None
    home: bool


class Tracker:
    def __init__(self):
        self._owner: dict[str, str] = {}  # phone MAC -> Person uid
        self._since: dict[str, float] = {}  # phone -> when it was first looked for (awake seconds)
        self._seen: dict[str, float] = {}  # phone -> when it last answered
        self._people: list[str] = []
        self._home: dict[str, bool | None] = {}
        self._anyone: bool | None = None

    def set_phones(self, people: dict[str, list[str]], now: float) -> None:
        """The People (uid -> their phones' MACs) as saved now. A phone just marked starts unknown."""
        owner = {mac: uid for uid, macs in people.items() for mac in macs}
        for mac in owner.keys() - self._owner.keys():
            self._since[mac] = now
        for mac in self._owner.keys() - owner.keys():
            self._since.pop(mac, None)
            self._seen.pop(mac, None)
        self._owner = owner
        self._people = list(people)
        self._home = {uid: self._home.get(uid) for uid in people}
        self.update(set(), now)  # a Person's phones changed: they may now be known (fires nothing new)

    def phones(self) -> set[str]:
        return set(self._owner)

    def missing(self, now: float, after: float) -> set[str]:
        """Phones that haven't answered for `after` seconds, to look for on other addresses."""
        return {mac for mac in self._owner if now - self._seen.get(mac, self._since[mac]) >= after}

    def update(self, answered: set[str], now: float) -> list[Change]:
        """Phones that answered just now (any MACs; others are ignored): what changed."""
        for mac in answered & self._owner.keys():
            self._seen[mac] = now
        changes = []
        for uid in self._people:
            was, is_ = self._home.get(uid), self._person(uid, now)
            self._home[uid] = is_
            if was is not None and is_ is not None and was != is_:
                changes.append(Change(uid, is_))
        was, is_ = self._anyone, self.anyone()
        self._anyone = is_
        if was is not None and is_ is not None and was != is_:
            changes.append(Change(None, is_))
        return changes

    def home(self, uid: str) -> bool | None:
        """Whether a Person is home; None while not known (or not a Person)."""
        return self._home.get(uid)

    def anyone(self) -> bool | None:
        values = [self._home.get(uid) for uid in self._people]
        if any(values):
            return True
        if values and all(v is False for v in values):
            return False
        return None

    def seen(self, mac: str) -> float | None:
        """When a phone last answered (awake seconds), or None."""
        return self._seen.get(mac)

    def _person(self, uid: str, now: float) -> bool | None:
        macs = [mac for mac, owner in self._owner.items() if owner == uid]
        if not macs:
            return None  # a Person without phones is never known
        if any(now - self._seen[mac] < AWAY_AFTER for mac in macs if mac in self._seen):
            return True
        if all(now - self._seen.get(mac, self._since[mac]) >= AWAY_AFTER for mac in macs):
            return False
        return None
