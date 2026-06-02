from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .db import LocalDatabase
from .models import SpotifyTrack


SPOTIFY_ACCOUNTS_URL = "https://accounts.spotify.com"
SPOTIFY_API_URL = "https://api.spotify.com/v1"
SPOTIFY_SCOPES = [
    "playlist-read-private",
    "playlist-modify-private",
    "playlist-modify-public",
    "user-library-read",
    "user-library-modify",
]


class SpotifyAuthError(RuntimeError):
    pass


class SpotifyClient:
    def __init__(self, database: LocalDatabase) -> None:
        self.database = database

    def build_authorization_url(self, client_id: str, redirect_uri: str) -> dict[str, str]:
        if not client_id.strip():
            raise SpotifyAuthError("Spotify Client ID is required.")

        verifier = create_code_verifier()
        state = secrets.token_urlsafe(32)
        challenge = create_code_challenge(verifier)

        self.database.set_setting("spotify_client_id", client_id.strip())
        self.database.set_setting("spotify_redirect_uri", redirect_uri.strip())
        self.database.set_setting("spotify_pkce_verifier", verifier)
        self.database.set_setting("spotify_oauth_state", state)

        query = urlencode(
            {
                "response_type": "code",
                "client_id": client_id.strip(),
                "scope": " ".join(SPOTIFY_SCOPES),
                "redirect_uri": redirect_uri.strip(),
                "state": state,
                "code_challenge_method": "S256",
                "code_challenge": challenge,
            }
        )
        return {
            "authorizationUrl": f"{SPOTIFY_ACCOUNTS_URL}/authorize?{query}",
            "state": state,
        }

    async def exchange_callback(self, code: str, state: str) -> None:
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
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.HTTPError as exc:
            # Network/SSL failure reaching Spotify — surface a readable message
            # instead of a bare 500 (e.g. missing CA bundle in a frozen build).
            raise SpotifyAuthError(
                f"Could not reach Spotify to complete sign-in: {exc}"
            ) from exc
        if response.status_code >= 400:
            raise SpotifyAuthError(response.text)

        payload = response.json()
        self._store_tokens(payload)

    async def get_playlist(self, playlist_id: str) -> dict[str, Any]:
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

    async def get_playlist_items(self, playlist_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        limit = 50
        while True:
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
            page_items = payload.get("items", [])
            items.extend(page_items)
            if not payload.get("next") or not page_items:
                break
            offset += limit
        return items

    async def get_current_user_playlists(
        self, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        limit = max(1, min(limit, 50))
        offset = max(0, offset)
        return await self._request(
            "GET",
            "/me/playlists",
            params={"limit": limit, "offset": offset},
        )

    async def get_current_user_id(self) -> str:
        payload = await self._request("GET", "/me", params={})
        user_id = payload.get("id")
        if not user_id:
            raise SpotifyAuthError("Could not resolve the current Spotify user.")
        return str(user_id)

    async def get_track(self, track_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/tracks/{track_id}", params={})

    async def search_track(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            "/search",
            params={"q": query, "type": "track", "limit": max(1, min(limit, 50))},
        )
        return payload.get("tracks", {}).get("items", []) or []

    async def create_playlist(
        self, name: str, *, public: bool = False, description: str = ""
    ) -> dict[str, Any]:
        user_id = await self.get_current_user_id()
        payload = await self._request(
            "POST",
            f"/users/{user_id}/playlists",
            json={"name": name, "public": public, "description": description},
        )
        external_urls = payload.get("external_urls") or {}
        return {
            "id": str(payload.get("id", "")),
            "name": str(payload.get("name", name)),
            "url": str(
                external_urls.get("spotify")
                or f"https://open.spotify.com/playlist/{payload.get('id', '')}"
            ),
        }

    async def add_tracks_to_playlist(self, playlist_id: str, uris: list[str]) -> None:
        for start in range(0, len(uris), 100):
            await self._request(
                "POST",
                f"/playlists/{playlist_id}/items",
                json={"uris": uris[start : start + 100]},
            )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        access_token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {access_token}"}

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
                    access_token = await self._refresh_access_token()
                    headers = {"Authorization": f"Bearer {access_token}"}
                    continue
                if response.status_code >= 400:
                    raise SpotifyAuthError(response.text)
                if response.status_code == 204:
                    return {}
                return response.json()
        raise SpotifyAuthError("Spotify request failed after retries.")

    async def _get_access_token(self) -> str:
        access_token = self.database.get_setting("spotify_access_token")
        expires_at = int(self.database.get_setting("spotify_expires_at", "0") or "0")
        if not access_token:
            raise SpotifyAuthError("Spotify is not authenticated.")
        if expires_at <= int(time.time()) + 60:
            return await self._refresh_access_token()
        return access_token

    async def _refresh_access_token(self) -> str:
        refresh_token = self.database.get_setting("spotify_refresh_token")
        client_id = self.database.get_setting("spotify_client_id")
        if not refresh_token or not client_id:
            raise SpotifyAuthError("Spotify refresh token is missing.")

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{SPOTIFY_ACCOUNTS_URL}/api/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if response.status_code >= 400:
            raise SpotifyAuthError(response.text)
        payload = response.json()
        self._store_tokens(payload, keep_refresh=True)
        return str(payload["access_token"])

    def _store_tokens(self, payload: dict[str, Any], keep_refresh: bool = False) -> None:
        self.database.set_setting("spotify_access_token", str(payload["access_token"]))
        if payload.get("refresh_token") or not keep_refresh:
            self.database.set_setting(
                "spotify_refresh_token", str(payload.get("refresh_token", ""))
            )
        expires_at = int(time.time()) + int(payload.get("expires_in", 3600))
        self.database.set_setting("spotify_expires_at", str(expires_at))


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
