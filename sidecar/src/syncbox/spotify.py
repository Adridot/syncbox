"""Spotify auth (OAuth PKCE, read-only) and Web API client
(SPEC-UNIFIED 5.9/6.10, SPEC-01 2.5, research 06 section 2).

Hard rules implemented here:
- Authorization Code + PKCE (S256) ONLY - no client secret exists anywhere
  (D3); scopes are read-only playlist scopes;
- redirect_uri is the hardcoded constant, used verbatim in BOTH the
  authorize and the token calls, NEVER derived from any incoming request
  (the browser may rewrite 127.0.0.1 to localhost; that must not matter);
- token refresh preserves the stored refresh_token when the response omits
  one;
- bounded retry, 4 attempts: 429 sleeps Retry-After + attempt; 401 forces
  ONE refresh and only on the first attempt (otherwise a refresh loop);
  204 yields {}; >= 400 raises with status_code preserved; 404 carries the
  actionable "connect your account" message.

Transport: stdlib urllib over a certifi CA context (3.5) - injectable for
tests; the only outbound network calls in the whole sidecar are here.
"""

import base64
import hashlib
import json
import secrets as pysecrets
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

import certifi

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"
REDIRECT_URI = "http://127.0.0.1:8765/callback"  # exact dashboard match; never derived
SCOPES = "playlist-read-private playlist-read-collaborative"
MAX_ATTEMPTS = 4
AUTHORIZATION_TIMEOUT_SECONDS = 120

ACCESS_TOKEN = "spotify.access_token"
REFRESH_TOKEN = "spotify.refresh_token"


class SpotifyApiError(RuntimeError):
    def __init__(self, status_code: int, message: str, error_code: str | None = None):
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


class NotConnectedError(RuntimeError):
    """No Spotify session: begin_authorization() must run first."""


def _default_transport(url, data=None, headers=None, method="GET"):
    """(status_code, headers dict, body bytes) - never raises on HTTP >= 400."""
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urllib.request.urlopen(request, context=context, timeout=30) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


