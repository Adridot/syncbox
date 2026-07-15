"""Tests for Spotify PKCE auth and the bounded retry ladder
(SPEC-UNIFIED 5.9, SPEC-01 2.5, research 06 section 2)."""

import base64
import hashlib
import json
import urllib.parse
from pathlib import Path

import pytest

from syncbox import spotify
from syncbox.spotify import (
    REDIRECT_URI,
    SCOPES,
    NotConnectedError,
    SpotifyApiError,
    SpotifyAuth,
    SpotifyClient,
)


class FakeSecrets(dict):
    def get(self, name):  # type: ignore[override]
        return super().get(name)

    def set(self, name, value):
        self[name] = value

    def delete(self, name):
        self.pop(name, None)


class FakeTransport:
    """Scripted (status, headers, body) responses; records every call."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, data=None, headers=None, method="GET"):
        self.calls.append(
            {"url": url, "data": data, "headers": headers or {}, "method": method}
        )
        return self.responses.pop(0)


def token_response(access="acc-1", refresh="ref-1"):
    payload = {"access_token": access}
    if refresh is not None:
        payload["refresh_token"] = refresh
    return (200, {}, json.dumps(payload).encode())


def make_auth(*responses, secrets=None, clock=None):
    transport = FakeTransport(*responses)
    secrets = secrets if secrets is not None else FakeSecrets()
    kwargs = {"transport": transport}
    if clock is not None:
        kwargs["clock"] = clock
    auth = SpotifyAuth(lambda: "client-123", secrets, **kwargs)
    return auth, transport, secrets


# --- PKCE authorization ------------------------------------------------------


def test_begin_authorization_builds_s256_url():
    auth, _, _ = make_auth()
    url = auth.begin_authorization()
    params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    assert params["client_id"] == "client-123"
    assert params["response_type"] == "code"
    assert params["redirect_uri"] == REDIRECT_URI == "http://127.0.0.1:8765/callback"
    assert params["scope"] == SCOPES == "playlist-read-private playlist-read-collaborative"
    assert params["code_challenge_method"] == "S256"
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(auth._verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert params["code_challenge"] == expected
    assert params["state"]


def test_callback_exchanges_code_with_hardcoded_redirect_uri():
    auth, transport, secrets = make_auth(token_response())
    auth.begin_authorization()
    result = auth.handle_callback({"code": "code-1", "state": auth._state})
    assert result == {"ok": True}
    call = transport.calls[0]
    body = dict(urllib.parse.parse_qsl(call["data"].decode()))
    assert call["url"] == spotify.TOKEN_URL
    assert body["grant_type"] == "authorization_code"
    assert body["redirect_uri"] == REDIRECT_URI  # hardcoded, never from request
    assert body["code_verifier"]
    assert body["client_id"] == "client-123"
    assert "client_secret" not in body  # PKCE only, D3
    assert secrets.get(spotify.ACCESS_TOKEN) == "acc-1"
    assert secrets.get(spotify.REFRESH_TOKEN) == "ref-1"
    assert auth._state is None
    assert auth._verifier is None
    assert auth.authorization_status() == {"pending": False, "result": "ok"}


def test_callback_rejects_state_mismatch_error_and_missing_code():
    auth, _, _ = make_auth()
    auth.begin_authorization()
    assert auth.handle_callback({"code": "c", "state": "WRONG"}) == {
        "ok": False,
        "error": "state_mismatch",
    }
    assert auth.handle_callback({"error": "access_denied"}) == {
        "ok": False,
        "error": "state_mismatch",
    }
    auth.begin_authorization()
    assert auth.handle_callback(
        {"error": "access_denied", "state": auth._state}
    ) == {"ok": False, "error": "access_denied"}
    assert auth._state is None
    assert auth._verifier is None
    auth.begin_authorization()
    assert auth.handle_callback({"state": auth._state}) == {
        "ok": False,
        "error": "missing_code",
    }
    assert auth.authorization_status() == {"pending": False, "result": "error"}


def test_authorization_state_expires_with_the_ui_poll_window():
    now = [100.0]
    auth, _, _ = make_auth(clock=lambda: now[0])
    auth.begin_authorization()
    state = auth._state
    assert auth.authorization_status() == {"pending": True, "result": None}

    now[0] += spotify.AUTHORIZATION_TIMEOUT_SECONDS

    assert auth.handle_callback({"code": "late", "state": state}) == {
        "ok": False,
        "error": "state_expired",
    }
    assert auth.authorization_status() == {"pending": False, "result": "expired"}
    assert auth._state is None
    assert auth._verifier is None


def test_disconnect_clears_tokens_and_pending_pkce_state():
    secrets = FakeSecrets()
    secrets.set(spotify.ACCESS_TOKEN, "access")
    secrets.set(spotify.REFRESH_TOKEN, "refresh")
    auth, _, _ = make_auth(secrets=secrets)
    auth.begin_authorization()

    auth.disconnect()
    auth.disconnect()  # idempotent

    assert auth.connected() is False
    assert secrets.get(spotify.ACCESS_TOKEN) is None
    assert secrets.get(spotify.REFRESH_TOKEN) is None
    assert auth._state is None
    assert auth._verifier is None
    assert auth.authorization_status() == {"pending": False, "result": None}


def test_no_client_secret_anywhere_in_module():
    assert "client_secret" not in Path(spotify.__file__).read_text().replace(
        '"client_secret" not in body', ""
    )


# --- refresh -----------------------------------------------------------------


def test_refresh_preserves_absent_refresh_token():
    secrets = FakeSecrets()
    secrets.set(spotify.REFRESH_TOKEN, "ref-original")
    auth, transport, secrets = make_auth(
        token_response(access="acc-2", refresh=None), secrets=secrets
    )
    auth.refresh()
    assert secrets.get(spotify.ACCESS_TOKEN) == "acc-2"
    assert secrets.get(spotify.REFRESH_TOKEN) == "ref-original"  # preserved (5.9)
    body = dict(urllib.parse.parse_qsl(transport.calls[0]["data"].decode()))
    assert body["grant_type"] == "refresh_token"


def test_refresh_overwrites_when_rotated():
    secrets = FakeSecrets()
    secrets.set(spotify.REFRESH_TOKEN, "ref-old")
    auth, _, secrets = make_auth(
        token_response(access="acc-3", refresh="ref-new"), secrets=secrets
    )
    auth.refresh()
    assert secrets.get(spotify.REFRESH_TOKEN) == "ref-new"


def test_refresh_without_stored_token_raises():
    auth, _, _ = make_auth()
    with pytest.raises(NotConnectedError):
        auth.refresh()


def test_revoked_refresh_token_clears_session_for_reauthorization():
    secrets = FakeSecrets()
    secrets.set(spotify.ACCESS_TOKEN, "expired-access")
    secrets.set(spotify.REFRESH_TOKEN, "revoked-refresh")
    auth, _, secrets = make_auth(
        (400, {}, b'{"error":"invalid_grant"}'), secrets=secrets
    )

    with pytest.raises(NotConnectedError, match="reconnect"):
        auth.refresh()

    assert auth.connected() is False
    assert secrets.get(spotify.ACCESS_TOKEN) is None
    assert secrets.get(spotify.REFRESH_TOKEN) is None


# --- retry ladder (SPEC-01 2.5) ----------------------------------------------


def api_ok(payload=None):
    return (200, {}, json.dumps(payload or {"items": []}).encode())


def make_client(*responses):
    secrets = FakeSecrets()
    secrets.set(spotify.ACCESS_TOKEN, "acc")
    secrets.set(spotify.REFRESH_TOKEN, "ref")
    transport = FakeTransport(*responses)
    auth = SpotifyAuth(lambda: "client-123", secrets, transport=transport)
    sleeps = []
    client = SpotifyClient(auth, transport=transport, sleep=sleeps.append)
    return client, transport, sleeps


def test_get_success_sends_bearer():
    client, transport, _ = make_client(api_ok({"name": "playlist"}))
    assert client.get("/playlists/xyz") == {"name": "playlist"}
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer acc"
    assert transport.calls[0]["url"].startswith("https://api.spotify.com/v1")


def test_401_forces_exactly_one_refresh_then_succeeds():
    client, transport, _ = make_client(
        (401, {}, b""),        # api call, attempt 0
        token_response("acc-fresh"),  # the forced refresh
        api_ok({"ok": 1}),     # retried api call
    )
    assert client.get("/me/playlists") == {"ok": 1}
    assert transport.calls[1]["url"] == spotify.TOKEN_URL
    assert transport.calls[2]["headers"]["Authorization"] == "Bearer acc-fresh"


def test_401_after_refresh_raises_not_loops():
    client, transport, _ = make_client(
        (401, {}, b""),
        token_response("acc-fresh"),
        (401, {}, b""),
    )
    with pytest.raises(SpotifyApiError) as info:
        client.get("/me/playlists")
    assert info.value.status_code == 401
    # exactly one token call: no refresh loop
    token_calls = [c for c in transport.calls if c["url"] == spotify.TOKEN_URL]
    assert len(token_calls) == 1


def test_429_sleeps_retry_after_plus_attempt():
    client, _, sleeps = make_client(
        (429, {"Retry-After": "3"}, b""),
        (429, {"Retry-After": "3"}, b""),
        api_ok(),
    )
    assert client.get("/x") == {"items": []}
    assert sleeps == [3, 4]  # Retry-After + attempt index


def test_429_exhausts_after_four_attempts():
    client, transport, sleeps = make_client(*[(429, {"Retry-After": "1"}, b"")] * 4)
    with pytest.raises(SpotifyApiError) as info:
        client.get("/x")
    assert info.value.status_code == 429
    assert len(transport.calls) == 4
    assert sleeps == [1, 2, 3, 4]


def test_204_returns_empty_dict():
    client, _, _ = make_client((204, {}, b""))
    assert client.get("/x") == {}


def test_404_carries_actionable_message():
    client, _, _ = make_client((404, {}, b""))
    with pytest.raises(SpotifyApiError) as info:
        client.get("/playlists/private")
    assert info.value.status_code == 404
    assert "Connect your Spotify account" in str(info.value)


def test_404_editorial_playlist_names_the_real_cause():
    client, _, _ = make_client((404, {}, b""))
    with pytest.raises(SpotifyApiError) as info:
        client.get("/playlists/37i9dQZF1DWWo4kzWesMJm")
    assert info.value.status_code == 404
    assert "editorial" in str(info.value)


def test_500_preserves_status_code():
    client, _, _ = make_client((500, {}, b""))
    with pytest.raises(SpotifyApiError) as info:
        client.get("/x")
    assert info.value.status_code == 500
