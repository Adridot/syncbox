from pathlib import Path

from app.db import LocalDatabase


def _db(tmp_path: Path, name: str = "app.sqlite3") -> LocalDatabase:
    db = LocalDatabase(tmp_path / name)
    db.migrate()
    return db


def test_settings_export_import_round_trip(tmp_path: Path) -> None:
    db = _db(tmp_path)
    db.set_setting("spotify_client_id", "CID123")
    db.set_setting("storage_root", "/Volumes/Music")
    db.set_setting("spotify_access_token", "tok")
    # Transient OAuth handshake values must be excluded.
    db.set_setting("spotify_oauth_state", "STATE")

    exported = db.export_settings()
    assert exported["spotify_client_id"] == "CID123"
    assert exported["spotify_access_token"] == "tok"
    assert "spotify_oauth_state" not in exported

    fresh = _db(tmp_path, "fresh.sqlite3")
    applied = fresh.import_settings(exported)
    assert applied >= 2
    assert fresh.get_setting("spotify_client_id") == "CID123"
    assert fresh.get_setting("storage_root") == "/Volumes/Music"


def test_snapshot_validate_and_replace(tmp_path: Path) -> None:
    db = _db(tmp_path)
    db.set_setting("storage_root", "/original")

    snapshot = db.snapshot_to(tmp_path / "exports" / "backup.sqlite3")
    assert snapshot.exists()
    assert db.is_valid_app_database(snapshot)

    # A non-DB file is rejected.
    junk = tmp_path / "junk.sqlite3"
    junk.write_bytes(b"not a database")
    assert not db.is_valid_app_database(junk)

    # Mutate live, then restore from the snapshot.
    db.set_setting("storage_root", "/changed")
    assert db.get_setting("storage_root") == "/changed"
    safety = db.replace_with(snapshot)
    assert Path(safety).exists()
    assert db.get_setting("storage_root") == "/original"


def test_import_settings_skips_non_portable(tmp_path: Path) -> None:
    db = _db(tmp_path)
    applied = db.import_settings(
        {"spotify_client_id": "X", "spotify_pkce_verifier": "secret"}
    )
    assert applied == 1
    assert db.get_setting("spotify_pkce_verifier") == ""
