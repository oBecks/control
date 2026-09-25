from dataclasses import dataclass, field
from enum import Enum


class Category(str, Enum):
    LIGHT = "light"
    PLUG = "plug"
    CLIMATE = "climate"
    MEDIA = "media"
    TRANSMITTER = "transmitter"
    UNKNOWN = "unknown"


class Readiness(str, Enum):
    """What stands between a Found Device and being controllable."""

    READY = "ready"  # controllable as-is
    NEEDS_LINK = "needs_link"  # needs a one-time Link (e.g. Tuya Local Key)
    NEEDS_SETUP = "needs_setup"  # user must change something on the device/brand app
    UNSUPPORTED = "unsupported"


@dataclass
class FoundDevice:
    brand: str
    ip: str
    # Stable identity across IP changes: brand-scoped device id, falling back to MAC.
    uid: str
    category: Category
    readiness: Readiness
    name: str = ""
    model: str = ""
    mac: str = ""
    note: str = ""
    raw: dict = field(default_factory=dict, repr=False)
