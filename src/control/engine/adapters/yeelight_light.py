import yeelight

from ..errors import DeviceUnreachable
from ..light import LightFeatures, LightState

# Yeelight's color_mode property: 1 = RGB, 2 = color temperature, 3 = HSV.
_COLOR_MODES = {"1", "3"}


class YeelightLight:
    """Local control over the bulb's LAN protocol (TCP 55443). Needs LAN Control enabled."""

    def __init__(self, ip: str):
        # A short effect makes changes feel smooth instead of snapping.
        self._bulb = yeelight.Bulb(ip, effect="smooth", duration=300)
        try:
            # Also teaches the library the bulb's type. Kept for the first get_state(): bulbs
            # rate-limit requests, so a status read shouldn't cost two.
            self._fresh: dict | None = self._bulb.get_properties()
        except (OSError, yeelight.BulbException) as exc:
            raise DeviceUnreachable(f"Yeelight at {ip}: {exc}") from exc
        specs = self._bulb.get_model_specs()
        kelvin = specs.get("color_temp", {})
        self.features = LightFeatures(
            color=self._bulb.bulb_type is yeelight.BulbType.Color,
            color_temp=bool(kelvin),
            min_kelvin=kelvin.get("min", 0),
            max_kelvin=kelvin.get("max", 0),
        )

    def get_state(self) -> LightState:
        props, self._fresh = self._fresh or self._bulb.get_properties(), None
        rgb = int(props.get("rgb") or 0)
        is_color = props.get("color_mode") in _COLOR_MODES
        return LightState(
            on=props.get("power") == "on",
            brightness=int(props.get("current_brightness") or props.get("bright") or 0),
            mode="color" if is_color else "white",
            rgb=((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF) if is_color else None,
            kelvin=None if is_color else int(props.get("ct") or 0),
        )

    def turn_on(self) -> None:
        self._fresh = None  # state is about to change
        self._bulb.turn_on()

    def turn_off(self) -> None:
        self._fresh = None  # state is about to change
        self._bulb.turn_off()

    def set_brightness(self, percent: int) -> None:
        self._fresh = None  # state is about to change
        self._bulb.set_brightness(max(1, min(100, percent)))

    def set_rgb(self, r: int, g: int, b: int) -> None:
        self._fresh = None  # state is about to change
        if not self.features.color:
            raise ValueError("this light has no color")
        self._bulb.set_rgb(r, g, b)

    def set_kelvin(self, kelvin: int) -> None:
        self._fresh = None  # state is about to change
        if not self.features.color_temp:
            raise ValueError("this light has no adjustable white")
        self._bulb.set_color_temp(max(self.features.min_kelvin, min(self.features.max_kelvin, kelvin)))
