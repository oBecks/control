"""Settings → Assistant (ADR 0005): Connect Claude, i.e. add Control's MCP server to Claude Desktop's
config, and the command that does the same for Claude Code. Only the computer running Control can
change it: it writes that computer's files."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..assistant import claude

router = APIRouter(prefix="/api/assistant")


class AssistantOut(BaseModel):
    claude_desktop: Literal["missing", "connected", "outdated", "off"] = Field(
        description="missing: not installed; outdated: connected to another copy of Control")
    claude_code_command: str
    can_change: bool  # only on the computer running the Engine


def _status(request: Request) -> AssistantOut:
    return AssistantOut(claude_desktop=claude.status(), claude_code_command=claude.claude_code_command(),
                        can_change=request.state.local)


def _local_only(request: Request) -> None:
    if not request.state.local:
        raise HTTPException(403, "This can only be changed on the computer running Control")


@router.get("", response_model=AssistantOut)
def status(request: Request):
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
