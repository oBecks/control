import yeelight

from ..found_device import Category, FoundDevice, Readiness


def scan(timeout: float) -> list[FoundDevice]:
    # Bulbs only answer this multicast search when "LAN Control" is enabled in the
    # Yeelight app, so a bulb with it off is invisible here.
    found = []
    for bulb in yeelight.discover_bulbs(timeout=timeout):
        caps = bulb["capabilities"]
        found.append(
            FoundDevice(
                brand="Yeelight",
                ip=bulb["ip"],
                uid=f"yeelight:{caps.get('id', bulb['ip'])}",
                category=Category.LIGHT,
                readiness=Readiness.READY,
                name=caps.get("name", ""),
                model=caps.get("model", ""),
                note=f"power={caps.get('power', '?')} bright={caps.get('bright', '?')}",
                raw=bulb,
            )
        )
    return found
