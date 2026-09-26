"""Turn a remembered device into a live, controllable object."""

from typing import Callable, TypeVar

from .adapters.androidtv_streamer import AndroidTVStreamer
from .adapters.broadlink_transmitter import BroadlinkTransmitter
from .adapters.tuya_plug import TuyaPlug
from .adapters.yeelight_light import YeelightLight
from .climate import ClimateState, RemoteClimate
from .errors import DeviceUnreachable
from .found_device import Category, Readiness
from .light import Light
from .plug import Plug
from .registry import KnownDevice, Registry, RemoteDevice
from .remote_buttons import RemoteButtons
from .scan import scan_and_remember
from .streamer import Streamer

T = TypeVar("T")

_LIGHT_ADAPTERS = {"Yeelight": YeelightLight}

# Re-find only needs one announcement from the brand, so it can be short.
_REFIND_TIMEOUT = 3.0


def _with_refind(registry: Registry, device: KnownDevice, open_: Callable[[KnownDevice], T]) -> tuple[KnownDevice, T]:
    """Open `device`; if it doesn't answer at its known IP, rescan its brand once
    in case the router gave it a new one."""
    try:
        opened = open_(device)
    except DeviceUnreachable:
        scan_and_remember(registry, _REFIND_TIMEOUT, brands={device.brand})
        refound = registry.get(device.uid)
        if refound is None or not refound.online or refound.ip == device.ip:
            raise
        return refound, open_(refound)
    if not device.online:
        registry.mark_online(device.uid)  # it answered: a Scan just missed it
    return device, opened


def control_kind(registry: Registry, device: KnownDevice) -> str | None:
    """Which control surface a remembered network device gets, or None if the app can't control it yet."""
    if device.readiness is not Readiness.READY:
        return None
    if device.category is Category.LIGHT and device.brand in _LIGHT_ADAPTERS:
        return "light"
    if device.category is Category.PLUG and device.brand == "Tuya" and registry.get_link(device.uid):
        return "plug"
    if device.category is Category.MEDIA and device.brand == "Android TV" and registry.get_link(device.uid):
        return "streamer"
    return None


def connect_light(registry: Registry, ref: str) -> tuple[KnownDevice, Light]:
    """Connect to a Light by uid, name or IP."""
    device = registry.resolve(ref)
    if device.category is not Category.LIGHT or device.brand not in _LIGHT_ADAPTERS:
        raise LookupError(f"'{device.name}' is not a light this app can control yet")
    adapter = _LIGHT_ADAPTERS[device.brand]
    return _with_refind(registry, device, lambda d: adapter(d.ip))


def connect_plug(registry: Registry, ref: str) -> tuple[KnownDevice, Plug]:
    device = registry.resolve(ref)
    if device.category is not Category.PLUG or device.brand != "Tuya":
        raise LookupError(f"'{device.name}' is not a plug this app can control yet")
    link = registry.get_link(device.uid)
    if link is None:
        raise LookupError(f"'{device.name}' needs a Link first: control tuya-link")
    return _with_refind(
        registry,
        device,
        lambda d: TuyaPlug(d.uid.removeprefix("tuya:"), d.ip, link["secret"]["local_key"], d.raw.get("version", "3.3")),
    )


def connect_streamer(registry: Registry, ref: str) -> tuple[KnownDevice, Streamer]:
    device = registry.resolve(ref)
    if control_kind(registry, device) != "streamer":
        raise LookupError(f"'{device.name}' is not a Streamer this app can control yet")
    return _with_refind(registry, device, lambda d: AndroidTVStreamer(d.uid, d.ip))


def connect_transmitter(registry: Registry, ref: str) -> tuple[KnownDevice, BroadlinkTransmitter]:
    device = registry.resolve(ref)
    if device.category is not Category.TRANSMITTER or device.brand != "Broadlink":
        raise LookupError(f"'{device.name}' is not a transmitter")
    if device.readiness is Readiness.NEEDS_SETUP:
        raise LookupError(f"'{device.name}' needs setup: {device.note}")
    return _with_refind(
        registry, device, lambda d: BroadlinkTransmitter(d.ip, d.mac, d.raw["devtype"])
    )


def only_transmitter(registry: Registry) -> KnownDevice:
    transmitters = [d for d in registry.all() if d.category is Category.TRANSMITTER]
    if len(transmitters) != 1:
        raise LookupError(f"found {len(transmitters)} transmitters; say which one with --via")
    return transmitters[0]


def connect_buttons(registry: Registry, ref: str) -> tuple[RemoteDevice, RemoteButtons]:
    remote = registry.resolve_remote(ref)
    if remote.signals.get("format") != "buttons":
        raise LookupError(f"'{remote.name}' isn't a button remote")
    _, transmitter = connect_transmitter(registry, remote.transmitter_uid)
    assumed_on = (remote.assumed_state or {}).get("on")
    return remote, RemoteButtons(remote.signals, transmitter, assumed_on)


def connect_climate(registry: Registry, ref: str) -> tuple[RemoteDevice, RemoteClimate]:
    remote = registry.resolve_remote(ref)
    if remote.category is not Category.CLIMATE:
        raise LookupError(f"'{remote.name}' is not an AC")
    _, transmitter = connect_transmitter(registry, remote.transmitter_uid)
    assumed = ClimateState(**remote.assumed_state) if remote.assumed_state else None
    return remote, RemoteClimate(remote.signals, transmitter, assumed)
