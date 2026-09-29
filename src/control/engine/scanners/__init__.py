"""One scanner per brand. Each exposes `scan(timeout: float) -> list[FoundDevice]` (blocking).

A scanner's module (and the brand library it needs) is imported when a Scan first runs it, not when
the Engine starts, so the Engine idles without them."""

from importlib import import_module


def _lazy(module: str, name: str, *args):
    def scan(timeout: float):
        fn = getattr(import_module(f"{__name__}.{module}"), name)
        return (fn(*args) if args else fn)(timeout)

    return scan


SCANNERS = {
    "Yeelight": _lazy("yeelight_scanner", "scan"),
    "Broadlink": _lazy("broadlink_scanner", "scan"),
    "Tuya": _lazy("tuya_scanner", "scan"),
    "Android TV": _lazy("media_scanner", "scan_android_tv"),
    # Seen so the user knows they aren't supported yet (all from the same mDNS browse).
    "Apple TV": _lazy("media_scanner", "unsupported_scanner", "Apple TV"),
    "Fire TV": _lazy("media_scanner", "unsupported_scanner", "Fire TV"),
    "Google Cast": _lazy("media_scanner", "unsupported_scanner", "Google Cast"),
}
