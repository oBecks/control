"""Connect Claude (ADR 0005): add a `control` entry to Claude Desktop's config, so Claude starts
`Control.exe --mcp`, and take it out again on Disconnect or uninstall. Everything else in the file is
kept, and it's backed up first.

Claude Desktop keeps its config in %APPDATA%\\Claude; the Microsoft Store install sees a private copy
of that folder under %LOCALAPPDATA%\\Packages\\Claude_…\\LocalCache\\Roaming\\Claude. Both are written
when both exist."""

import json
import os
import subprocess
import sys
from pathlib import Path

NAME = "control"  # the entry in mcpServers
CONFIG = "claude_desktop_config.json"


def command() -> list[str]:
    """What Claude runs: this Control.exe, or from source this Python."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--mcp"]
    return [sys.executable, "-m", "control.desktop", "--mcp"]


def claude_code_command() -> str:
    return subprocess.list2cmdline(["claude", "mcp", "add", "--scope", "user", NAME, "--", *command()])


def config_dirs() -> list[Path]:
    """Claude Desktop's config folders on this PC; empty if it isn't installed."""
    dirs = []
    if appdata := os.environ.get("APPDATA"):
        dirs.append(Path(appdata) / "Claude")
    if local := os.environ.get("LOCALAPPDATA"):
        dirs += sorted((Path(local) / "Packages").glob("Claude_*/LocalCache/Roaming/Claude"))
    return [d for d in dirs if d.is_dir()]


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        config = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        raise ValueError(f"Claude's settings file isn't valid JSON, so Control left it alone: {path}") from None
    if not isinstance(config, dict):
        raise ValueError(f"Claude's settings file isn't a JSON object, so Control left it alone: {path}")
    return config


def _write(path: Path, config: dict) -> None:
    if path.exists():
        path.with_name(path.name + ".bak").write_bytes(path.read_bytes())
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _servers(config: dict) -> dict:
    servers = config.get("mcpServers")
    return servers if isinstance(servers, dict) else {}


def entry() -> dict:
    cmd = command()
    return {"command": cmd[0], "args": cmd[1:]}


def status() -> str:
    """"missing" (no Claude Desktop), "connected", "outdated" (points at another Control) or "off"."""
    dirs = config_dirs()
    if not dirs:
        return "missing"
    found = []
    for d in dirs:
        try:
            found.append(_servers(_read(d / CONFIG)).get(NAME))
        except ValueError:
            found.append(None)
    if all(e == entry() for e in found):
        return "connected"
    return "outdated" if any(found) else "off"


def connect() -> None:
    dirs = config_dirs()
    if not dirs:
        raise LookupError("Claude Desktop isn't installed on this PC")
    configs = {d / CONFIG: _read(d / CONFIG) for d in dirs}  # all readable before anything changes
    for path, config in configs.items():
        servers = config.get("mcpServers")
        if not isinstance(servers, dict):
            servers = config["mcpServers"] = {}
        servers[NAME] = entry()
        _write(path, config)


def disconnect() -> None:
    """Remove this Control's entry. One pointing at another copy of Control is that copy's, so
    uninstalling an old copy doesn't disconnect the new one."""
    for d in config_dirs():
        path = d / CONFIG
        try:
            config = _read(path)
        except ValueError:
            continue  # not ours to fix
        servers = _servers(config)
        if servers.get(NAME) == entry():
            del servers[NAME]
            _write(path, config)
