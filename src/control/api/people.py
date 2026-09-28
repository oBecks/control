"""People and Presence (ADR 0014): who lives in the home, their phones, and who's home now.

The presence thread runs only while some phone is marked. Every CHECK_EVERY seconds it nudges each
marked phone where it answered last, waits for Windows to ask for their MACs, and reads the
neighbour table (`engine/neighbors.py`). What changes (someone arrives or leaves, the first arrives
or the last leaves) starts the Automations whose Trigger it is.

A phone may come back on a new IP (the router restarted, its lease ran out), so Control also looks
on every address of the home subnet (a sweep): at once when it starts, when this PC's address
changes and when the network comes back; and for a phone missing SWEEP_AFTER, then every
SWEEP_BACKOFF while it stays missing, which keeps the network quiet while someone is away all day.

While Control can't see the network (this PC has no address on it, or the router doesn't answer:
it's nudged with the phones, since an idle PC's entry for it goes stale too), nobody is home or away: everyone becomes unknown until it sees again, so a power cut
doesn't make everyone leave.

Anyone who may use the Engine may set People up, phones included, like Groups. "This is my phone"
only works from the phone itself, since Control reads its MAC from the address the request came
from.
"""

import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import closing

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..engine import automations, neighbors
from ..engine.presence import Change, Tracker
from ..engine.registry import Person, Registry
from . import access, lan
from .deps import registry
from .listening import awake

router = APIRouter(prefix="/api/people")

CHECK_EVERY = 30  # seconds between looks for the marked phones
SWEEP_AFTER = 5 * 60  # a phone missing this long is looked for across the subnet
SWEEP_BACKOFF = 30 * 60  # and again this often while it stays missing
NAMES_WAIT = 2  # seconds the nearby list waits for the router to name devices
SWEEP_SHARED = 15  # seconds a nearby sweep's answers serve anyone else who asks meanwhile


def _automations_api():
    from . import automations as automations_api

    return automations_api


class Presence:
    def __init__(self):
        self.tracker = Tracker()
        self._lock = threading.Condition()
        self._thread: threading.Thread | None = None
        self._closing = False
        self._revision = 0
        self._ips: dict[str, str] = {}  # phone -> where it answered last
        self._swept = 0.0  # awake seconds of the last sweep
        self._sweeps = 0  # sweeps since every phone last answered
        self._own: list[str] | None = None  # this PC's addresses at the last look; None: not looked yet
        self._blind = False  # the last look couldn't see the network

    def start(self) -> None:
        with self._lock:
            self._closing = False
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop, name="presence", daemon=True)
                self._thread.start()
        self.sync()

    def stop(self) -> None:
        with self._lock:
            self._closing = True
            self._lock.notify_all()
            thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=neighbors.SETTLE + 5)

    def sync(self) -> None:
        """People or phones changed: look for what's marked now, at once."""
        with closing(Registry()) as r:
            people = r.people()
        with self._lock:
            self.tracker.set_phones({p.uid: [ph.mac for ph in p.phones] for p in people}, awake())
            self._ips = {ph.mac: ph.ip for p in people for ph in p.phones}
            self._revision += 1
            self._lock.notify_all()

    def _loop(self) -> None:
        while True:
            with self._lock:
                if self._closing:
                    return
                revision = self._revision
                if not self._ips:
                    self._lock.wait()  # nothing marked: sleep until something is
                    continue
                ips = dict(self._ips)
            try:
                self.check(ips)
            except Exception as exc:  # one bad look mustn't stop presence
                print(f"Presence: looking for phones failed: {exc!r}", file=sys.stderr)
            with self._lock:
                if self._revision == revision and not self._closing:
                    self._lock.wait(CHECK_EVERY)

    def check(self, ips: dict[str, str]) -> None:
        """One look: nudge, wait, read, and act on what changed."""
        now = awake()
        own, router = lan.lan_ips(), neighbors.gateway()
        if not own or router is None:
            self._go_blind(now)
            return
        targets = {ip for ip in ips.values() if ip} | {router}
        if self._sweep_due(now, own):
            self._swept = now
            self._sweeps += 1
            targets |= set(neighbors.subnet_hosts(own))
        self._own, self._blind = own, False
        neighbors.nudge(targets)
        if self._sleep(neighbors.SETTLE):
            return
        table = neighbors.table()
        if not any(n.reachable and n.ip == router for n in table):
            self._go_blind(awake())  # the router didn't answer: the network is down, not everyone gone
            return
        answered = {n.mac: n.ip for n in table if n.reachable and n.mac in ips}
        with closing(Registry()) as r:
            for mac, ip in answered.items():
                if ips[mac] != ip:
                    r.phone_moved(mac, ip)
                    with self._lock:
                        if mac in self._ips:
                            self._ips[mac] = ip
            with self._lock:
                changes = self.tracker.update(set(answered), awake())
            if changes:
                started(r, changes)

    def _sweep_due(self, now: float, own: list[str]) -> bool:
        """Whether this look covers the whole subnet (see the module's docstring)."""
        if self._own is None or self._blind or own != self._own:
            return True  # Control just started, the network came back, or this PC moved
        with self._lock:
            missing = self.tracker.missing(now, SWEEP_AFTER)
        if not missing:
            self._sweeps = 0
            return False
        return self._sweeps == 0 or now - self._swept >= SWEEP_BACKOFF

    def _go_blind(self, now: float) -> None:
        if not self._blind:
            print("Presence: can't see the home network; nobody counts as home or away until it's back",
                  file=sys.stderr)
        self._blind = True
        with self._lock:
            self.tracker.blind(now)

    def _sleep(self, seconds: float) -> bool:
        """Wait, unless Control is quitting (True)."""
        with self._lock:
            self._lock.wait_for(lambda: self._closing, seconds)
            return self._closing

    def home(self, uid: str) -> bool | None:
        with self._lock:
            return self.tracker.home(uid)

    def anyone(self) -> bool | None:
        with self._lock:
            return self.tracker.anyone()

    def seen(self, mac: str) -> float | None:
        """When a phone last answered, as a wall-clock time."""
        with self._lock:
            at = self.tracker.seen(mac)
        return None if at is None else time.time() - (awake() - at)


