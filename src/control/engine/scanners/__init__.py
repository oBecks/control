"""One scanner per brand. Each exposes `scan(timeout: float) -> list[FoundDevice]` (blocking)."""

from . import broadlink_scanner, media_scanner, tuya_scanner, yeelight_scanner

SCANNERS = {
    "Yeelight": yeelight_scanner.scan,
    "Broadlink": broadlink_scanner.scan,
    "Tuya": tuya_scanner.scan,
    "Android TV": media_scanner.scan_android_tv,
    # Seen so the user knows they aren't supported yet (all from the same mDNS browse).
    "Apple TV": media_scanner.unsupported_scanner("Apple TV"),
    "Fire TV": media_scanner.unsupported_scanner("Fire TV"),
    "Google Cast": media_scanner.unsupported_scanner("Google Cast"),
}
