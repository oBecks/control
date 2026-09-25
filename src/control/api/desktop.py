"""The Desktop App's part of Settings (ADR 0004): Start with Windows and update notices. The Engine
only knows about the Desktop App when it runs inside it; under `control serve`, `app` is False."""

from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import __version__
from ..desktop.updates import Update


@dataclass
class DesktopApp:
    running: bool = False  # set by the Desktop App when this Engine runs inside it
    update: Update | None = None


state = DesktopApp()

router = APIRouter(prefix="/api/desktop")


class UpdateOut(BaseModel):
    version: str
    url: str  # the new installer


class DesktopOut(BaseModel):
    version: str
    app: bool  # this Engine runs inside the Desktop App
    start_with_windows: bool | None  # null outside the Desktop App
    update: UpdateOut | None
    can_change: bool  # only on the computer running the Engine


class StartWithWindowsIn(BaseModel):
    on: bool


def _status(request: Request) -> DesktopOut:
    from ..desktop import autostart

    u = state.update
    return DesktopOut(
        version=__version__, app=state.running,
        start_with_windows=autostart.is_on() if state.running else None,
        update=UpdateOut(version=u.version, url=u.url) if u else None, can_change=request.state.local,
    )


@router.get("", response_model=DesktopOut)
def status(request: Request):
    return _status(request)


@router.put("/start-with-windows", response_model=DesktopOut)
def set_start_with_windows(body: StartWithWindowsIn, request: Request):
    from ..desktop import autostart

    if not request.state.local:
        raise HTTPException(403, "This can only be changed on the computer running Control")
    if not state.running:
        raise HTTPException(409, "Control isn't running as the desktop app")
    autostart.set_on(body.on)
    return _status(request)
