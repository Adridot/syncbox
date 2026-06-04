import base64
from pathlib import Path

from app.db import LocalDatabase
from app.spotify import (
    SpotifyClient,
    parse_playlist_id,
    parse_track_id,
    playlist_items_to_tracks,
    summarize_playlist_page,
    track_payload_to_spotify_track,
)


def test_app_token_uses_client_credentials(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    import httpx

    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    database.set_setting("spotify_client_id", "cid")
    database.set_setting("spotify_client_secret", "sec")
    captured: dict = {}

    class FakeResp:
        status_code = 200
        text = ""

        def json(self):
            return {"access_token": "TKN", "expires_in": 3600}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, *, data=None, headers=None):
            captured["data"] = data
            captured["headers"] = headers
            return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    token = asyncio.run(SpotifyClient(database)._get_app_token())

    # Client-Credentials grant with HTTP Basic auth — no browser, no user.
    assert token == "TKN"
    assert captured["data"] == {"grant_type": "client_credentials"}
    expected = "Basic " + base64.b64encode(b"cid:sec").decode("ascii")
    assert captured["headers"]["Authorization"] == expected
    # Token is cached in settings for reuse.
    assert database.get_setting("spotify_app_token") == "TKN"


def test_app_token_requires_credentials(tmp_path: Path) -> None:
    import asyncio

    import pytest

    from app.spotify import SpotifyAuthError

    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    with pytest.raises(SpotifyAuthError):
        asyncio.run(SpotifyClient(database)._get_app_token())


def test_parse_track_id_from_url() -> None:
    assert parse_track_id("https://open.spotify.com/track/abc123?si=xyz") == "abc123"


def test_parse_track_id_from_uri_and_raw() -> None:
    assert parse_track_id("spotify:track:abc123") == "abc123"
    assert parse_track_id("abc123") == "abc123"


def test_track_payload_to_spotify_track_valid() -> None:
    track = track_payload_to_spotify_track(
        {
            "id": "t1",
            "uri": "spotify:track:t1",
            "name": "Song",
            "artists": [{"name": "Artist A"}, {"name": "Artist B"}],
            "duration_ms": 200000,
            "external_ids": {"isrc": "USRC11111111"},
            "type": "track",
        }
    )
    assert track is not None
    assert track.id == "t1"
    assert track.artists == ["Artist A", "Artist B"]
    assert track.isrc == "USRC11111111"


def test_track_payload_to_spotify_track_rejects_local_and_missing() -> None:
    assert track_payload_to_spotify_track({"id": "x", "uri": "u", "is_local": True}) is None
    assert track_payload_to_spotify_track({"id": None, "uri": None}) is None
    assert track_payload_to_spotify_track({"type": "episode", "id": "e", "uri": "u"}) is None


def test_parse_playlist_id_from_url() -> None:
    playlist_id = parse_playlist_id(
        "https://open.spotify.com/playlist/abc123?si=tracking"
    )

    assert playlist_id == "abc123"


def test_parse_playlist_id_from_uri() -> None:
    assert parse_playlist_id("spotify:playlist:abc123") == "abc123"


def test_summarize_playlist_page_prefers_items_total() -> None:
    page = summarize_playlist_page(
        {
            "limit": 50,
            "offset": 0,
            "total": 1,
            "next": None,
            "items": [
                {
                    "id": "playlist-id",
                    "name": "Client Dinner",
                    "owner": {"display_name": "Adrien"},
                    "items": {"total": 42},
                    "tracks": {"total": 7},
                    "public": False,
                    "snapshot_id": "snapshot",
                    "images": [{"url": "https://images.example/cover.jpg"}],
                    "external_urls": {
                        "spotify": "https://open.spotify.com/playlist/playlist-id"
                    },
                }
            ],
        }
    )

    assert page["items"][0]["trackCount"] == 42
    assert page["items"][0]["name"] == "Client Dinner"
    assert page["items"][0]["imageUrl"] == "https://images.example/cover.jpg"
    assert page["nextOffset"] is None


