"""Sunrise and sunset for Automations (ADR 0006): from a location picked offline, either a city
from the list bundled with `astral` or typed coordinates. No Windows Location and no IP lookup.

Times are the PC's local time, like every other time in an Automation.
"""

import datetime as dt
from dataclasses import dataclass

from astral import Observer
from astral import sun as astral_sun
from astral.geocoder import all_locations, database

EVENTS = ("sunrise", "sunset")


@dataclass(frozen=True)
class Location:
    name: str  # a city ("Jerusalem, Israel"), or the coordinates as typed
    lat: float
    lon: float


def check(name: str | None, lat, lon) -> Location:
    """A location from the user's input, or ValueError."""
    for value, low, high, what in ((lat, -90, 90, "latitude"), (lon, -180, 180, "longitude")):
        if not isinstance(value, int | float) or isinstance(value, bool) or not low <= value <= high:
            raise ValueError(f"the {what} must be a number from {low} to {high}")
    return Location(name=(name or "").strip() or f"{lat:.4f}, {lon:.4f}", lat=float(lat), lon=float(lon))


_cities: list[Location] | None = None


def cities() -> list[Location]:
    """Every city astral knows (a few hundred: capitals and big cities), by name."""
    global _cities
    if _cities is None:
        found = [Location(f"{c.name}, {c.region}", c.latitude, c.longitude) for c in all_locations(database())]
        _cities = sorted(found, key=lambda c: c.name)
    return _cities


def find_cities(query: str, limit: int = 20) -> list[Location]:
    q = query.strip().casefold()
    if not q:
        return []
    starts = [c for c in cities() if c.name.casefold().startswith(q)]
    within = [c for c in cities() if q in c.name.casefold() and c not in starts]
    return (starts + within)[:limit]


def _local_zone(day: dt.date) -> dt.tzinfo:
    # The PC's offset on that day (so summer time is right), without needing a time zone database.
    return dt.datetime(day.year, day.month, day.day, 12).astimezone().tzinfo


def event_at(where: Location, day: dt.date, event: str) -> dt.datetime | None:
    """Local (naive) time of sunrise or sunset on that day; None when the sun doesn't rise or set."""
    zone = _local_zone(day)
    fn = astral_sun.sunrise if event == "sunrise" else astral_sun.sunset
    try:
        return fn(Observer(where.lat, where.lon), day, tzinfo=zone).replace(tzinfo=None)
    except ValueError:  # polar day or night
        return None


def is_dark(where: Location, at: dt.datetime) -> bool:
    """Between sunset and sunrise."""
    rise, set_ = event_at(where, at.date(), "sunrise"), event_at(where, at.date(), "sunset")
    if rise is None or set_ is None:
        # No sunrise or sunset today: dark when the sun is below the horizon at noon.
        noon = dt.datetime.combine(at.date(), dt.time(12)).replace(tzinfo=_local_zone(at.date()))
        return astral_sun.elevation(Observer(where.lat, where.lon), noon) < 0
    return not rise <= at < set_
