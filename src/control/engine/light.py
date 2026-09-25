"""The Light Category: the essentials every light adapter must offer."""

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass
class LightFeatures:
    color: bool
    color_temp: bool
    min_kelvin: int = 0
    max_kelvin: int = 0


@dataclass
class LightState:
    on: bool
    brightness: int  # 1-100
    mode: Literal["color", "white"]
    rgb: tuple[int, int, int] | None = None  # set when mode == "color"
    kelvin: int | None = None  # set when mode == "white"


class Light(Protocol):
    features: LightFeatures

    def get_state(self) -> LightState: ...
    def turn_on(self) -> None: ...
    def turn_off(self) -> None: ...
    def set_brightness(self, percent: int) -> None: ...
    def set_rgb(self, r: int, g: int, b: int) -> None: ...
    def set_kelvin(self, kelvin: int) -> None: ...