def test_playlist_items_to_tracks_skips_local_items() -> None:
    tracks = playlist_items_to_tracks(
        [
            {
                "track": {
                    "id": "track-1",
                    "uri": "spotify:track:track-1",
                    "name": "Track",
                    "artists": [{"name": "Artist"}],
                    "duration_ms": 180000,
                    "external_ids": {"isrc": "USRC17607839"},
                    "is_local": False,
                    "type": "track",
                }
            },
            {
                "track": {
                    "id": None,
                    "uri": None,
                    "name": "Local",
                    "artists": [],
                    "duration_ms": 180000,
                    "is_local": True,
                    "type": "track",
                }
            },
        ]
    )

    assert len(tracks) == 1
    assert tracks[0].isrc == "USRC17607839"


def test_is_account_connected_and_disconnect(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    client = SpotifyClient(database)
    assert client.is_account_connected() is False

    database.set_setting("spotify_user_refresh_token", "RT")
    assert client.is_account_connected() is True

    client.disconnect_account()
    assert client.is_account_connected() is False
    assert database.get_setting("spotify_user_access_token") == ""


def test_connection_status_oauth_vs_app(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    client = SpotifyClient(database)

    # App mode: client id + username configured, no account.
    database.set_setting("spotify_client_id", "cid")
    database.set_setting("spotify_username", "adrien")
    app_status = client.connection_status("http://127.0.0.1:8765/api/spotify/callback")
    assert app_status["mode"] == "app"
    assert app_status["connected"] is True
    assert app_status["redirectUri"].endswith("/api/spotify/callback")

    # OAuth mode wins once an account is connected.
    database.set_setting("spotify_user_refresh_token", "RT")
    database.set_setting("spotify_user_display_name", "Adrien D")
    oauth_status = client.connection_status()
    assert oauth_status["mode"] == "oauth"
    assert oauth_status["connected"] is True
    assert oauth_status["displayName"] == "Adrien D"


def test_build_authorization_url_stores_pkce_and_scopes(tmp_path: Path) -> None:
    from app.spotify import SPOTIFY_SCOPES

    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    result = SpotifyClient(database).build_authorization_url(
        "cid", "http://127.0.0.1:8765/api/spotify/callback"
    )

    assert result["authorizationUrl"].startswith(
        "https://accounts.spotify.com/authorize?"
    )
    assert "code_challenge_method=S256" in result["authorizationUrl"]
    for scope in SPOTIFY_SCOPES:
        assert scope.replace(":", "%3A") in result["authorizationUrl"] or scope in result[
            "authorizationUrl"
        ].replace("+", " ").replace("%20", " ")
    # Handshake state persisted for the callback to validate.
    assert database.get_setting("spotify_oauth_state") == result["state"]
    assert database.get_setting("spotify_pkce_verifier")


def _fake_async_client_capturing(captured: dict, *, json_payload: dict):
    """A fake httpx.AsyncClient that records the request URL and returns 200 JSON."""
    import httpx

    class FakeResp:
        status_code = 200
        text = ""

        def json(self):
            return json_payload

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def request(self, method, url, *, params=None, json=None, headers=None):
            captured["url"] = url
            captured["headers"] = headers
            return FakeResp()

    return FakeClient


def test_playlists_route_to_me_when_connected(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    import httpx

    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    database.set_setting("spotify_user_refresh_token", "RT")
    database.set_setting("spotify_user_access_token", "USER")
    # Far-future expiry so no refresh is attempted.
    database.set_setting("spotify_user_expires_at", "9999999999")

    captured: dict = {}
    monkeypatch.setattr(
        httpx, "AsyncClient", _fake_async_client_capturing(captured, json_payload={"items": []})
    )

    asyncio.run(SpotifyClient(database).get_current_user_playlists())

    assert captured["url"].endswith("/me/playlists")
    assert captured["headers"]["Authorization"] == "Bearer USER"


def test_playlists_route_to_username_when_not_connected(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    import httpx

    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    database.set_setting("spotify_username", "adrien")
    database.set_setting("spotify_app_token", "APP")
    database.set_setting("spotify_app_token_expires_at", "9999999999")

    captured: dict = {}
    monkeypatch.setattr(
        httpx, "AsyncClient", _fake_async_client_capturing(captured, json_payload={"items": []})
    )

    asyncio.run(SpotifyClient(database).get_current_user_playlists())

    assert captured["url"].endswith("/users/adrien/playlists")
    assert captured["headers"]["Authorization"] == "Bearer APP"


def test_exchange_callback_stores_tokens_with_confidential_client(
    tmp_path: Path, monkeypatch
) -> None:
    import asyncio

    import httpx

    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    database.set_setting("spotify_client_id", "cid")
    database.set_setting("spotify_client_secret", "sec")
    database.set_setting("spotify_redirect_uri", "http://127.0.0.1:8765/api/spotify/callback")
    database.set_setting("spotify_pkce_verifier", "verifier")
    database.set_setting("spotify_oauth_state", "state123")

    captured: dict = {}

    class FakeResp:
        def __init__(self, payload):
            self._payload = payload

        status_code = 200
        text = ""

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, *, data=None, headers=None):
            captured["token_headers"] = headers
            captured["grant"] = data.get("grant_type")
            return FakeResp(
                {"access_token": "UA", "refresh_token": "UR", "expires_in": 3600}
            )

        async def request(self, method, url, *, params=None, json=None, headers=None):
            # The GET /me identity lookup after the token exchange.
            return FakeResp({"id": "adrien", "display_name": "Adrien D"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    asyncio.run(SpotifyClient(database).exchange_callback("code", "state123"))

    assert database.get_setting("spotify_user_access_token") == "UA"
    assert database.get_setting("spotify_user_refresh_token") == "UR"
    assert database.get_setting("spotify_user_id") == "adrien"
    assert database.get_setting("spotify_user_display_name") == "Adrien D"
    # One-shot handshake values are cleared.
    assert database.get_setting("spotify_oauth_state") == ""
    # Confidential client: token exchange used HTTP Basic (stable refresh token).
    expected = "Basic " + base64.b64encode(b"cid:sec").decode("ascii")
    assert captured["token_headers"]["Authorization"] == expected
    assert captured["grant"] == "authorization_code"


def test_exchange_callback_rejects_bad_state(tmp_path: Path) -> None:
    import asyncio

    import pytest

    from app.spotify import SpotifyAuthError

    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    database.set_setting("spotify_oauth_state", "expected")

    with pytest.raises(SpotifyAuthError):
        asyncio.run(SpotifyClient(database).exchange_callback("code", "wrong"))


def test_refresh_user_token_keeps_existing_refresh_token(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    import httpx

    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    database.set_setting("spotify_client_id", "cid")
    database.set_setting("spotify_user_refresh_token", "ORIGINAL")

    class FakeResp:
        status_code = 200
        text = ""

        def json(self):
            # No refresh_token in the response (stable confidential client).
            return {"access_token": "FRESH", "expires_in": 3600}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    token = asyncio.run(SpotifyClient(database)._get_user_token(force=True))
    assert token == "FRESH"
    # The original refresh token survives when Spotify omits a new one.
    assert database.get_setting("spotify_user_refresh_token") == "ORIGINAL"


def test_app_token_wraps_transport_error(tmp_path, monkeypatch) -> None:
    import asyncio

    import httpx
    import pytest

    from app.spotify import SpotifyAuthError

    db = LocalDatabase(tmp_path / "app.sqlite3")
    db.migrate()
    db.set_setting("spotify_client_id", "cid")
    db.set_setting("spotify_client_secret", "sec")

    class BoomClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            raise httpx.ConnectError("certificate verify failed")

    monkeypatch.setattr(httpx, "AsyncClient", BoomClient)

    with pytest.raises(SpotifyAuthError) as exc:
        asyncio.run(SpotifyClient(db)._get_app_token())
    assert "Could not reach Spotify" in str(exc.value)
