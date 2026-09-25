import broadlink

from ..found_device import Category, FoundDevice, Readiness

_CATEGORY_BY_TYPE_PREFIX = [
    ("RM", Category.TRANSMITTER),
    ("SP", Category.PLUG),
    ("MP", Category.PLUG),
    ("BG", Category.PLUG),
    ("EHC", Category.PLUG),
    ("LB", Category.LIGHT),
    ("HYS", Category.CLIMATE),
    ("HVAC", Category.CLIMATE),
]


def _category(device_type: str) -> Category:
    for prefix, category in _CATEGORY_BY_TYPE_PREFIX:
        if device_type.startswith(prefix):
            return category
    return Category.UNKNOWN


def scan(timeout: float) -> list[FoundDevice]:
    found = []
    for dev in broadlink.discover(timeout=int(max(1, timeout))):
        mac = ":".join(f"{b:02x}" for b in dev.mac)
        category = _category(dev.TYPE)
        if dev.is_locked:
            readiness, note = Readiness.NEEDS_SETUP, "locked: unlock it in the Broadlink app"
        elif dev.TYPE == "Unknown":
            readiness, note = Readiness.UNSUPPORTED, f"unknown devtype 0x{dev.devtype:04x}"
        else:
            readiness, note = Readiness.READY, ""
        found.append(
            FoundDevice(
                brand="Broadlink",
                ip=dev.host[0],
                uid=f"broadlink:{mac}",
                category=category,
                readiness=readiness,
                name=dev.name,
                model=f"{dev.model} ({dev.TYPE})" if dev.model else dev.TYPE,
                mac=mac,
                note=note,
                raw={"devtype": dev.devtype, "type": dev.TYPE, "manufacturer": dev.manufacturer},
            )
        )
    return found
