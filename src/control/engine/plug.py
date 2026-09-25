"""The Plug Category: the essentials every plug adapter must offer."""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class PlugState:
    on: bool


class Plug(Protocol):
    def get_state(self) -> PlugState: ...
    def turn_on(self) -> None: ...
    def turn_off(self) -> None: ...
