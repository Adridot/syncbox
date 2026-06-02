from pathlib import Path

from app.db import LocalDatabase
from app.models import AppSettings, TagPlaylistMappingIn, TagRuleIn


def test_database_migrates_and_stores_settings(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    settings = AppSettings(
        spotifyClientId="client-id",
        spotifyRedirectUri="http://127.0.0.1:8765/api/spotify/callback",
        rekordboxDatabaseDir="/tmp/rekordbox",
        storageRoot="/tmp/storage",
    )

    database.save_app_settings(settings)
    stored = database.get_app_settings(settings)

    assert stored.spotify_client_id == "client-id"
    assert stored.storage_root == "/tmp/storage"


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


def test_tag_playlist_mapping_upsert(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()

    saved = database.upsert_tag_playlist_mapping(
        TagPlaylistMappingIn(
            tagName="Cocktail",
            spotifyPlaylistId="spotify-playlist",
            spotifyPlaylistName="Cocktail Spotify",
            enabled=True,
        )
    )

    assert saved.id > 0
    assert database.list_tag_playlist_mappings()[0].tag_name == "Cocktail"
