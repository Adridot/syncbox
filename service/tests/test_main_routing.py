"""Endpoint-level guardrails for the Spotify error routing in app.main.

These import app.main, which binds a module-level database — tests/conftest.py
forces all config paths to temp dirs, so this never touches real user data.
"""

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main
from app.spotify import SpotifyAuthError

VALID_PLAYLIST_URL = "https://open.spotify.com/playlist/3cEYpjA9oz9GiPac4AsH4n"


def test_spotify_http_error_maps_404_to_404_else_401() -> None:
    # Regression: a Spotify 404 (private/deleted playlist) is not an auth failure,
    # so it must surface as HTTP 404 with its message — not a misleading 401.
    not_found = main.spotify_http_error(SpotifyAuthError("It may be private", status_code=404))
    assert isinstance(not_found, HTTPException)
    assert not_found.status_code == 404
    assert "private" in str(not_found.detail).lower()

    bad_token = main.spotify_http_error(SpotifyAuthError("token revoked", status_code=401))
    assert bad_token.status_code == 401

    no_code = main.spotify_http_error(SpotifyAuthError("generic failure"))
    assert no_code.status_code == 401


def test_analyze_endpoint_returns_404_not_401_for_inaccessible_playlist(monkeypatch) -> None:
    # Regression: an inaccessible (private) playlist returned a confusing 401; the
    # event analyze endpoint must return 404 with the actionable message.
    class FakeSpotify:
        def __init__(self, _database) -> None:
            pass

        def is_account_connected(self) -> bool:
            return False

        async def get_playlist(self, _playlist_id):
            raise SpotifyAuthError(
                "Playlist not found. If it's private, connect your Spotify account "
                "in Settings.",
                status_code=404,
            )

        async def get_playlist_items(self, _playlist_id):
            return []

    monkeypatch.setattr(main, "SpotifyClient", FakeSpotify)

    main.database.migrate()  # the module-level DB is a throwaway temp (conftest)
    client = TestClient(main.app)
    response = client.post(
        "/api/events/spotify/analyze",
        json={"playlistUrl": VALID_PLAYLIST_URL, "eventName": "Routing Test"},
    )
    assert response.status_code == 404
    assert "private" in response.json()["detail"].lower()


def test_sync_all_keeps_going_when_one_playlist_is_inaccessible(monkeypatch) -> None:
    # Regression: a private/deleted source (404) used to abort the whole sync-all
    # run as if the token were dead. It must count as one failure while the rest
    # still sync.
    from app.models import LibraryReview, LibrarySourceIn

    main.database.migrate()
    source_a = main.database.upsert_library_source(
        LibrarySourceIn(spotifyPlaylistId="pl-a", spotifyPlaylistName="Private One", tags=[])
    )
    main.database.upsert_library_source(
        LibrarySourceIn(spotifyPlaylistId="pl-b", spotifyPlaylistName="Public One", tags=[])
    )

    async def fake_sync(database, adapter, client, source_id):
        if source_id == source_a.id:
            raise SpotifyAuthError("It may be private", status_code=404)
        source = next(s for s in database.list_library_sources() if s.id == source_id)
        return LibraryReview(
            source=source,
            totalTracks=0,
            newTracks=0,
            matchedTracks=0,
            missingTracks=0,
            readyTracks=0,
            importedTracks=0,
            ignoredTracks=0,
            conflictTracks=0,
            removedTracks=0,
            tracks=[],
        )

    monkeypatch.setattr(main, "sync_library_source", fake_sync)
    monkeypatch.setattr(main, "SpotifyClient", lambda _database: object())

    client = TestClient(main.app)
    response = client.post("/api/library/sources/sync-all")

    assert response.status_code == 200
    names = [item["source"]["spotifyPlaylistName"] for item in response.json()]
    assert names == ["Public One"]  # B synced even though A returned 404
