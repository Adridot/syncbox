from pathlib import Path

from app.db import LocalDatabase
from app.models import AppSettings, TagRuleIn


def test_database_migrates_and_stores_settings(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    settings = AppSettings(
        spotifyClientId="client-id",
        spotifyUsername="my-user",
        rekordboxDatabaseDir="/tmp/rekordbox",
        storageRoot="/tmp/storage",
    )

    database.save_app_settings(settings)
    stored = database.get_app_settings(settings)

    assert stored.spotify_client_id == "client-id"
    assert stored.spotify_username == "my-user"
    assert stored.storage_root == "/tmp/storage"


def test_save_app_settings_preserves_credentials_on_blank(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    database.save_app_settings(
        AppSettings(
            spotifyClientId="cid",
            spotifyClientSecret="secret",
            spotifyUsername="user",
            deemixArl="arl-token",
            rekordboxDatabaseDir="/tmp/rekordbox",
            storageRoot="/tmp/storage",
        )
    )

    # A blank round-trip (e.g. a UI that didn't echo the secret back) must NOT
    # wipe the stored credentials — this is the "settings reset" guard.
    result = database.save_app_settings(
        AppSettings(
            spotifyClientId="",
            spotifyClientSecret="",
            spotifyUsername="",
            deemixArl="",
            rekordboxDatabaseDir="/tmp/rekordbox",
            storageRoot="/tmp/storage",
        )
    )

    assert result.spotify_client_secret == "secret"
    assert result.deemix_arl == "arl-token"
    assert result.spotify_username == "user"
    assert database.get_setting("spotify_client_secret") == "secret"


def test_default_data_dir_is_absolute_and_stable(monkeypatch) -> None:
    from app.config import load_config

    # Without RBSYNC_DATA_DIR the DB path must be absolute (never cwd-relative),
    # so it doesn't move — and reset settings — when launched from a different dir.
    monkeypatch.delenv("RBSYNC_DATA_DIR", raising=False)
    cfg = load_config()
    assert cfg.app_database_path.is_absolute()


def test_tag_rule_upsert(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()

    saved = database.upsert_tag_rule(
        TagRuleIn(
            sourcePlaylistId="playlist-id",
            sourcePlaylistName="Dinner",
            tags=["Dinner", "Client"],
            enabled=True,
        )
    )

    assert saved.id > 0
    assert database.list_tag_rules()[0].tags == ["Dinner", "Client"]


