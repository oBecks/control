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
"""


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
        # The API opens a Registry per request and may touch it from several worker threads.
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
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

    def forget(self, uid: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM devices WHERE uid = ?", (uid,))

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
