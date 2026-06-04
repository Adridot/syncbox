from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .db import LocalDatabase
from .models import SpotifyTrack


# Serialises Client-Credentials token fetches across concurrent requests so a
# burst doesn't trigger several token requests at once.
_token_lock = asyncio.Lock()

# Serialises *user* token refreshes. With a public PKCE client Spotify rotates the
# refresh token on every refresh, so simultaneous refreshes would invalidate each
# other and force a re-login. The lock (plus the inside-lock freshness re-check)
# guarantees a single refresh wins. (With a client secret the refresh token is
# stable, but the lock is still correct and cheap.)
_refresh_lock = asyncio.Lock()

SPOTIFY_ACCOUNTS_URL = "https://accounts.spotify.com"
SPOTIFY_API_URL = "https://api.spotify.com/v1"

# Read-only scopes: enough to list the user's own private/collaborative/followed
# playlists. No modify scopes — Syncbox never writes back to Spotify.
SPOTIFY_SCOPES = [
    "playlist-read-private",
    "playlist-read-collaborative",
]


class SpotifyAuthError(RuntimeError):
    """A Spotify request failed. Carries the HTTP status code (when it came from
    a Spotify response) so callers can react — e.g. turn a 404 on a playlist into
    actionable "it may be private, sign in" guidance."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _spotify_error_message(response: "httpx.Response") -> str:
    """Pull Spotify's human error message out of the JSON body when present
    (``{"error": {"message": ...}}``), else fall back to the raw text."""
    try:
        data = response.json()
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])
            if isinstance(error, str) and error:
                return error
    except Exception:
        pass
    return response.text or f"Spotify request failed ({response.status_code})."


class SpotifyClient:
    def __init__(self, database: LocalDatabase) -> None:
        self.database = database

    async def test_connection(self) -> dict[str, Any]:
        """Validate the Client ID/Secret (app token) and the username — backs the
        Settings "Test Connection" button. Raises SpotifyAuthError with a readable
        message on failure."""
        await self._get_app_token(force=True)
        username = self.database.get_setting("spotify_username").strip()
        if not username:
            raise SpotifyAuthError("Spotify username is required.")
        profile = await self._request(
            "GET", f"/users/{username}", params={}, use_user_token=False
        )
        return {
            "connected": True,
            "mode": "app",
            "username": username,
            "displayName": str(profile.get("display_name") or username),
        }

    # --- Optional user account (Authorization Code + PKCE) --------------------
    # The app token (Client Credentials) only reaches *public* playlists. When the
    # user signs in with their own account, we use their token instead, which
    # reaches private + collaborative + followed playlists.

    def build_authorization_url(self, client_id: str, redirect_uri: str) -> dict[str, str]:
        """Build the Spotify consent URL and persist the PKCE verifier + CSRF state.
        Returns the URL for the renderer to open in the browser."""
        client_id = client_id.strip()
        redirect_uri = redirect_uri.strip()
        if not client_id:
            raise SpotifyAuthError("Spotify Client ID is required.")
        if not redirect_uri:
            raise SpotifyAuthError("Spotify redirect URI is required.")

        verifier = create_code_verifier()
        state = secrets.token_urlsafe(32)
        challenge = create_code_challenge(verifier)

        self.database.set_setting("spotify_client_id", client_id)
        self.database.set_setting("spotify_redirect_uri", redirect_uri)
        self.database.set_setting("spotify_pkce_verifier", verifier)
        self.database.set_setting("spotify_oauth_state", state)

        query = urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "scope": " ".join(SPOTIFY_SCOPES),
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge_method": "S256",
                "code_challenge": challenge,
            }
        )
        return {
            "authorizationUrl": f"{SPOTIFY_ACCOUNTS_URL}/authorize?{query}",
            "state": state,
            "redirectUri": redirect_uri,
        }

    async def exchange_callback(self, code: str, state: str) -> None:
        """Complete the OAuth handshake: validate state, swap the code for tokens,
        store them, and record the signed-in user's identity."""
        expected_state = self.database.get_setting("spotify_oauth_state")
        if not expected_state or state != expected_state:
            raise SpotifyAuthError("Spotify OAuth state mismatch.")

        client_id = self.database.get_setting("spotify_client_id")
        redirect_uri = self.database.get_setting("spotify_redirect_uri")
        verifier = self.database.get_setting("spotify_pkce_verifier")
        if not all([client_id, redirect_uri, verifier]):
            raise SpotifyAuthError("Spotify OAuth session is incomplete.")

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"{SPOTIFY_ACCOUNTS_URL}/api/token",
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "client_id": client_id,
                        "code_verifier": verifier,
                    },
                    headers=self._token_headers(client_id),
                )
        except httpx.HTTPError as exc:
            # Network/SSL failure reaching Spotify — surface a readable message
            # instead of a bare 500 (e.g. missing CA bundle in a frozen build).
            raise SpotifyAuthError(
                f"Could not reach Spotify to complete sign-in: {exc}"
            ) from exc
        if response.status_code >= 400:
            raise SpotifyAuthError(response.text)

        self._store_user_tokens(response.json())
        # One-shot handshake values are spent — clear them.
        self.database.set_setting("spotify_oauth_state", "")
        self.database.set_setting("spotify_pkce_verifier", "")

        # Record who just signed in (for the "Connected as …" badge).
        try:
            profile = await self._request("GET", "/me", params={}, use_user_token=True)
            self.database.set_setting("spotify_user_id", str(profile.get("id") or ""))
            self.database.set_setting(
                "spotify_user_display_name",
                str(profile.get("display_name") or profile.get("id") or ""),
            )
        except SpotifyAuthError:
            # Tokens are stored; identity is cosmetic — don't fail the sign-in.
            pass

    def is_account_connected(self) -> bool:
        return bool(self.database.get_setting("spotify_user_refresh_token").strip())

    def disconnect_account(self) -> None:
        for key in (
            "spotify_user_access_token",
            "spotify_user_refresh_token",
            "spotify_user_expires_at",
            "spotify_user_id",
            "spotify_user_display_name",
        ):
            self.database.set_setting(key, "")

    def connection_status(self, redirect_uri: str = "") -> dict[str, Any]:
        """Report the current Spotify auth state for the Settings badge."""
        if self.is_account_connected():
            display = self.database.get_setting("spotify_user_display_name").strip()
            user_id = self.database.get_setting("spotify_user_id").strip()
            return {
                "connected": True,
                "mode": "oauth",
                "username": user_id,
                "displayName": display or user_id,
                "redirectUri": redirect_uri,
            }
        username = self.database.get_setting("spotify_username").strip()
        client_id = self.database.get_setting("spotify_client_id").strip()
        return {
            "connected": bool(client_id and username),
            "mode": "app" if (client_id and username) else "",
            "username": username,
            "displayName": username,
            "redirectUri": redirect_uri,
        }

    def _translate_playlist_error(self, exc: SpotifyAuthError) -> SpotifyAuthError:
        """Spotify returns 404 (not 403) for a playlist the current token can't
        see — including any *private* playlist when no user account is connected.
        It never says "private" explicitly, so infer it: a 404 while signed out is
        almost always a private playlist, and the fix is to connect the account."""
        if exc.status_code != 404:
            return exc
        if not self.is_account_connected():
            return SpotifyAuthError(
                "Playlist not found. If it's private, connect your Spotify "
                "account in Settings — private playlists are only visible once "
                "you're signed in.",
                status_code=404,
            )
        return SpotifyAuthError(
            "Spotify playlist not found. If it's your own private playlist, try "
            "reconnecting your Spotify account in Settings; otherwise check the "
            "link — it may be private (someone else's) or deleted.",
            status_code=404,
        )

    async def get_playlist(self, playlist_id: str) -> dict[str, Any]:
        try:
            return await self._request(
                "GET",
                f"/playlists/{playlist_id}",
                params={
                    "fields": (
                        "id,name,snapshot_id,public,images,"
                        "items.total,tracks.total,external_urls,owner(display_name,id)"
                    )
                },
            )
        except SpotifyAuthError as exc:
            raise self._translate_playlist_error(exc) from exc

    async def get_playlist_items(self, playlist_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        limit = 50
        while True:
            try:
                payload = await self._request(
                    "GET",
                    f"/playlists/{playlist_id}/items",
                    params={
                        "limit": limit,
                        "offset": offset,
                        "additional_types": "track",
                        "fields": (
                            "items(added_at,track(id,uri,name,artists(name),duration_ms,"
                            "external_ids,is_local,type)),total,next,limit,offset"
                        ),
                    },
                )
            except SpotifyAuthError as exc:
                raise self._translate_playlist_error(exc) from exc
            page_items = payload.get("items", [])
            items.extend(page_items)
            if not payload.get("next") or not page_items:
                break
            offset += limit
        return items

    async def get_current_user_playlists(
        self, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        """List playlists for "Manage sources".

        When a user account is connected, use their token and ``/me/playlists``
        (private + collaborative + followed). Otherwise fall back to the app token
        and ``/users/{username}/playlists`` (public only, no browser sign-in)."""
        limit = max(1, min(limit, 50))
        offset = max(0, offset)
        if self.is_account_connected():
            return await self._request(
                "GET",
                "/me/playlists",
                params={"limit": limit, "offset": offset},
                use_user_token=True,
            )
        username = self.database.get_setting("spotify_username").strip()
        if not username:
            raise SpotifyAuthError("Set your Spotify username in Settings.")
        return await self._request(
            "GET",
            f"/users/{username}/playlists",
            params={"limit": limit, "offset": offset},
            use_user_token=False,
        )

    async def get_track(self, track_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/tracks/{track_id}", params={})

    async def search_track(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            "/search",
            params={"q": query, "type": "track", "limit": max(1, min(limit, 50))},
        )
        return payload.get("tracks", {}).get("items", []) or []

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        use_user_token: bool | None = None,
    ) -> dict[str, Any]:
        # use_user_token: True forces the signed-in user's token, False forces the
        # app token. None auto-selects — the user's token when an account is
        # connected, else the app token (both reach public catalog data).
        prefer_user = (
            self.is_account_connected() if use_user_token is None else use_user_token
        )

        async def _token(force: bool) -> str:
            return (
                await self._get_user_token(force=force)
                if prefer_user
                else await self._get_app_token(force=force)
            )

        token = await _token(force=False)
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=30) as client:
            for attempt in range(4):
                try:
                    response = await client.request(
                        method,
                        f"{SPOTIFY_API_URL}{path}",
                        params=params,
                        json=json,
                        headers=headers,
                    )
                except httpx.HTTPError as exc:
                    raise SpotifyAuthError(f"Could not reach Spotify: {exc}") from exc
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "1"))
                    await sleep_seconds(retry_after + attempt)
                    continue
                if response.status_code == 401 and attempt == 0:
                    token = await _token(force=True)
                    headers = {"Authorization": f"Bearer {token}"}
                    continue
                if response.status_code >= 400:
                    raise SpotifyAuthError(
                        _spotify_error_message(response),
                        status_code=response.status_code,
                    )
                if response.status_code == 204:
                    return {}
                return response.json()
        raise SpotifyAuthError("Spotify request failed after retries.")

    async def _get_app_token(self, *, force: bool = False) -> str:
        """Client-Credentials app token (client_id + client_secret, no browser).
        Cached in settings and refreshed automatically when it expires."""

        def _cached() -> str | None:
            token = self.database.get_setting("spotify_app_token")
            expires_at = int(
                self.database.get_setting("spotify_app_token_expires_at", "0") or "0"
            )
            if token and expires_at > int(time.time()) + 60:
                return token
            return None

        if not force:
            token = _cached()
            if token:
                return token

        async with _token_lock:
            # A concurrent caller may have refreshed while we waited on the lock.
            if not force:
                token = _cached()
                if token:
                    return token

            client_id = self.database.get_setting("spotify_client_id").strip()
            client_secret = self.database.get_setting("spotify_client_secret").strip()
            if not client_id or not client_secret:
                raise SpotifyAuthError(
                    "Spotify Client ID and Client Secret are required (Settings)."
                )
            basic = base64.b64encode(
                f"{client_id}:{client_secret}".encode("utf-8")
            ).decode("ascii")
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(
                        f"{SPOTIFY_ACCOUNTS_URL}/api/token",
                        data={"grant_type": "client_credentials"},
                        headers={
                            "Authorization": f"Basic {basic}",
                            "Content-Type": "application/x-www-form-urlencoded",
                        },
                    )
            except httpx.HTTPError as exc:
                raise SpotifyAuthError(f"Could not reach Spotify: {exc}") from exc
            if response.status_code >= 400:
                raise SpotifyAuthError(
                    f"Spotify rejected the Client ID/Secret: {response.text}"
                )
            payload = response.json()
            token = str(payload["access_token"])
            self.database.set_setting("spotify_app_token", token)
            self.database.set_setting(
                "spotify_app_token_expires_at",
                str(int(time.time()) + int(payload.get("expires_in", 3600))),
            )
            return token

    async def _get_user_token(self, *, force: bool = False) -> str:
        """The signed-in user's access token, refreshed via the stored refresh
        token when stale. Mirrors the app-token cache pattern, but uses the
        ``spotify_user_*`` keys and the OAuth refresh grant."""
        access_token = self.database.get_setting("spotify_user_access_token")
        expires_at = int(
            self.database.get_setting("spotify_user_expires_at", "0") or "0"
        )
        if not access_token and not self.database.get_setting(
            "spotify_user_refresh_token"
        ):
            raise SpotifyAuthError("Spotify account is not connected.")
        if not force and access_token and expires_at > int(time.time()) + 60:
            return access_token
        return await self._refresh_user_token(force=force)

    async def _refresh_user_token(self, *, force: bool = False) -> str:
        async with _refresh_lock:
            # A concurrent caller may have refreshed while we waited on the lock —
            # reuse that token instead of refreshing again (which, on a public PKCE
            # client, would invalidate the just-issued refresh token).
            if not force:
                access_token = self.database.get_setting("spotify_user_access_token")
                expires_at = int(
                    self.database.get_setting("spotify_user_expires_at", "0") or "0"
                )
                if access_token and expires_at > int(time.time()) + 60:
                    return access_token

            refresh_token = self.database.get_setting("spotify_user_refresh_token")
            client_id = self.database.get_setting("spotify_client_id")
            if not refresh_token or not client_id:
                raise SpotifyAuthError("Spotify account is not connected.")

            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(
                        f"{SPOTIFY_ACCOUNTS_URL}/api/token",
                        data={
                            "grant_type": "refresh_token",
                            "refresh_token": refresh_token,
                            "client_id": client_id,
                        },
                        headers=self._token_headers(client_id),
                    )
            except httpx.HTTPError as exc:
                raise SpotifyAuthError(f"Could not reach Spotify: {exc}") from exc
            if response.status_code >= 400:
                raise SpotifyAuthError(response.text)
            payload = response.json()
            self._store_user_tokens(payload, keep_refresh=True)
            return str(payload["access_token"])

    def _token_headers(self, client_id: str) -> dict[str, str]:
        """Headers for a token-endpoint call. When a client secret is configured we
        authenticate as a *confidential* client (HTTP Basic), which makes Spotify
        issue a stable, non-rotating refresh token — so the user signs in once and
        Syncbox refreshes silently forever. Without a secret we stay on the public
        PKCE flow (client_id only, rotating refresh token)."""
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        client_secret = self.database.get_setting("spotify_client_secret")
        if client_secret:
            basic = base64.b64encode(
                f"{client_id}:{client_secret}".encode("utf-8")
            ).decode("ascii")
            headers["Authorization"] = f"Basic {basic}"
        return headers

    def _store_user_tokens(
        self, payload: dict[str, Any], keep_refresh: bool = False
    ) -> None:
        self.database.set_setting(
            "spotify_user_access_token", str(payload["access_token"])
        )
        # On refresh, Spotify may omit refresh_token (stable confidential client) —
        # keep the existing one in that case rather than blanking it.
        if payload.get("refresh_token") or not keep_refresh:
            self.database.set_setting(
                "spotify_user_refresh_token", str(payload.get("refresh_token", ""))
            )
        expires_at = int(time.time()) + int(payload.get("expires_in", 3600))
        self.database.set_setting("spotify_user_expires_at", str(expires_at))