presence = Presence()


def started(r: Registry, changes: list[Change]) -> None:
    """Start the Runs of the enabled Automations whose Presence Trigger just happened."""
    api = _automations_api()
    names = api._names(r)
    for a in r.automations():
        if not a.enabled:
            continue
        for t in a.triggers:
            if any(_fires(t, c) for c in changes):
                api.runner.run(r, a.uid, automations.trigger_label(t, names))
                break


def _fires(t: dict, c: Change) -> bool:
    if t["type"] == "person":
        return c.person == t["target"] and c.home == t["home"]
    if t["type"] == "home":
        return c.person is None and c.home == t["occupied"]
    return False


def holds(c: dict) -> bool | None:
    """Whether a Presence Condition holds now; None while not known."""
    value = presence.home(c["target"]) if c["type"] == "person" else presence.anyone()
    return None if value is None else value == (c["home"] if c["type"] == "person" else c["occupied"])


# --- Views ------------------------------------------------------------------------------


class PhoneOut(BaseModel):
    mac: str
    name: str
    ip: str
    private: bool = Field(description="a private (made-up) Wi-Fi address, as phones use")
    seen: float | None = Field(description="when it last answered, since Control started")
    current: bool = Field(description="the phone this browser runs on")


class PersonOut(BaseModel):
    uid: str
    name: str
    home: bool | None = Field(description="home, away, or null while not known yet")
    phones: list[PhoneOut]
    made_by: str


def _out(p: Person, request: Request | None = None) -> PersonOut:
    browser = request.state.browser.id if request is not None and request.state.browser else None
    return PersonOut(
        uid=p.uid, name=p.name, home=presence.home(p.uid), made_by=p.made_by,
        phones=[PhoneOut(mac=ph.mac, name=ph.name, ip=ph.ip, private=neighbors.is_private(ph.mac),
                         seen=presence.seen(ph.mac), current=browser is not None and ph.browser == browser)
                for ph in p.phones],
    )


def _name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("say who")
    return name


@router.get("", response_model=list[PersonOut])
def list_people(request: Request, r: Registry = Depends(registry)):
    return [_out(p, request) for p in r.people()]


class PersonIn(BaseModel):
    name: str
    by_assistant: bool = False


@router.post("", response_model=PersonOut, status_code=201)
def add_person(body: PersonIn, request: Request, r: Registry = Depends(registry)):
    uid = r.add_person(_name(body.name), "assistant" if body.by_assistant else "user")
    return _out(r.get_person(uid), request)


class PersonPatch(BaseModel):
    name: str


@router.patch("/{uid}", response_model=PersonOut)
def rename_person(uid: str, body: PersonPatch, request: Request, r: Registry = Depends(registry)):
    r.rename_person(uid, _name(body.name))
    return _out(r.get_person(uid), request)


@router.delete("/{uid}", status_code=204)
def delete_person(uid: str, r: Registry = Depends(registry)):
    r.forget_person(uid)
    presence.sync()
    _automations_api().runner.changed()  # the parts of Automations that named them


