"""Streamers (see CONTEXT.md): a box playing media on the TV it's plugged into, controlled over the
network with a real state. Also a TV with network control of its own, which gets the same controls.

Streamer App Shortcuts are stored per Device as [{"name", "app", "link"?}]: "app" is the Android package
(it names the open app), "link" what opens it. Some devices (e.g. an NVIDIA Shield) refuse to open an app
by its package and only take its link. Android TV can't list what's installed, so the catalogue below
is Control's own.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class StreamerState:
    on: bool
    app: str | None = None  # the open app's package, e.g. "com.netflix.ninja"
    volume: int | None = None
    volume_max: int | None = None
    muted: bool | None = None


class Streamer(Protocol):
    def get_state(self) -> StreamerState: ...
    def set_power(self, on: bool) -> None: ...
    def press(self, button: str) -> None: ...
    def open_app(self, app: str) -> None: ...


# Button names are shared with an infrared TV's (remote_buttons.SUGGESTED), so Hotkeys, Dashboards
# and the Assistant can treat both alike. Values: Android key codes.
BUTTONS: dict[str, tuple[str, str]] = {
    "power": ("Power", "POWER"),
    "volume_up": ("Volume +", "VOLUME_UP"),
    "volume_down": ("Volume −", "VOLUME_DOWN"),
    "mute": ("Mute", "VOLUME_MUTE"),
    "up": ("Up", "DPAD_UP"),
    "down": ("Down", "DPAD_DOWN"),
    "left": ("Left", "DPAD_LEFT"),
    "right": ("Right", "DPAD_RIGHT"),
    "ok": ("OK", "DPAD_CENTER"),
    "back": ("Back", "BACK"),
    "home": ("Home", "HOME"),
    "channel_up": ("Channel +", "CHANNEL_UP"),
    "channel_down": ("Channel −", "CHANNEL_DOWN"),
    "play_pause": ("Play / Pause", "MEDIA_PLAY_PAUSE"),
}


def key_code(button: str) -> str:
    if button not in BUTTONS:
        raise ValueError(f"no '{button}' button; try one of {', '.join(BUTTONS)}")
    return BUTTONS[button][1]


# Known apps, in the order the setup offers them. `default`: ticked at setup.
CATALOGUE: list[dict] = [
    {"name": "YouTube", "app": "com.google.android.youtube.tv", "link": "https://www.youtube.com", "default": True},
    {"name": "Netflix", "app": "com.netflix.ninja", "link": "https://www.netflix.com/title", "default": True},
    {"name": "Spotify", "app": "com.spotify.tv.android", "link": "https://open.spotify.com", "default": True},
    {"name": "Apple TV", "app": "com.apple.atve.androidtv.appletv", "link": "https://tv.apple.com", "default": True},
    {"name": "yes+", "app": "il.co.yes.yesplus", "default": False, "yes": True},
    {"name": "Stremio", "app": "com.stremio.one", "link": "stremio://", "default": False},
    {"name": "Disney+", "app": "com.disney.disneyplus", "link": "https://www.disneyplus.com", "default": False},
    {"name": "Prime Video", "app": "com.amazon.amazonvideo.livingroom", "link": "https://app.primevideo.com",
     "default": False},
    {"name": "YouTube Music", "app": "com.google.android.youtube.tvmusic", "default": False},
    {"name": "Plex", "app": "com.plexapp.android", "link": "plex://", "default": False},
    {"name": "Kodi", "app": "org.xbmc.kodi", "default": False},
    {"name": "Twitch", "app": "tv.twitch.android.app", "link": "twitch://home", "default": False},
]


# Names for apps a box may list as installed (with adb) that the catalogue doesn't offer.
NAMES = {
    "com.android.tv.settings": "Settings",
    "com.android.vending": "Play Store",
    "com.android.gallery3d": "Gallery",
    "com.google.android.play.games": "Play Games",
    "com.nvidia.tegrazone3": "GeForce NOW",
    "com.plexapp.mediaserver.smb": "Plex Media Server",
    "com.valvesoftware.steamlink": "Steam Link",
    "com.disneyplus.mea": "Disney+",
}
_SYSTEM = {"com.android.tv.settings", "com.android.vending", "com.android.gallery3d"}


def _shortcut(entry: dict) -> dict:
    return {k: entry[k] for k in ("name", "app", "link") if entry.get(k)}


def with_links(shortcuts: list[dict]) -> list[dict]:
    """Shortcuts saved without a link get the catalogue's, when it has one."""
    links = {e["app"]: e["link"] for e in CATALOGUE if e.get("link")}
    return [s if s.get("link") or s["app"] not in links else s | {"link": links[s["app"]]} for s in shortcuts]