def create_code_verifier() -> str:
    return secrets.token_urlsafe(64)[:128]


def create_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _parse_spotify_id(value: str, kind: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme.startswith("http") and parsed.netloc:
        parts = [part for part in parsed.path.split("/") if part]
        if kind in parts:
            index = parts.index(kind)
            if len(parts) > index + 1:
                # Strip any trailing query/fragment captured in the path segment.
                return parts[index + 1].split("?")[0]
        query = parse_qs(parsed.query)
        if kind in query:
            return query[kind][0]
    if value.startswith(f"spotify:{kind}:"):
        return value.split(":")[-1]
    return value.strip()


def parse_playlist_id(value: str) -> str:
    return _parse_spotify_id(value, "playlist")


def parse_track_id(value: str) -> str:
    return _parse_spotify_id(value, "track")


def summarize_playlist_page(payload: dict[str, Any]) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    for playlist in payload.get("items", []):
        if not playlist:
            continue
        owner = playlist.get("owner") or {}
        item_collection = playlist.get("items") or {}
        legacy_tracks = playlist.get("tracks") or {}
        external_urls = playlist.get("external_urls") or {}
        images = playlist.get("images") or []
        playlist_id = str(playlist.get("id", ""))
        summaries.append(
            {
                "id": playlist_id,
                "name": str(playlist.get("name") or "Untitled playlist"),
                "owner": str(owner.get("display_name") or owner.get("id") or "Unknown"),
                "trackCount": int(
                    item_collection.get("total")
                    if item_collection.get("total") is not None
                    else legacy_tracks.get("total") or 0
                ),
                "public": playlist.get("public"),
                "snapshotId": playlist.get("snapshot_id"),
                "imageUrl": playlist_image_url(images),
                "url": str(
                    external_urls.get("spotify")
                    or f"https://open.spotify.com/playlist/{playlist_id}"
                ),
            }
        )

    limit = int(payload.get("limit") or 50)
    offset = int(payload.get("offset") or 0)
    next_offset = offset + limit if payload.get("next") else None
    return {
        "items": summaries,
        "total": int(payload.get("total") or len(summaries)),
        "limit": limit,
        "offset": offset,
        "nextOffset": next_offset,
    }


def playlist_image_url(images: object) -> str | None:
    if not isinstance(images, list):
        return None
    for image in images:
        if not isinstance(image, dict):
            continue
        url = image.get("url")
        if url:
            return str(url)
    return None


def track_payload_to_spotify_track(track: dict[str, Any]) -> SpotifyTrack | None:
    """Convert a raw Spotify track object into a SpotifyTrack, or None if it is
    not a usable full track (local files, episodes, missing id/uri)."""
    if not isinstance(track, dict):
        return None
    if track.get("type") not in (None, "track") or track.get("is_local"):
        return None
    track_id = track.get("id")
    uri = track.get("uri")
    if not track_id or not uri:
        return None
    external_ids = track.get("external_ids") or {}
    return SpotifyTrack(
        id=str(track_id),
        uri=str(uri),
        title=str(track.get("name") or "Untitled track"),
        artists=[
            str(artist.get("name"))
            for artist in track.get("artists", [])
            if artist.get("name")
        ],
        durationMs=int(track.get("duration_ms") or 0),
        isrc=external_ids.get("isrc"),
    )


def playlist_items_to_tracks(items: list[dict[str, Any]]) -> list[SpotifyTrack]:
    tracks: list[SpotifyTrack] = []
    for item in items:
        track = track_payload_to_spotify_track(item.get("track") or {})
        if track is not None:
            tracks.append(track)
    return tracks


async def sleep_seconds(seconds: int) -> None:
    import asyncio

    await asyncio.sleep(seconds)
