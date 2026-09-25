"""The Desktop App's part of Settings (ADR 0004): Start with Windows and update notices. The Engine
only knows about the Desktop App when it runs inside it; under `control serve`, `app` is False."""

from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import __version__
from ..desktop.updates import Update
from ..engine.registry import Registry
from .deps import registry

# Setting (bool): the Window should say, once, that closing it kept Control running. Set on the first
# close when Windows notifications are off, so the tray's notification can't say it.
CLOSE_NOTE = "desktop_close_note"


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
    close_note: bool  # show the one-time "still running" note (this computer only)
    can_change: bool  # only on the computer running the Engine


class StartWithWindowsIn(BaseModel):
    on: bool


def _status(request: Request, r: Registry) -> DesktopOut:
    from ..desktop import autostart

    u, local = state.update, request.state.local
    return DesktopOut(
        version=__version__, app=state.running,
        start_with_windows=autostart.is_on() if state.running else None,
        update=UpdateOut(version=u.version, url=u.url) if u else None,
        close_note=local and r.setting(CLOSE_NOTE, False), can_change=local,
    )


def _local_only(request: Request) -> None:
    if not request.state.local:
        raise HTTPException(403, "This can only be changed on the computer running Control")


@router.get("", response_model=DesktopOut)
def status(request: Request, r: Registry = Depends(registry)):
    return _status(request, r)


@router.delete("/close-note", status_code=204)
def dismiss_close_note(request: Request, r: Registry = Depends(registry)):
    _local_only(request)
    r.set_setting(CLOSE_NOTE, False)


@router.put("/start-with-windows", response_model=DesktopOut)
def set_start_with_windows(body: StartWithWindowsIn, request: Request, r: Registry = Depends(registry)):
    from ..desktop import autostart

    _local_only(request)
    if not state.running:
        raise HTTPException(409, "Control isn't running as the desktop app")
    autostart.set_on(body.on)
    return _status(request, r)
