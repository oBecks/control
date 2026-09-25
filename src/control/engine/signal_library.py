"""The Signal Library: SmartIR's community catalogue of IR codes (github.com/smartHomeHub/SmartIR).

Each domain (climate, media_player, fan) has an index in the docs markdown (one table per
manufacturer). Code files are downloaded on demand and cached, and a Remote Device keeps its
own copy of its Signals so it keeps working offline.
"""

import json
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .registry import default_db_path

Domain = Literal["climate", "media_player", "fan"]
DOMAINS: dict[str, str] = {"climate": "CLIMATE.md", "media_player": "MEDIA_PLAYER.md", "fan": "FAN.md"}

_RAW = "https://raw.githubusercontent.com/smartHomeHub/SmartIR/master"
# Rows look like "| [1942](../codes/..json) | Models | Broadlink |"; some tables drop the outer pipes.
_ROW = re.compile(r"^\|?\s*\[(\d+)\]\([^)]*\)\s*\|\s*(.*?)\s*\|\s*(\w[\w ]*?)\s*\|?\s*$")


@dataclass
class CodeSet:
    code: int
    manufacturer: str
    models: list[str]
    controller: str


def _cache_dir(domain: str) -> Path:
    path = default_db_path().parent / "smartir" / domain
    path.mkdir(parents=True, exist_ok=True)
    return path


def _fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.read().decode("utf-8")


def parse_index(markdown: str) -> list[CodeSet]:
    sets, manufacturer = [], ""
    for line in markdown.splitlines():
        if line.startswith("#### "):
            manufacturer = line[5:].strip()
        elif manufacturer and (m := _ROW.match(line)):
            models = [s.strip() for s in re.split(r"<br\s*/?>", re.sub(r"</?b>", "", m[2])) if s.strip()]
            sets.append(CodeSet(int(m[1]), manufacturer, models, m[3].strip()))
    return sets


def index(domain: str, refresh: bool = False) -> list[CodeSet]:
    if domain not in DOMAINS:
        raise ValueError(f"unknown signal library domain '{domain}'")
    cached = _cache_dir(domain) / "index.md"
    if refresh or not cached.exists():
        cached.write_text(_fetch(f"{_RAW}/docs/{DOMAINS[domain]}"), encoding="utf-8")
    return parse_index(cached.read_text(encoding="utf-8"))


def search(domain: str, brand: str, controller: str = "Broadlink") -> list[CodeSet]:
    brand = brand.casefold()
    return [
        s
        for s in index(domain)
        if brand in s.manufacturer.casefold() and s.controller.casefold() == controller.casefold()
    ]


def load(domain: str, code: int) -> dict:
    if domain not in DOMAINS:
        raise ValueError(f"unknown signal library domain '{domain}'")
    cached = _cache_dir(domain) / f"{code}.json"
    if not cached.exists():
        cached.write_text(_fetch(f"{_RAW}/codes/{domain}/{code}.json"), encoding="utf-8")
    data = json.loads(cached.read_text(encoding="utf-8"))
    if data.get("commandsEncoding") != "Base64" or data.get("supportedController") != "Broadlink":
        raise ValueError(f"code set {code} is not a Broadlink code set")
    return data


# Climate shorthands (the AC flow predates the other domains).
def climate_index(refresh: bool = False) -> list[CodeSet]:
    return index("climate", refresh)


def search_climate(brand: str, controller: str = "Broadlink") -> list[CodeSet]:
    return search("climate", brand, controller)


def load_climate(code: int) -> dict:
    return load("climate", code)
