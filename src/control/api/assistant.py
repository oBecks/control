"""Settings → Assistant (ADR 0005): Connect Claude, i.e. add Control's MCP server to Claude Desktop's
config, and the command that does the same for Claude Code. Only the computer running Control can
change it: it writes that computer's files."""

from contextlib import closing
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import __version__
from ..assistant import claude
from ..assistant.server import MCP_HEADER
from ..engine.registry import Registry

router = APIRouter(prefix="/api/assistant")

# After an update Claude keeps running the old MCP server, with the old tools, until it restarts.
# `updated_from` is set when this Engine first runs a new version, and cleared once an MCP server of
# this version calls the Engine (or the user dismisses the note).
_VERSION, _UPDATED_FROM = "version", "updated_from"
_restart_pending: bool | None = None  # memory copy, so most requests never touch the Registry


def _note_version(r: Registry) -> None:
    global _restart_pending
    last = r.setting(_VERSION)
    if last != __version__:
        # Versions before this note didn't record themselves: devices mean it's an update.
        if last or r.all() or r.remotes():
            r.set_setting(_UPDATED_FROM, last or "an older version")
        r.set_setting(_VERSION, __version__)
    _restart_pending = r.setting(_UPDATED_FROM) is not None


def _clear_restart(r: Registry) -> None:
    global _restart_pending
    r.set_setting(_UPDATED_FROM, None)
    _restart_pending = False


async def note_mcp(request: Request, call_next):
    """Middleware: an MCP server of this version is running, so Claude has the new tools."""
    if request.headers.get(MCP_HEADER) == __version__ and _restart_pending is not False:
        with closing(Registry()) as r:
            _note_version(r)
            if _restart_pending:
                _clear_restart(r)
    return await call_next(request)


class AssistantOut(BaseModel):
    claude_desktop: Literal["missing", "connected", "outdated", "off"] = Field(
        description="missing: not installed; outdated: connected to another copy of Control")
    claude_code_command: str
    can_change: bool  # only on the computer running the Engine
    restart_claude: str | None = Field(
        None, description="Control was updated and Claude still runs the old tools: this version")


def _status(request: Request) -> AssistantOut:
    status = claude.status()
    with closing(Registry()) as r:
        _note_version(r)
        restart = __version__ if _restart_pending and status in ("connected", "outdated") else None
    return AssistantOut(claude_desktop=status, claude_code_command=claude.claude_code_command(),
                        can_change=request.state.local, restart_claude=restart)


def _local_only(request: Request) -> None:
    if not request.state.local:
        raise HTTPException(403, "This can only be changed on the computer running Control")


@router.get("", response_model=AssistantOut)
def status(request: Request):
    return _status(request)


@router.delete("/restart-note", response_model=AssistantOut)
def dismiss_restart_note(request: Request):
    _local_only(request)
    with closing(Registry()) as r:
        _clear_restart(r)
    return _status(request)


@router.put("/claude", response_model=AssistantOut)
def connect_claude(request: Request):
    _local_only(request)
    claude.connect()
    return _status(request)


@router.delete("/claude", response_model=AssistantOut)
def disconnect_claude(request: Request):
    _local_only(request)
    claude.disconnect()
    return _status(request)