class PhoneIn(BaseModel):
    this_phone: bool = Field(False, description="the phone this browser runs on")
    mac: str | None = Field(None, description="a phone from /api/people/nearby")
    ip: str = ""
    name: str | None = None


@router.post("/{uid}/phones", response_model=PersonOut, status_code=201)
def add_phone(uid: str, body: PhoneIn, request: Request, r: Registry = Depends(registry)):
    r.get_person(uid)
    browser = None
    if body.this_phone:
        if request.state.local:
            raise ValueError("this is the computer running Control: open Control on the phone to mark it")
        ip = request.client.host if request.client else ""
        mac = next((n.mac for n in neighbors.table() if n.ip == ip), None)
        if mac is None:
            raise ValueError("Control can't see this phone's Wi-Fi address. Is it on the home Wi-Fi, "
                             "not mobile data or a VPN?")
        browser = request.state.browser
        name = body.name or access.browser_name(request.headers.get("user-agent", "")).split(" · ")[0]
    elif body.mac:
        mac, ip = neighbors.normal_mac(body.mac), body.ip
        name = body.name or "Phone"
    else:
        raise ValueError("say which phone")
    if mac in {d.mac.lower().replace("-", ":") for d in r.all() if d.mac}:
        raise ValueError("that's one of your Devices, not a phone")
    r.add_phone(uid, mac, name.strip()[:40] or "Phone", ip, browser.id if browser else None)
    presence.sync()
    return _out(r.get_person(uid), request)


@router.delete("/{uid}/phones/{mac}", status_code=204)
def remove_phone(uid: str, mac: str, r: Registry = Depends(registry)):
    phone = r.phone(neighbors.normal_mac(mac))
    if phone is None or phone.person != uid:
        raise LookupError(f"no phone '{mac}' for that Person")
    r.forget_phone(phone.mac)
    presence.sync()


class NearbyOut(BaseModel):
    ip: str
    mac: str
    private: bool = Field(description="a private (made-up) Wi-Fi address: most likely a phone")
    name: str | None = Field(description="what the router calls it, if it says")
    browser: str | None = Field(description="the Approved Browser last seen at this address")


@router.get("/nearby", response_model=list[NearbyOut])
def nearby(r: Registry = Depends(registry)):
    """What answers on the home network now, to pick a phone from: a sweep of the subnet (takes a few
    seconds). Devices Control knows, and phones already marked, are left out. Private MACs first."""
    own = lan.lan_ips()
    table = _swept(own)
    known_ips = {d.ip for d in r.all()} | set(own)
    known_macs = {d.mac.lower().replace("-", ":") for d in r.all() if d.mac}
    known_macs |= {ph.mac for p in r.people() for ph in p.phones}
    found = {n.mac: n for n in table
             if n.reachable and n.ip not in known_ips and n.mac not in known_macs}
    names = _host_names([n.ip for n in found.values()])
    out = [NearbyOut(ip=n.ip, mac=n.mac, private=neighbors.is_private(n.mac), name=names.get(n.ip),
                     browser=access.browser_at(n.ip)) for n in found.values()]
    return sorted(out, key=lambda n: (n.browser is None, not n.private, tuple(int(x) for x in n.ip.split("."))))


_sweep_lock = threading.Lock()
_last_sweep: tuple[float, list[neighbors.Neighbor]] = (0.0, [])


def _swept(own: list[str]) -> list[neighbors.Neighbor]:
    """Sweep the subnet, once at a time: a second browser asking meanwhile waits for the sweep going
    on and gets its answers, rather than holding another worker and sending every packet again."""
    global _last_sweep
    with _sweep_lock:
        at, table = _last_sweep
        if time.monotonic() - at < SWEEP_SHARED:
            return table
        neighbors.nudge(neighbors.subnet_hosts(own))
        time.sleep(neighbors.SETTLE)
        _last_sweep = (time.monotonic(), neighbors.table())
        return _last_sweep[1]


def _host_names(ips: list[str]) -> dict[str, str]:
    """What the router's DNS calls each address, for as long as NAMES_WAIT allows."""
    if not ips:
        return {}
    pool = ThreadPoolExecutor(max_workers=16)
    futures = {pool.submit(_host_name, ip): ip for ip in ips}
    done, _ = wait(futures, timeout=NAMES_WAIT)
    pool.shutdown(wait=False, cancel_futures=True)
    return {futures[f]: f.result() for f in done if f.result()}


def _host_name(ip: str) -> str | None:
    try:
        name = socket.gethostbyaddr(ip)[0]
    except OSError:
        return None
    name = name.split(".")[0]
    return None if not name or name == ip else name
