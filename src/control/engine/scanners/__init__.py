"""One scanner per brand. Each exposes `scan(timeout: float) -> list[FoundDevice]` (blocking)."""

from . import broadlink_scanner, tuya_scanner, yeelight_scanner

SCANNERS = {
    "Yeelight": yeelight_scanner.scan,
    "Broadlink": broadlink_scanner.scan,
    "Tuya": tuya_scanner.scan,
}