def launch_target(shortcut: dict) -> str:
    """What to send to open it: its link, else its package."""
    return shortcut.get("link") or shortcut["app"]


def is_yes_box(model: str) -> bool:
    return model.strip().casefold() == "yes"


def catalogue_for(model: str) -> list[dict]:
    """The catalogue as a setup shows it for this model: yes+ is ticked on yes boxes."""
    yes = is_yes_box(model)
    return [_shortcut(e) | {"default": e["default"] or (yes and e.get("yes", False))} for e in CATALOGUE]


def installed_catalogue(packages: list[str], model: str) -> list[dict]:
    """The apps a box really has (read with adb), shaped like the catalogue: known ones by name and
    with their link and default; others by a tidied package name. System apps go last."""
    known = {e["app"]: e for e in catalogue_for(model)}
    out = []
    for package in sorted(packages, key=lambda p: p in _SYSTEM):
        entry = known.get(package)
        if entry is None:
            entry = {"name": app_name(package, []) or package, "app": package, "default": False}
        out.append(entry)
    return out


def default_shortcuts(model: str) -> list[dict]:
    return [_shortcut(e) for e in catalogue_for(model) if e["default"]]


def check_shortcuts(shortcuts: list[dict]) -> list[dict]:
    """Clean a user's list: names and apps present, no app twice."""
    out, seen = [], set()
    for s in shortcuts:
        name, app = str(s.get("name", "")).strip(), str(s.get("app", "")).strip()
        link = str(s.get("link") or "").strip()
        if not name or not app:
            raise ValueError("each app needs a name and a package name or link")
        if app in seen:
            continue
        seen.add(app)
        out.append({"name": name, "app": app} | ({"link": link} if link else {}))
    return out


def app_name(package: str | None, shortcuts: list[dict]) -> str | None:
    """What to call the open app: its App Shortcut's name, the catalogue's, or its package, shortened."""
    if not package:
        return None
    for entry in [*shortcuts, *CATALOGUE]:
        if entry["app"] == package:
            return entry["name"]
    if package in NAMES:
        return NAMES[package]
    if "launcher" in package:  # com.google.android.tvlauncher, Google TV's ...launcherx
        return "Home screen"
    if package in ("com.google.android.backdrop", "com.android.dreams.basic"):
        return "Screensaver"
    parts = [p for p in package.split(".") if p not in {"com", "android", "tv", "app", "google", "androidtv"}]
    return (parts[-1] if parts else package).replace("_", " ").capitalize()


def find_shortcut(ref: str, shortcuts: list[dict]) -> str:
    """What to open for `ref` (see launch_target): a shortcut's name (any case, or a unique part), a
    catalogue name, or a package."""
    folded = ref.casefold().strip()
    for pool in (shortcuts, CATALOGUE):
        exact = [s for s in pool if s["name"].casefold() == folded or s["app"] == ref]
        if exact:
            return launch_target(exact[0])
        partial = [s for s in pool if folded and folded in s["name"].casefold()]
        if len(partial) == 1:
            return launch_target(partial[0])
    if "." in ref and " " not in ref:
        return ref  # a package name or link the user gave directly
    names = ", ".join(s["name"] for s in shortcuts) or "none yet"
    raise ValueError(f"no app '{ref}' on this Streamer (its apps: {names})")


_TV_MAKERS = ("sony", "bravia", "tcl", "philips", "hisense", "sharp", "panasonic", "toshiba", "skyworth", "xiaomi mi tv", "mitv", "thomson", "grundig", "loewe")


def guess_is_tv(manufacturer: str, model: str) -> bool:
    """A TV running Android TV itself, rather than a box plugged into one. Only a guess: setup asks."""
    text = f"{manufacturer} {model}".casefold()
    return any(maker in text for maker in _TV_MAKERS)