class SpotifyAuth:
    """PKCE flow state + token storage in the encrypted SecretsStore."""

    def __init__(
        self, client_id_getter, secrets, transport=_default_transport, clock=time.monotonic
    ):
        self._client_id = client_id_getter
        self._secrets = secrets
        self._transport = transport
        self._clock = clock
        self._verifier = None
        self._state = None
        self._deadline = None
        self._authorization_result = None

    def begin_authorization(self) -> str:
        """Return the authorize URL to open in the user's browser."""
        self._verifier = base64.urlsafe_b64encode(pysecrets.token_bytes(64)).rstrip(
            b"="
        ).decode()
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(self._verifier.encode()).digest()
        ).rstrip(b"=").decode()
        self._state = pysecrets.token_urlsafe(16)
        self._deadline = self._clock() + AUTHORIZATION_TIMEOUT_SECONDS
        self._authorization_result = None
        params = {
            "client_id": self._client_id(),
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": self._state,
        }
        return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    def handle_callback(self, params: dict) -> dict:
        """GET /callback handler body: validate state, exchange code."""
        self._expire_pending()
        if self._authorization_result == "expired":
            return {"ok": False, "error": "state_expired"}
        received_state = params.get("state")
        if (
            self._state is None
            or not isinstance(received_state, str)
            or not pysecrets.compare_digest(received_state, self._state)
        ):
            return {"ok": False, "error": "state_mismatch"}
        verifier = self._verifier
        self._state = None
        self._verifier = None
        self._deadline = None
        if "error" in params:
            self._authorization_result = "error"
            return {"ok": False, "error": params["error"]}
        code = params.get("code")
        if not code:
            self._authorization_result = "error"
            return {"ok": False, "error": "missing_code"}
        if verifier is None:
            self._authorization_result = "error"
            return {"ok": False, "error": "missing_verifier"}
        try:
            self._token_request(
                grant_type="authorization_code",
                code=code,
                redirect_uri=REDIRECT_URI,  # hardcoded again: both calls (06 rule)
                code_verifier=verifier,
            )
        except SpotifyApiError as exc:
            self._authorization_result = "error"
            return {"ok": False, "error": f"token_exchange_failed_{exc.status_code}"}
        self._authorization_result = "ok"
        return {"ok": True}

    def authorization_status(self) -> dict:
        """Non-secret status for the UI polling the current PKCE attempt."""
        self._expire_pending()
        return {
            "pending": self._state is not None,
            "result": self._authorization_result,
        }

    def _expire_pending(self) -> None:
        if self._deadline is None or self._clock() < self._deadline:
            return
        self._state = None
        self._verifier = None
        self._deadline = None
        self._authorization_result = "expired"

    def connected(self) -> bool:
        """Token presence only - no network call (feeds GET /api/status, G1)."""
        return self._secrets.get(REFRESH_TOKEN) is not None

    def disconnect(self) -> None:
        """Forget the local Spotify session and any pending PKCE exchange."""
        self._state = None
        self._verifier = None
        self._deadline = None
        self._authorization_result = None
        self._secrets.delete(ACCESS_TOKEN)
        self._secrets.delete(REFRESH_TOKEN)

    def refresh(self) -> None:
        refresh_token = self._secrets.get(REFRESH_TOKEN)
        if not refresh_token:
            raise NotConnectedError("no refresh token stored")
        try:
            self._token_request(grant_type="refresh_token", refresh_token=refresh_token)
        except SpotifyApiError as exc:
            if exc.error_code != "invalid_grant":
                raise
            self._secrets.delete(ACCESS_TOKEN)
            self._secrets.delete(REFRESH_TOKEN)
            raise NotConnectedError(
                "Spotify authorization expired or was revoked; reconnect the account"
            ) from None

    def access_token(self) -> str:
        token = self._secrets.get(ACCESS_TOKEN)
        if not token:
            raise NotConnectedError("no access token stored")
        return token

    def _token_request(self, **fields) -> None:
        fields["client_id"] = self._client_id()
        status, _headers, body = self._transport(
            TOKEN_URL,
            data=urllib.parse.urlencode(fields).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        if status >= 400:
            try:
                error_code = json.loads(body).get("error")
            except (json.JSONDecodeError, AttributeError):
                error_code = None
            raise SpotifyApiError(
                status, f"token endpoint returned {status}", error_code=error_code
            )
        payload = json.loads(body)
        self._secrets.set(ACCESS_TOKEN, payload["access_token"])
        if payload.get("refresh_token"):
            # Absent refresh_token in a refresh response: PRESERVE the stored
            # one (5.9) - only overwrite when Spotify actually rotates it.
            self._secrets.set(REFRESH_TOKEN, payload["refresh_token"])


class SpotifyClient:
    """Read-only Web API calls with the bounded 5.9 retry ladder."""

    def __init__(self, auth: SpotifyAuth, transport=_default_transport, sleep=time.sleep):
        self._auth = auth
        self._transport = transport
        self._sleep = sleep

    def get(self, path: str) -> dict:
        url = path if path.startswith("http") else f"{API_BASE}{path}"
        for attempt in range(MAX_ATTEMPTS):
            status, headers, body = self._transport(
                url,
                headers={"Authorization": f"Bearer {self._auth.access_token()}"},
            )
            if status == 401:
                # Force ONE refresh, only on the first attempt; a 401 later in
                # the ladder means refresh did not help - never loop refreshes.
                if attempt == 0:
                    self._auth.refresh()
                    continue
                raise SpotifyApiError(401, "unauthorized after refresh")
            if status == 429:
                retry_after = int(headers.get("Retry-After", 1))
                self._sleep(retry_after + attempt)
                continue
            if status == 204:
                return {}
            if status == 404:
                # ponytail: prefix sniff — Spotify's Web API 404s all
                # editorial/algorithmic playlists (37i9dQZF*) since Nov 2024;
                # connecting an account does not help, say so.
                if "/playlists/37i9dQZF" in url:
                    raise SpotifyApiError(
                        404,
                        "This is a Spotify-owned editorial playlist; the "
                        "Spotify API no longer exposes these (since Nov 2024).",
                    )
                raise SpotifyApiError(
                    404,
                    "Playlist not found or private. Connect your Spotify "
                    "account to access your private playlists.",
                )
            if status >= 400:
                raise SpotifyApiError(status, f"Spotify API error {status}")
            return json.loads(body)
        raise SpotifyApiError(429, "rate limited after retries")
