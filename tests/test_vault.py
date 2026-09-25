import sqlite3
import sys

import pytest

from control.engine import vault
from control.engine.found_device import Category
from control.engine.registry import Registry

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")


def stored_secret(path, uid: str) -> str:
    db = sqlite3.connect(path)
    try:
        return db.execute("SELECT secret FROM links WHERE uid = ?", (uid,)).fetchone()[0]
    finally:
        db.close()


def test_unseal_passes_plain_text_through():
    assert vault.unseal('{"local_key": "k"}') == '{"local_key": "k"}'


@windows_only
def test_seal_round_trips_and_hides_the_text():
    sealed = vault.seal("secret-local-key")
    assert vault.is_sealed(sealed) and "secret-local-key" not in sealed
    assert vault.unseal(sealed) == "secret-local-key"


@windows_only
def test_registry_never_writes_the_local_key_in_plain_text(tmp_path):
    path = tmp_path / "test.db"
    r = Registry(path)
    r.save_link("tuya:abc", "Kettle", Category.PLUG, {"local_key": "secret-local-key"})
    assert "secret-local-key" not in stored_secret(path, "tuya:abc")
    assert r.get_link("tuya:abc")["secret"] == {"local_key": "secret-local-key"}
    r.close()


@windows_only
def test_opening_an_old_database_seals_its_plain_secrets_once(tmp_path):
    path = tmp_path / "test.db"
    Registry(path).close()
    db = sqlite3.connect(path)
    with db:
        db.execute(
            "INSERT INTO links (uid, name, category, secret, info, linked_at) VALUES (?, ?, ?, ?, '{}', 0)",
            ("tuya:abc", "Kettle", "plug", '{"local_key": "secret-local-key"}'),
        )
    db.close()

    r = Registry(path)
    sealed = stored_secret(path, "tuya:abc")
    assert vault.is_sealed(sealed) and "secret-local-key" not in sealed
    r.close()

    r = Registry(path)  # reopening leaves it alone
    assert stored_secret(path, "tuya:abc") == sealed
    assert r.get_link("tuya:abc")["secret"] == {"local_key": "secret-local-key"}
    r.close()
