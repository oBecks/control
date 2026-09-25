"""Update notices (ADR 0004): look for a newer release on GitHub. Notify only: the user downloads and
runs the new installer themselves, since an unsigned self-updater is too easy a target."""

import json
import re
import urllib.request
from dataclasses import dataclass

from .. import __version__

REPO = "oBecks/control"
INSTALLER = "ControlSetup.exe"
CHECK_EVERY = 24 * 3600  # seconds


@dataclass(frozen=True)
class Update:
    version: str
    url: str  # the new installer, or the release page if it has none


def parse_version(text: str) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text.strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def newer(release: dict, current: str = __version__) -> Update | None:
    """The Update a GitHub release offers, if it's newer than `current`."""
    if release.get("draft") or release.get("prerelease"):
        return None
    version, mine = parse_version(release.get("tag_name", "")), parse_version(current)
    if version is None or mine is None or version <= mine:
        return None
    url = next((a["browser_download_url"] for a in release.get("assets", []) if a.get("name") == INSTALLER),
               release.get("html_url") or f"https://github.com/{REPO}/releases/latest")
    return Update(version=".".join(map(str, version)), url=url)


def check(timeout: float = 15) -> Update | None:
    """Ask GitHub for the latest release. None when there's nothing newer or GitHub can't be reached."""
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": f"Control/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return newer(json.load(resp))
    except (OSError, ValueError):
        return None
