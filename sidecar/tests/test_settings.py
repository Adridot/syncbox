"""Tests for the single settings store (SPEC-UNIFIED 5.10)."""

import pytest

from syncbox import appdb
from syncbox.settings import DEFAULTS, Settings, validate_directory


@pytest.fixture
def settings(tmp_path):
    conn = appdb.open_app_db(tmp_path / "app.db")
    return Settings(conn)


def test_defaults_apply_at_read_without_writing(settings):
    assert settings.get("backup_retention") == 15
    assert settings.get("language") == "en"
    assert settings.all() == DEFAULTS
    # Reading must not have persisted anything (never re-saved at boot).
    stored = settings._conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
    assert stored == 0


def test_update_round_trip(settings):
    out = settings.update({"backup_retention": 30, "language": "fr"})
    assert out["backup_retention"] == 30
    assert settings.get("language") == "fr"


def test_blank_credential_preserves_stored_value(settings):
    settings.update({"spotify_client_id": "abc123"})
    settings.update({"spotify_client_id": ""})
    assert settings.get("spotify_client_id") == "abc123"
    settings.update({"spotify_client_id": None})
    assert settings.get("spotify_client_id") == "abc123"


def test_blank_non_credential_is_stored(settings):
    settings.update({"storage_root": "/tmp/x"})
    settings.update({"storage_root": ""})
    assert settings.get("storage_root") == ""


def test_unknown_key_rejected(settings):
    with pytest.raises(KeyError):
        settings.update({"deezer_arl": "nope"})  # no such setting exists in v1
    with pytest.raises(KeyError):
        settings.get("arl")


def test_wrong_type_rejected_and_rolled_back(settings):
    with pytest.raises(TypeError):
        settings.update({"language": "fr", "backup_retention": "many"})
    # the whole update rolled back - language untouched
    assert settings.get("language") == "en"


def test_validate_directory(tmp_path):
    assert validate_directory("") == (False, "empty")
    assert validate_directory("relative/path") == (False, "not absolute")
    assert validate_directory(str(tmp_path / "missing")) == (False, "not found")
    assert validate_directory(str(tmp_path)) == (True, "ok")
