"""TVs and streaming boxes, found over mDNS (Bonjour).

Android TV / Google TV devices announce `_androidtvremote2._tcp`; most also announce Google Cast
(`_googlecast._tcp`), whose record carries the model ("SHIELD Android TV", "yes"). Boxes Control can't
control yet are shown as Unsupported: Apple TV (AirPlay), Fire TV (Amazon's `_amzn-wplay`) and
Cast-only devices such as older Chromecasts and Nest speakers.
"""

import threading
import time
from dataclasses import dataclass

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

from ..found_device import Category, FoundDevice, Readiness

ANDROID_TV = "_androidtvremote2._tcp.local."
CAST = "_googlecast._tcp.local."
AIRPLAY = "_airplay._tcp.local."
FIRE_TV = "_amzn-wplay._tcp.local."

# mDNS answers arrive within a second or two; longer only waits for nothing.
_MAX_WAIT = 4.0


@dataclass
class Service:
    type: str
    name: str  # the instance name, e.g. "SHIELD" or "TV – סלון"
    ip: str
    txt: dict[str, str]


def browse(types: list[str], timeout: float) -> list[Service]:
    zc = Zeroconf()
    names: list[tuple[str, str]] = []

    class Listener(ServiceListener):
        def add_service(self, zc, type_, name):
            names.append((type_, name))

        def update_service(self, zc, type_, name):
            pass

        def remove_service(self, zc, type_, name):
            pass

    try:
        browsers = [ServiceBrowser(zc, t, Listener()) for t in types]
        time.sleep(min(timeout, _MAX_WAIT))
        found = []
        for type_, name in dict.fromkeys(names):
            info = zc.get_service_info(type_, name, 2000)
            if info is None:
                continue
            ips = [a for a in info.parsed_addresses() if ":" not in a]  # IPv4 only
            if not ips:
                continue
            txt = {k.decode(errors="replace"): (v or b"").decode(errors="replace") for k, v in info.properties.items()}
            found.append(Service(type_, name.removesuffix("." + type_), ips[0], txt))
        for b in browsers:
            b.cancel()
        return found + _ask_missing_android_tvs(zc, found) if ANDROID_TV in types else found
    finally:
        zc.close()


def _ask_missing_android_tvs(zc: Zeroconf, found: list[Service]) -> list[Service]:
    """A browse can miss an announcement. An Android TV's instance name is its Cast name, so ask
    for it directly for every Cast device that didn't show up as one."""
    android = {s.ip for s in found if s.type == ANDROID_TV}
    extra = []
    for s in found:
        if s.type != CAST or s.ip in android or not s.txt.get("fn"):
            continue
        info = zc.get_service_info(ANDROID_TV, f"{s.txt['fn']}.{ANDROID_TV}", 1500)
        if info is None:
            continue
        txt = {k.decode(errors="replace"): (v or b"").decode(errors="replace") for k, v in info.properties.items()}
        extra.append(Service(ANDROID_TV, s.txt["fn"], s.ip, txt))
    return extra


def android_tvs(services: list[Service]) -> list[FoundDevice]:
    cast = {s.ip: s for s in services if s.type == CAST}
    found = []
    for s in services:
        if s.type != ANDROID_TV:
            continue
        ident = s.txt.get("bt") or cast.get(s.ip, Service("", "", "", {"id": s.ip})).txt.get("id", s.ip)
        model = cast[s.ip].txt.get("md", "") if s.ip in cast else ""
        found.append(FoundDevice(
            brand="Android TV", ip=s.ip, uid=f"androidtv:{ident.lower()}", category=Category.MEDIA,
            readiness=Readiness.NEEDS_LINK, name=s.name, model=model, raw={"txt": s.txt},
        ))
    return found


def unsupported(services: list[Service]) -> list[FoundDevice]:
    android = {s.ip for s in services if s.type == ANDROID_TV}
    found = []
    for s in services:
        if s.type == AIRPLAY and s.txt.get("model", "").startswith("AppleTV"):
            brand, uid, model = "Apple TV", f"appletv:{s.txt.get('deviceid', s.ip).lower()}", s.txt["model"]
        elif s.type == FIRE_TV:
            brand, uid, model = "Fire TV", f"firetv:{s.name}", ""
        elif s.type == CAST and s.ip not in android:
            brand, uid, model = "Google Cast", f"cast:{s.txt.get('id', s.ip)}", s.txt.get("md", "")
            s = Service(s.type, s.txt.get("fn") or s.name, s.ip, s.txt)
        else:
            continue
        found.append(FoundDevice(
            brand=brand, ip=s.ip, uid=uid, category=Category.MEDIA, readiness=Readiness.UNSUPPORTED,
            name=s.name, model=model, note=f"{brand} isn't supported yet", raw={"txt": s.txt},
        ))
    return found


# One browse serves every media scanner of a Scan, since they run side by side.
_TYPES = [ANDROID_TV, CAST, AIRPLAY, FIRE_TV]
_lock = threading.Lock()
_last: tuple[float, list[Service]] | None = None


def _browse_once(timeout: float) -> list[Service]:
    global _last
    with _lock:
        if _last is None or time.monotonic() - _last[0] > _MAX_WAIT + 2:
            _last = (time.monotonic(), browse(_TYPES, timeout))
        return _last[1]


def scan_android_tv(timeout: float) -> list[FoundDevice]:
    return android_tvs(_browse_once(timeout))


def unsupported_scanner(brand: str):
    def scan(timeout: float) -> list[FoundDevice]:
        return [d for d in unsupported(_browse_once(timeout)) if d.brand == brand]

    return scan
