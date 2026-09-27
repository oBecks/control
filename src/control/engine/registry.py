"""The Registry remembers every Found Device across Scans, keyed by its stable uid,
so a device keeps its name (and later its Room, Link secrets...) when its IP changes."""

import hashlib
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import dashboards as dashboard_items
from . import vault
from .found_device import Category, FoundDevice, Readiness

_SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    uid         TEXT PRIMARY KEY,
    brand       TEXT NOT NULL,
    category    TEXT NOT NULL,
    readiness   TEXT NOT NULL,
    ip          TEXT NOT NULL,
    model       TEXT NOT NULL DEFAULT '',
    mac         TEXT NOT NULL DEFAULT '',
    brand_name  TEXT NOT NULL DEFAULT '',  -- name reported by the device itself
    user_name   TEXT,                      -- name the user gave it; wins over brand_name
    note        TEXT NOT NULL DEFAULT '',
    raw         TEXT NOT NULL DEFAULT '{}',
    first_seen  REAL NOT NULL,
    last_seen   REAL NOT NULL,
    is_new      INTEGER NOT NULL DEFAULT 1,
    online      INTEGER NOT NULL DEFAULT 1   -- seen in the latest Scan that covered its brand
);
-- What a Link taught us about a device. Survives rescans (which only know what's on the wire).
CREATE TABLE IF NOT EXISTS links (
    uid        TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    category   TEXT NOT NULL,
    secret     TEXT NOT NULL,     -- JSON, e.g. {"local_key": ...}, sealed by vault (DPAPI on Windows)
    info       TEXT NOT NULL DEFAULT '{}',
    linked_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS remote_devices (
    uid              TEXT PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE COLLATE NOCASE,
    category         TEXT NOT NULL,
    transmitter_uid  TEXT NOT NULL,
    source           TEXT NOT NULL,           -- where the Signals came from, e.g. smartir:climate:1942
    signals          TEXT NOT NULL,           -- own copy, so the device works offline
    assumed_state    TEXT,
    created          REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL       -- JSON
);
-- Browsers on other devices the user let in (ADR 0003). Only a hash of each token is kept.
CREATE TABLE IF NOT EXISTS approved_browsers (
    id           TEXT PRIMARY KEY,
    token_hash   TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    approved_at  REAL NOT NULL,
    last_seen    REAL NOT NULL
);
-- Groups: a named set of Devices controlled as one (network or Remote Devices, by uid).
CREATE TABLE IF NOT EXISTS groups (
    uid       TEXT PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    made_by   TEXT NOT NULL DEFAULT 'user',   -- 'user' or 'assistant'
    created   REAL NOT NULL
);
-- Streamers (and TVs with network control of their own): set up after their Link.
CREATE TABLE IF NOT EXISTS streamers (
    uid     TEXT PRIMARY KEY,
    is_tv   INTEGER NOT NULL DEFAULT 0,   -- a TV running Android TV itself, not a box plugged into one
    apps    TEXT NOT NULL DEFAULT '[]',   -- Streamer App Shortcuts, in order: [{"name", "app", "link"?}]
    adb     INTEGER NOT NULL DEFAULT 0    -- the Link's optional second step: adb allowed (ADR 0008)
);
CREATE TABLE IF NOT EXISTS group_members (
    group_uid   TEXT NOT NULL,
    device_uid  TEXT NOT NULL,
    position    INTEGER NOT NULL,
    PRIMARY KEY (group_uid, device_uid)
);
-- Hotkeys (ADR 0007): keys on the PC that do one thing to one Device or Group.
CREATE TABLE IF NOT EXISTS hotkeys (
    uid      TEXT PRIMARY KEY,
    keys     TEXT NOT NULL UNIQUE COLLATE NOCASE,   -- e.g. "Ctrl+Alt+L" (engine/hotkeys.py)
    target   TEXT NOT NULL,                         -- a Device's or Group's uid
    action   TEXT NOT NULL,                         -- JSON, e.g. {"do": "toggle"}
    made_by  TEXT NOT NULL DEFAULT 'user',          -- 'user' or 'assistant'
    created  REAL NOT NULL
);
-- Dashboards (ADR 0010): named screens the user arranges, items placed freely on a grid.
CREATE TABLE IF NOT EXISTS dashboards (
    uid       TEXT PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    columns   INTEGER NOT NULL DEFAULT 8,   -- the grid's width: 4 phone, 6 tablet, 8 desktop
    items     TEXT NOT NULL DEFAULT '[]',   -- JSON: [{"id", "kind", "x", "y", "w", "h", "target"?, "text"?...}]
    position  INTEGER NOT NULL,             -- order in the Dashboards list
    created   REAL NOT NULL
);
-- Automations (ADR 0006, 0012): When (triggers) -> Only if (conditions) -> Then (actions), engine/automations.py.
CREATE TABLE IF NOT EXISTS automations (
    uid         TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    enabled     INTEGER NOT NULL DEFAULT 1,
    match       TEXT NOT NULL DEFAULT 'all',   -- the Conditions: 'all' or 'any'
    triggers    TEXT NOT NULL DEFAULT '[]',    -- JSON
    conditions  TEXT NOT NULL DEFAULT '[]',
    actions     TEXT NOT NULL DEFAULT '[]',
    attention   TEXT,                          -- why it switched itself off, e.g. its last Action's Device was forgotten
    made_by     TEXT NOT NULL DEFAULT 'user',  -- 'user' or 'assistant'
    armed       REAL NOT NULL,                 -- since when its Triggers count: earlier times aren't missed Runs
    created     REAL NOT NULL
);
-- Scenes (ADR 0013): a named end state for several Devices, engine/scenes.py.
CREATE TABLE IF NOT EXISTS scenes (
    uid        TEXT PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    icon       TEXT NOT NULL DEFAULT 'sparkles',
    parts      TEXT NOT NULL DEFAULT '[]',    -- JSON: [{"target": uid, "state": {...}}]
    attention  TEXT,                          -- why it needs looking at, e.g. nothing is left in it
    position   INTEGER NOT NULL,              -- order on the Scenes page and Home
    made_by    TEXT NOT NULL DEFAULT 'user',  -- 'user' or 'assistant'
    created    REAL NOT NULL
);
-- Each Automation's last Runs (RUNS_KEPT).
CREATE TABLE IF NOT EXISTS automation_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    automation  TEXT NOT NULL,
    cause       TEXT NOT NULL,                 -- what started it, e.g. "At 07:00, every day" or "Run by hand"
    started     REAL NOT NULL,
    ended       REAL,
    outcome     TEXT NOT NULL,                 -- engine/automations.py OUTCOMES
    steps       TEXT NOT NULL DEFAULT '[]',    -- JSON: [{"label", "result": done|failed|not_run, "detail"?}]
    note        TEXT NOT NULL DEFAULT ''       -- e.g. which Condition wasn't met
);
-- Notifications from Automations: a Windows notification from the tray, and a notice in the UI.
CREATE TABLE IF NOT EXISTS notices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    time        REAL NOT NULL,
    title       TEXT NOT NULL,
    text        TEXT NOT NULL,
    automation  TEXT,
    seen        INTEGER NOT NULL DEFAULT 0
);
"""

RUNS_KEPT = 50  # per Automation (ADR 0012)
NOTICES_KEPT = 50


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def default_db_path() -> Path:
    base = os.environ.get("CONTROL_DATA_DIR") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Control"
    return Path(base) / "control.db"


@dataclass
class KnownDevice:
    uid: str
    brand: str
    category: Category
    readiness: Readiness
    ip: str
    model: str
    mac: str
    brand_name: str
    user_name: str | None
    note: str
    raw: dict
    first_seen: float
    last_seen: float
    is_new: bool
    online: bool  # seen in the latest Scan that covered its brand

    @property
    def name(self) -> str:
        return self.user_name or self.brand_name or f"{self.brand} {self.model or 'device'}"


@dataclass
class RemoteDevice:
    uid: str
    name: str
    category: Category
    transmitter_uid: str
    source: str
    signals: dict
    assumed_state: dict | None


@dataclass
class Group:
    uid: str
    name: str
    members: list[str]  # device uids, in the order the user picked them
    made_by: str  # "user" or "assistant"


@dataclass
class Hotkey:
    uid: str
    keys: str  # e.g. "Ctrl+Alt+L"
    target: str  # a Device's or Group's uid
    action: dict
    made_by: str  # "user" or "assistant"


@dataclass
class Dashboard:
    uid: str
    name: str
    columns: int
    items: list[dict]  # engine/dashboards.py


@dataclass
class Automation:
    uid: str
    name: str
    enabled: bool
    match: str  # the Conditions: "all" or "any"
    triggers: list[dict]  # engine/automations.py
    conditions: list[dict]
    actions: list[dict]
    attention: str | None  # why it switched itself off
    made_by: str  # "user" or "assistant"
    armed: float  # since when its Triggers count


@dataclass
class Scene:
    uid: str
    name: str
    icon: str
    parts: list[dict]  # engine/scenes.py
    attention: str | None  # why it needs looking at
    made_by: str  # "user" or "assistant"


@dataclass
class Run:
    id: int
    automation: str
    cause: str
    started: float
    ended: float | None
    outcome: str
    steps: list[dict]
    note: str


@dataclass
class Notice:
    id: int
    time: float
    title: str
    text: str
    automation: str | None
    seen: bool


@dataclass
class ApprovedBrowser:
    id: str
    name: str
    approved_at: float
    last_seen: float


@dataclass
class MergeReport:
    added: list[str]
    moved: dict[str, tuple[str, str]]  # uid -> (old ip, new ip)
    missing: list[str]  # known but not seen this Scan


class Registry:
    def __init__(self, path: Path | str | None = None):
        path = Path(path) if path else default_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        # The API opens a Registry per request and may touch it from several worker threads.
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        self._add_missing_columns()
        self._seal_plain_secrets()

    def close(self) -> None:
        self._db.close()

    # --- Scans -------------------------------------------------------------

    def merge_scan(self, found: list[FoundDevice], brands: set[str] | None = None) -> MergeReport:
        """Record a Scan's results. `brands` limits which brands the Scan covered, so a
        partial Scan (e.g. one brand failed) never marks other brands' devices offline."""
        known = {d.uid: d for d in self.all()}
        report = MergeReport(added=[], moved={}, missing=[])
        now = time.time()
        with self._db:
            for f in found:
                old = known.get(f.uid)
                if old is None:
                    report.added.append(f.uid)
                elif old.ip != f.ip:
                    report.moved[f.uid] = (old.ip, f.ip)
                self._db.execute(
                    """INSERT INTO devices (uid, brand, category, readiness, ip, model, mac, brand_name,
                                            note, raw, first_seen, last_seen, online)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                       ON CONFLICT(uid) DO UPDATE SET
                           category=excluded.category, readiness=excluded.readiness, ip=excluded.ip,
                           model=excluded.model, mac=excluded.mac, brand_name=excluded.brand_name,
                           note=excluded.note, raw=excluded.raw, last_seen=excluded.last_seen, online=1""",
                    (f.uid, f.brand, f.category.value, f.readiness.value, f.ip, f.model, f.mac, f.name,
                     f.note, json.dumps(f.raw, default=str), now, now),
                )
            seen = {f.uid for f in found}
            report.missing = [
                uid for uid, d in known.items() if uid not in seen and (brands is None or d.brand in brands)
            ]
            self._db.executemany("UPDATE devices SET online = 0 WHERE uid = ?", [(u,) for u in report.missing])
            self._apply_links()
        return report

    # --- Queries -----------------------------------------------------------

    def all(self) -> list[KnownDevice]:
        rows = self._db.execute("SELECT * FROM devices ORDER BY category, brand, ip").fetchall()
        return [self._to_known(r) for r in rows]

    def get(self, uid: str) -> KnownDevice | None:
        row = self._db.execute("SELECT * FROM devices WHERE uid = ?", (uid,)).fetchone()
        return self._to_known(row) if row else None

    def resolve(self, ref: str) -> KnownDevice:
        """Find a device by uid, name (case-insensitive) or current IP."""
        devices = self.all()
        for match in (
            lambda d: d.uid == ref,
            lambda d: d.name.casefold() == ref.casefold(),
            lambda d: d.ip == ref,
        ):
            hits = [d for d in devices if match(d)]
            if len(hits) == 1:
                return hits[0]
            if len(hits) > 1:
                raise LookupError(f"'{ref}' matches {len(hits)} devices; use the uid")
        raise LookupError(f"no known device '{ref}'; run a scan first")

    # --- User edits --------------------------------------------------------

    def rename(self, uid: str, name: str | None) -> None:
        with self._db:
            self._db.execute("UPDATE devices SET user_name = ? WHERE uid = ?", (name or None, uid))

    def mark_seen(self, uids: list[str] | None = None) -> None:
        """Clear the New flag (all devices when uids is None)."""
        with self._db:
            if uids is None:
                self._db.execute("UPDATE devices SET is_new = 0")
            else:
                self._db.executemany("UPDATE devices SET is_new = 0 WHERE uid = ?", [(u,) for u in uids])

    def mark_online(self, uid: str) -> None:
        """The device answered directly. Scans can miss a reply, so this overrides a stale Offline."""
        with self._db:
            self._db.execute("UPDATE devices SET online = 1 WHERE uid = ?", (uid,))

    def mark_offline(self, uid: str) -> None:
        """A listened-to device stopped answering for a minute (ADR 0011)."""
        with self._db:
            self._db.execute("UPDATE devices SET online = 0 WHERE uid = ?", (uid,))

    def forget(self, uid: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM devices WHERE uid = ?", (uid,))
            self._db.execute("DELETE FROM streamers WHERE uid = ?", (uid,))
            self._leave_groups(uid)
            self._drop_hotkeys(uid)
            self._drop_dashboard_items()
            self._trim_automations()
            self._trim_scenes()

    # --- Links ---------------------------------------------------------------

    def save_link(self, uid: str, name: str, category: Category, secret: dict, info: dict | None = None) -> None:
        with self._db:
            self._db.execute(
                """INSERT INTO links (uid, name, category, secret, info, linked_at) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(uid) DO UPDATE SET name=excluded.name, category=excluded.category,
                       secret=excluded.secret, info=excluded.info, linked_at=excluded.linked_at""",
                (uid, name, category.value, vault.seal(json.dumps(secret)), json.dumps(info or {}, default=str), time.time()),
            )
            self._apply_links()

    def get_link(self, uid: str) -> dict | None:
        row = self._db.execute("SELECT * FROM links WHERE uid = ?", (uid,)).fetchone()
        if row is None:
            return None
        return {"name": row["name"], "category": Category(row["category"]),
                "secret": json.loads(vault.unseal(row["secret"])), "info": json.loads(row["info"])}

    def _add_missing_columns(self) -> None:
        """Columns added after a table was first made (CREATE TABLE IF NOT EXISTS keeps the old one)."""
        columns = {r["name"] for r in self._db.execute("PRAGMA table_info(streamers)")}
        if "adb" not in columns:
            with self._db:
                self._db.execute("ALTER TABLE streamers ADD COLUMN adb INTEGER NOT NULL DEFAULT 0")
        columns = {r["name"] for r in self._db.execute("PRAGMA table_info(dashboards)")}
        if "columns" not in columns:
            with self._db:
                self._db.execute("ALTER TABLE dashboards ADD COLUMN columns INTEGER NOT NULL DEFAULT 8")

    def _seal_plain_secrets(self) -> None:
        """Databases from before sealing hold plain Link secrets: seal them once."""
        rows = self._db.execute("SELECT uid, secret FROM links").fetchall()
        with self._db:
            for r in rows:
                if vault.is_sealed(r["secret"]):
                    continue
                sealed = vault.seal(r["secret"])
                if sealed != r["secret"]:  # no store on this platform
                    self._db.execute("UPDATE links SET secret = ? WHERE uid = ?", (sealed, r["uid"]))

    def _apply_links(self) -> None:
        self._db.execute(
            """UPDATE devices SET category = links.category, brand_name = links.name, readiness = 'ready', note = ''
               FROM links WHERE devices.uid = links.uid"""
        )

    # --- Streamers -----------------------------------------------------------

    def streamer(self, uid: str) -> dict | None:
        """{"is_tv", "apps", "adb"} for a Streamer that has been set up, else None."""
        row = self._db.execute("SELECT * FROM streamers WHERE uid = ?", (uid,)).fetchone()
        if row is None:
            return None
        return {"is_tv": bool(row["is_tv"]), "apps": json.loads(row["apps"]), "adb": bool(row["adb"])}

    def set_streamer(
        self, uid: str, is_tv: bool | None = None, apps: list[dict] | None = None, adb: bool | None = None
    ) -> None:
        """Save a Streamer's setup; a field left as None keeps its current value."""
        current = self.streamer(uid) or {"is_tv": False, "apps": [], "adb": False}
        is_tv = current["is_tv"] if is_tv is None else is_tv
        apps = current["apps"] if apps is None else apps
        adb = current["adb"] if adb is None else adb
        with self._db:
            self._db.execute(
                """INSERT INTO streamers (uid, is_tv, apps, adb) VALUES (?, ?, ?, ?)
                   ON CONFLICT(uid) DO UPDATE SET is_tv=excluded.is_tv, apps=excluded.apps, adb=excluded.adb""",
                (uid, int(is_tv), json.dumps(apps), int(adb)),
            )

    # --- Remote Devices ----------------------------------------------------

    def add_remote(self, name: str, category: Category, transmitter_uid: str, source: str, signals: dict) -> str:
        uid = f"remote:{uuid.uuid4().hex[:12]}"
        try:
            with self._db:
                self._db.execute(
                    "INSERT INTO remote_devices (uid, name, category, transmitter_uid, source, signals, created)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (uid, name, category.value, transmitter_uid, source, json.dumps(signals), time.time()),
                )
        except sqlite3.IntegrityError:
            raise ValueError(f"a remote device named '{name}' already exists") from None
        return uid

    def remotes(self) -> list[RemoteDevice]:
        rows = self._db.execute("SELECT * FROM remote_devices ORDER BY category, name").fetchall()
        return [self._to_remote(r) for r in rows]

    def resolve_remote(self, ref: str) -> RemoteDevice:
        row = self._db.execute(
            "SELECT * FROM remote_devices WHERE uid = ? OR name = ? COLLATE NOCASE", (ref, ref)
        ).fetchone()
        if row is None:
            raise LookupError(f"no remote device '{ref}'")
        return self._to_remote(row)

    def set_remote_signals(self, uid: str, source: str, signals: dict) -> None:
        """Swap the Signals (e.g. trying another code set). Assumed State is reset."""
        with self._db:
            self._db.execute(
                "UPDATE remote_devices SET source = ?, signals = ?, assumed_state = NULL WHERE uid = ?",
                (source, json.dumps(signals), uid),
            )

    def set_remote_button(self, uid: str, name: str, signal: str | None) -> None:
        """Add/replace one learned button on a button Remote Device (None removes it)."""
        remote = self.resolve_remote(uid)
        if remote.signals.get("format") != "buttons":
            raise ValueError(f"'{remote.name}' doesn't use buttons")
        buttons = remote.signals["buttons"]
        if signal is None:
            buttons.pop(name, None)
        else:
            buttons[name] = signal
        with self._db:
            self._db.execute("UPDATE remote_devices SET signals = ? WHERE uid = ?", (json.dumps(remote.signals), uid))

    def set_assumed_state(self, uid: str, state: dict) -> None:
        with self._db:
            self._db.execute("UPDATE remote_devices SET assumed_state = ? WHERE uid = ?", (json.dumps(state), uid))

    def rename_remote(self, uid: str, name: str) -> None:
        try:
            with self._db:
                self._db.execute("UPDATE remote_devices SET name = ? WHERE uid = ?", (name, uid))
        except sqlite3.IntegrityError:
            raise ValueError(f"a remote device named '{name}' already exists") from None

    def forget_remote(self, uid: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM remote_devices WHERE uid = ?", (uid,))
            self._leave_groups(uid)
            self._drop_hotkeys(uid)
            self._drop_dashboard_items()
            self._trim_automations()
            self._trim_scenes()

    # --- Groups --------------------------------------------------------------

    def add_group(self, name: str, members: list[str], made_by: str = "user") -> str:
        uid = f"group:{uuid.uuid4().hex[:12]}"
        try:
            with self._db:
                self._db.execute(
                    "INSERT INTO groups (uid, name, made_by, created) VALUES (?, ?, ?, ?)",
                    (uid, name, made_by, time.time()),
                )
                self._set_members(uid, members)
        except sqlite3.IntegrityError:
            raise ValueError(f"a group named '{name}' already exists") from None
        return uid

    def groups(self) -> list[Group]:
        rows = self._db.execute("SELECT * FROM groups ORDER BY created").fetchall()
        return [self._to_group(r) for r in rows]

    def get_group(self, uid: str) -> Group:
        row = self._db.execute("SELECT * FROM groups WHERE uid = ?", (uid,)).fetchone()
        if row is None:
            raise LookupError(f"no group '{uid}'")
        return self._to_group(row)

    def update_group(self, uid: str, name: str | None = None, members: list[str] | None = None) -> None:
        self.get_group(uid)  # 404s early
        try:
            with self._db:
                if name is not None:
                    self._db.execute("UPDATE groups SET name = ? WHERE uid = ?", (name, uid))
                if members is not None:
                    self._set_members(uid, members)
        except sqlite3.IntegrityError:
            raise ValueError(f"a group named '{name}' already exists") from None

    def forget_group(self, uid: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM group_members WHERE group_uid = ?", (uid,))
            if self._db.execute("DELETE FROM groups WHERE uid = ?", (uid,)).rowcount == 0:
                raise LookupError(f"no group '{uid}'")
            self._drop_hotkeys(uid)
            self._drop_dashboard_items()
            self._trim_automations()
            self._trim_scenes()

    def _set_members(self, uid: str, members: list[str]) -> None:
        self._db.execute("DELETE FROM group_members WHERE group_uid = ?", (uid,))
        self._db.executemany(
            "INSERT INTO group_members (group_uid, device_uid, position) VALUES (?, ?, ?)",
            [(uid, m, i) for i, m in enumerate(dict.fromkeys(members))],
        )

    def _leave_groups(self, device_uid: str) -> None:
        """A forgotten Device leaves its Groups; a Group left with nobody in it goes too."""
        self._db.execute("DELETE FROM group_members WHERE device_uid = ?", (device_uid,))
        self._db.execute("DELETE FROM groups WHERE uid NOT IN (SELECT group_uid FROM group_members)")

    # --- Hotkeys -------------------------------------------------------------

    def add_hotkey(self, keys: str, target: str, action: dict, made_by: str = "user") -> str:
        uid = f"hotkey:{uuid.uuid4().hex[:12]}"
        try:
            with self._db:
                self._db.execute(
                    "INSERT INTO hotkeys (uid, keys, target, action, made_by, created) VALUES (?, ?, ?, ?, ?, ?)",
                    (uid, keys, target, json.dumps(action), made_by, time.time()),
                )
        except sqlite3.IntegrityError:
            raise ValueError(f"another Hotkey already uses {keys}") from None
        return uid

    def hotkeys(self) -> list[Hotkey]:
        rows = self._db.execute("SELECT * FROM hotkeys ORDER BY created").fetchall()
        return [self._to_hotkey(r) for r in rows]

    def get_hotkey(self, uid: str) -> Hotkey:
        row = self._db.execute("SELECT * FROM hotkeys WHERE uid = ?", (uid,)).fetchone()
        if row is None:
            raise LookupError(f"no Hotkey '{uid}'")
        return self._to_hotkey(row)

    def update_hotkey(self, uid: str, keys: str | None = None, target: str | None = None,
                      action: dict | None = None) -> None:
        self.get_hotkey(uid)  # 404s early
        try:
            with self._db:
                for column, value in (("keys", keys), ("target", target),
                                      ("action", json.dumps(action) if action is not None else None)):
                    if value is not None:
                        self._db.execute(f"UPDATE hotkeys SET {column} = ? WHERE uid = ?", (value, uid))  # noqa: S608
        except sqlite3.IntegrityError:
            raise ValueError(f"another Hotkey already uses {keys}") from None

    def forget_hotkey(self, uid: str) -> None:
        with self._db:
            if self._db.execute("DELETE FROM hotkeys WHERE uid = ?", (uid,)).rowcount == 0:
                raise LookupError(f"no Hotkey '{uid}'")

    def _drop_hotkeys(self, target: str) -> None:
        """Forgetting a Device, Group or Automation deletes its Hotkeys, and those of a Group that went with it."""
        self._db.execute("DELETE FROM hotkeys WHERE target = ?", (target,))
        self._db.execute("DELETE FROM hotkeys WHERE target LIKE 'group:%' AND target NOT IN (SELECT uid FROM groups)")

    # --- Dashboards ----------------------------------------------------------

    def add_dashboard(self, name: str, columns: int, items: list[dict]) -> str:
        uid = uuid.uuid4().hex[:12]
        try:
            with self._db:
                position = self._db.execute("SELECT COALESCE(MAX(position) + 1, 0) FROM dashboards").fetchone()[0]
                self._db.execute(
                    "INSERT INTO dashboards (uid, name, columns, items, position, created) VALUES (?, ?, ?, ?, ?, ?)",
                    (uid, name, columns, json.dumps(items), position, time.time()),
                )
        except sqlite3.IntegrityError:
            raise ValueError(f"a dashboard named '{name}' already exists") from None
        return uid

    def dashboards(self) -> list[Dashboard]:
        rows = self._db.execute("SELECT * FROM dashboards ORDER BY position, created").fetchall()
        return [self._to_dashboard(r) for r in rows]

    def get_dashboard(self, uid: str) -> Dashboard:
        row = self._db.execute("SELECT * FROM dashboards WHERE uid = ?", (uid,)).fetchone()
        if row is None:
            raise LookupError(f"no dashboard '{uid}'")
        return self._to_dashboard(row)

    def update_dashboard(self, uid: str, name: str | None = None, columns: int | None = None,
                         items: list[dict] | None = None) -> None:
        self.get_dashboard(uid)  # 404s early
        try:
            with self._db:
                if name is not None:
                    self._db.execute("UPDATE dashboards SET name = ? WHERE uid = ?", (name, uid))
                if columns is not None:
                    self._db.execute("UPDATE dashboards SET columns = ? WHERE uid = ?", (columns, uid))
                if items is not None:
                    self._db.execute("UPDATE dashboards SET items = ? WHERE uid = ?", (json.dumps(items), uid))
        except sqlite3.IntegrityError:
            raise ValueError(f"a dashboard named '{name}' already exists") from None

    def order_dashboards(self, uids: list[str]) -> None:
        """Put the Dashboards in this order; any left out keep their order after them. Unknown or
        repeated uids are ignored."""
        known = [d.uid for d in self.dashboards()]
        uids = [u for u in dict.fromkeys(uids) if u in known]
        rest = [u for u in known if u not in uids]
        with self._db:
            self._db.executemany(
                "UPDATE dashboards SET position = ? WHERE uid = ?", [(i, u) for i, u in enumerate(uids + rest)]
            )

    def forget_dashboard(self, uid: str) -> None:
        with self._db:
            if self._db.execute("DELETE FROM dashboards WHERE uid = ?", (uid,)).rowcount == 0:
                raise LookupError(f"no dashboard '{uid}'")

    def targets(self) -> set[str]:
        """Every uid a Dashboard item or Hotkey can point at: Devices, Remote Devices and Groups."""
        rows = self._db.execute(
            "SELECT uid FROM devices UNION SELECT uid FROM remote_devices UNION SELECT uid FROM groups"
        ).fetchall()
        return {r["uid"] for r in rows}

    def automation_uids(self) -> set[str]:
        """What a Dashboard's Run button can point at."""
        return {r["uid"] for r in self._db.execute("SELECT uid FROM automations").fetchall()}

    def _drop_dashboard_items(self) -> None:
        """Forgetting a Device or deleting a Group or Automation takes it off every Dashboard."""
        targets = self.targets() | self.automation_uids()
        for r in self._db.execute("SELECT uid, items FROM dashboards").fetchall():
            items = json.loads(r["items"])
            kept = [i for i in items if "target" not in i or i["target"] in targets]
            if len(kept) != len(items):
                self._db.execute("UPDATE dashboards SET items = ? WHERE uid = ?", (json.dumps(kept), r["uid"]))

    # --- Automations -----------------------------------------------------------

    def add_automation(self, name: str, triggers: list[dict], conditions: list[dict], actions: list[dict],
                       match: str = "all", enabled: bool = True, made_by: str = "user") -> str:
        uid = f"automation:{uuid.uuid4().hex[:12]}"
        try:
            with self._db:
                self._db.execute(
                    """INSERT INTO automations (uid, name, enabled, match, triggers, conditions, actions, made_by,
                                              armed, created)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (uid, name, int(enabled), match, json.dumps(triggers), json.dumps(conditions),
                     json.dumps(actions), made_by, time.time(), time.time()),
                )
        except sqlite3.IntegrityError:
            raise ValueError(f"an Automation named '{name}' already exists") from None
        return uid

    def automations(self) -> list[Automation]:
        rows = self._db.execute("SELECT * FROM automations ORDER BY created").fetchall()
        return [self._to_automation(r) for r in rows]

    def get_automation(self, uid: str) -> Automation:
        row = self._db.execute("SELECT * FROM automations WHERE uid = ?", (uid,)).fetchone()
        if row is None:
            raise LookupError(f"no Automation '{uid}'")
        return self._to_automation(row)

    def update_automation(self, uid: str, name: str | None = None, enabled: bool | None = None,
                          match: str | None = None, triggers: list[dict] | None = None,
                          conditions: list[dict] | None = None, actions: list[dict] | None = None) -> None:
        """Change what's given. Any change clears `attention`: the user has looked at it since."""
        self.get_automation(uid)  # 404s early
        values = {"name": name, "enabled": None if enabled is None else int(enabled), "match": match}
        values |= {k: json.dumps(v) for k, v in (("triggers", triggers), ("conditions", conditions),
                                                  ("actions", actions)) if v is not None}
        try:
            with self._db:
                for column, value in values.items():
                    if value is not None:
                        self._db.execute(f"UPDATE automations SET {column} = ? WHERE uid = ?", (value, uid))  # noqa: S608
                self._db.execute("UPDATE automations SET attention = NULL WHERE uid = ?", (uid,))
                if triggers is not None or enabled:
                    self._db.execute("UPDATE automations SET armed = ? WHERE uid = ?", (time.time(), uid))
        except sqlite3.IntegrityError:
            raise ValueError(f"an Automation named '{name}' already exists") from None

    def switch_off(self, uid: str, attention: str) -> None:
        """Switch an Automation off by itself, saying why (e.g. it was caught in a loop)."""
        with self._db:
            self._db.execute("UPDATE automations SET enabled = 0, attention = ? WHERE uid = ?", (attention, uid))

    def forget_automation(self, uid: str) -> None:
        with self._db:
            if self._db.execute("DELETE FROM automations WHERE uid = ?", (uid,)).rowcount == 0:
                raise LookupError(f"no Automation '{uid}'")
            self._db.execute("DELETE FROM automation_runs WHERE automation = ?", (uid,))
            self._drop_hotkeys(uid)
            self._drop_dashboard_items()
            self._trim_automations()  # the Actions that ran it

    def _trim_automations(self) -> None:
        """Forgetting a Device or deleting a Group or Automation removes only the parts naming it (ADR
        0012). One that loses its last Trigger (it would quietly become manual-only) or its last Action
        is switched off."""
        from . import automations

        targets = self.targets() | self.automation_uids()
        for a in self.automations():
            gone = automations.targets_of(a) - targets
            if not gone:
                continue
            triggers, conditions, actions = automations.without(a.triggers, a.conditions, a.actions, gone)
            lost = ("Trigger" if a.triggers and not triggers else None) or ("Action" if not actions else None)
            self._db.execute(
                "UPDATE automations SET triggers = ?, conditions = ?, actions = ? WHERE uid = ?",
                (json.dumps(triggers), json.dumps(conditions), json.dumps(actions), a.uid),
            )
            if lost:
                self._db.execute(
                    "UPDATE automations SET enabled = 0, attention = ? WHERE uid = ?",
                    (f"Switched off: its last {lost} was for a Device, Group or Automation that was removed", a.uid),
                )

    # Runs

    def add_run(self, automation: str, cause: str, outcome: str = "running", steps: list[dict] | None = None,
                started: float | None = None) -> int:
        now = time.time()
        with self._db:
            cur = self._db.execute(
                "INSERT INTO automation_runs (automation, cause, started, ended, outcome, steps) VALUES (?, ?, ?, ?, ?, ?)",
                (automation, cause, started or now, None if outcome == "running" else now, outcome,
                 json.dumps(steps or [])),
            )
            self._db.execute(
                """DELETE FROM automation_runs WHERE automation = ? AND id NOT IN
                   (SELECT id FROM automation_runs WHERE automation = ? ORDER BY id DESC LIMIT ?)""",
                (automation, automation, RUNS_KEPT),
            )
        return cur.lastrowid

    def update_run(self, run_id: int, steps: list[dict], outcome: str = "running", note: str = "") -> None:
        """Save a Run's progress; any outcome but running ends it."""
        ended = None if outcome == "running" else time.time()
        with self._db:
            self._db.execute("UPDATE automation_runs SET steps = ?, outcome = ?, ended = ?, note = ? WHERE id = ?",
                             (json.dumps(steps), outcome, ended, note, run_id))

    def runs(self, automation: str | None = None, limit: int = RUNS_KEPT, outcome: str | None = None) -> list[Run]:
        """Newest first."""
        where, args = [], []
        if automation is not None:
            where.append("automation = ?")
            args.append(automation)
        if outcome is not None:
            where.append("outcome = ?")
            args.append(outcome)
        sql = "SELECT * FROM automation_runs" + (" WHERE " + " AND ".join(where) if where else "")
        rows = self._db.execute(sql + " ORDER BY id DESC LIMIT ?", (*args, limit)).fetchall()
        return [self._to_run(r) for r in rows]

    def last_runs(self) -> dict[str, Run]:
        """Each Automation's latest Run."""
        rows = self._db.execute(
            "SELECT * FROM automation_runs WHERE id IN (SELECT MAX(id) FROM automation_runs GROUP BY automation)"
        ).fetchall()
        return {r["automation"]: self._to_run(r) for r in rows}

    # Notices

    def add_notice(self, title: str, text: str, automation: str | None = None) -> int:
        with self._db:
            cur = self._db.execute(
                "INSERT INTO notices (time, title, text, automation) VALUES (?, ?, ?, ?)",
                (time.time(), title, text, automation),
            )
            self._db.execute(
                "DELETE FROM notices WHERE id NOT IN (SELECT id FROM notices ORDER BY id DESC LIMIT ?)", (NOTICES_KEPT,)
            )
        return cur.lastrowid

    def notices(self, after: int = 0, unseen: bool = False) -> list[Notice]:
        """Oldest first."""
        sql = "SELECT * FROM notices WHERE id > ?" + (" AND seen = 0" if unseen else "") + " ORDER BY id"
        return [Notice(id=r["id"], time=r["time"], title=r["title"], text=r["text"], automation=r["automation"],
                       seen=bool(r["seen"])) for r in self._db.execute(sql, (after,)).fetchall()]

    def mark_notices_seen(self, ids: list[int] | None = None) -> None:
        """All of them when `ids` is None."""
        with self._db:
            if ids is None:
                self._db.execute("UPDATE notices SET seen = 1")
            else:
                self._db.executemany("UPDATE notices SET seen = 1 WHERE id = ?", [(i,) for i in ids])

    # --- Scenes ----------------------------------------------------------------

    def add_scene(self, name: str, parts: list[dict], icon: str = "sparkles", made_by: str = "user") -> str:
        uid = f"scene:{uuid.uuid4().hex[:12]}"
        try:
            with self._db:
                position = self._db.execute("SELECT COALESCE(MAX(position) + 1, 0) FROM scenes").fetchone()[0]
                self._db.execute(
                    "INSERT INTO scenes (uid, name, icon, parts, position, made_by, created) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (uid, name, icon, json.dumps(parts), position, made_by, time.time()),
                )
        except sqlite3.IntegrityError:
            raise ValueError(f"a Scene named '{name}' already exists") from None
        return uid

    def scenes(self) -> list[Scene]:
        rows = self._db.execute("SELECT * FROM scenes ORDER BY position, created").fetchall()
        return [self._to_scene(r) for r in rows]

    def get_scene(self, uid: str) -> Scene:
        row = self._db.execute("SELECT * FROM scenes WHERE uid = ?", (uid,)).fetchone()
        if row is None:
            raise LookupError(f"no Scene '{uid}'")
        return self._to_scene(row)

    def update_scene(self, uid: str, name: str | None = None, icon: str | None = None,
                     parts: list[dict] | None = None) -> None:
        """Change what's given. Any change clears `attention`: the user has looked at it since."""
        self.get_scene(uid)  # 404s early
        values = {"name": name, "icon": icon, "parts": json.dumps(parts) if parts is not None else None}
        try:
            with self._db:
                for column, value in values.items():
                    if value is not None:
                        self._db.execute(f"UPDATE scenes SET {column} = ? WHERE uid = ?", (value, uid))  # noqa: S608
                self._db.execute("UPDATE scenes SET attention = NULL WHERE uid = ?", (uid,))
        except sqlite3.IntegrityError:
            raise ValueError(f"a Scene named '{name}' already exists") from None

    def order_scenes(self, uids: list[str]) -> None:
        """Put the Scenes in this order; any left out keep their order after them."""
        known = [s.uid for s in self.scenes()]
        uids = [u for u in dict.fromkeys(uids) if u in known]
        rest = [u for u in known if u not in uids]
        with self._db:
            self._db.executemany("UPDATE scenes SET position = ? WHERE uid = ?", [(i, u) for i, u in enumerate(uids + rest)])

    def forget_scene(self, uid: str) -> None:
        with self._db:
            if self._db.execute("DELETE FROM scenes WHERE uid = ?", (uid,)).rowcount == 0:
                raise LookupError(f"no Scene '{uid}'")

    def _trim_scenes(self) -> None:
        """Forgetting a Device or deleting a Group drops only its part (ADR 0013). A Scene left with
        nothing is kept, marked as needing attention."""
        from . import scenes

        targets = self.targets()
        for sc in self.scenes():
            parts = scenes.without(sc.parts, {p["target"] for p in sc.parts} - targets)
            if len(parts) == len(sc.parts):
                continue
            self._db.execute("UPDATE scenes SET parts = ? WHERE uid = ?", (json.dumps(parts), sc.uid))
            if not parts:
                self._db.execute(
                    "UPDATE scenes SET attention = ? WHERE uid = ?",
                    ("Nothing is left in it: its Devices were forgotten or its Groups deleted", sc.uid),
                )

    # --- Settings ------------------------------------------------------------

    def setting(self, key: str, default=None):
        row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_setting(self, key: str, value) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )

    # --- Approved Browsers ---------------------------------------------------

    def approve_browser(self, token: str, name: str) -> str:
        browser_id = uuid.uuid4().hex[:12]
        now = time.time()
        with self._db:
            self._db.execute(
                "INSERT INTO approved_browsers (id, token_hash, name, approved_at, last_seen) VALUES (?, ?, ?, ?, ?)",
                (browser_id, _hash_token(token), name, now, now),
            )
        return browser_id

    def browser_for_token(self, token: str) -> ApprovedBrowser | None:
        row = self._db.execute(
            "SELECT * FROM approved_browsers WHERE token_hash = ?", (_hash_token(token),)
        ).fetchone()
        return self._to_browser(row) if row else None

    def approved_browsers(self) -> list[ApprovedBrowser]:
        rows = self._db.execute("SELECT * FROM approved_browsers ORDER BY last_seen DESC").fetchall()
        return [self._to_browser(r) for r in rows]

    def browser_seen(self, browser_id: str) -> None:
        with self._db:
            self._db.execute("UPDATE approved_browsers SET last_seen = ? WHERE id = ?", (time.time(), browser_id))

    def revoke_browser(self, browser_id: str) -> None:
        with self._db:
            if self._db.execute("DELETE FROM approved_browsers WHERE id = ?", (browser_id,)).rowcount == 0:
                raise LookupError(f"no approved browser '{browser_id}'")

    # --- Internals ---------------------------------------------------------

    def _to_group(self, r: sqlite3.Row) -> Group:
        members = self._db.execute(
            "SELECT device_uid FROM group_members WHERE group_uid = ? ORDER BY position", (r["uid"],)
        ).fetchall()
        return Group(uid=r["uid"], name=r["name"], members=[m["device_uid"] for m in members], made_by=r["made_by"])

    def _to_dashboard(self, r: sqlite3.Row) -> Dashboard:
        items = dashboard_items.upgrade(json.loads(r["items"]), r["columns"])
        return Dashboard(uid=r["uid"], name=r["name"], columns=r["columns"], items=items)

    def _to_hotkey(self, r: sqlite3.Row) -> Hotkey:
        return Hotkey(uid=r["uid"], keys=r["keys"], target=r["target"], action=json.loads(r["action"]),
                      made_by=r["made_by"])

    def _to_automation(self, r: sqlite3.Row) -> Automation:
        return Automation(uid=r["uid"], name=r["name"], enabled=bool(r["enabled"]), match=r["match"],
                          triggers=json.loads(r["triggers"]), conditions=json.loads(r["conditions"]),
                          actions=json.loads(r["actions"]), attention=r["attention"], made_by=r["made_by"],
                          armed=r["armed"])

    def _to_scene(self, r: sqlite3.Row) -> Scene:
        return Scene(uid=r["uid"], name=r["name"], icon=r["icon"], parts=json.loads(r["parts"]),
                     attention=r["attention"], made_by=r["made_by"])

    def _to_run(self, r: sqlite3.Row) -> Run:
        return Run(id=r["id"], automation=r["automation"], cause=r["cause"], started=r["started"], ended=r["ended"],
                   outcome=r["outcome"], steps=json.loads(r["steps"]), note=r["note"])

    def _to_browser(self, r: sqlite3.Row) -> ApprovedBrowser:
        return ApprovedBrowser(id=r["id"], name=r["name"], approved_at=r["approved_at"], last_seen=r["last_seen"])

    def _to_remote(self, r: sqlite3.Row) -> RemoteDevice:
        return RemoteDevice(
            uid=r["uid"],
            name=r["name"],
            category=Category(r["category"]),
            transmitter_uid=r["transmitter_uid"],
            source=r["source"],
            signals=json.loads(r["signals"]),
            assumed_state=json.loads(r["assumed_state"]) if r["assumed_state"] else None,
        )

    def _to_known(self, r: sqlite3.Row) -> KnownDevice:
        return KnownDevice(
            uid=r["uid"],
            brand=r["brand"],
            category=Category(r["category"]),
            readiness=Readiness(r["readiness"]),
            ip=r["ip"],
            model=r["model"],
            mac=r["mac"],
            brand_name=r["brand_name"],
            user_name=r["user_name"],
            note=r["note"],
            raw=json.loads(r["raw"]),
            first_seen=r["first_seen"],
            last_seen=r["last_seen"],
            is_new=bool(r["is_new"]),
            online=bool(r["online"]),
        )
