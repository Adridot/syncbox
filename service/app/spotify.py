from __future__ import annotations

import asyncio
import base64
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from .db import LocalDatabase
from .models import SpotifyTrack


# Serialises Client-Credentials token fetches across concurrent requests so a
# burst doesn't trigger several token requests at once.
_token_lock = asyncio.Lock()

SPOTIFY_ACCOUNTS_URL = "https://accounts.spotify.com"
SPOTIFY_API_URL = "https://api.spotify.com/v1"


class SpotifyAuthError(RuntimeError):
    pass


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
        profile = await self._request("GET", f"/users/{username}", params={})
        return {
            "connected": True,
            "username": username,
            "displayName": str(profile.get("display_name") or username),
        }

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
        """The user's *public* playlists, fetched by username with an app token —
        no browser sign-in needed."""
        username = self.database.get_setting("spotify_username").strip()
        if not username:
            raise SpotifyAuthError("Set your Spotify username in Settings.")
        limit = max(1, min(limit, 50))
        offset = max(0, offset)
        return await self._request(
            "GET",
            f"/users/{username}/playlists",
            params={"limit": limit, "offset": offset},
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
    ) -> dict[str, Any]:
        token = await self._get_app_token()
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
                    token = await self._get_app_token(force=True)
                    headers = {"Authorization": f"Bearer {token}"}
                    continue
                if response.status_code >= 400:
                    raise SpotifyAuthError(response.text)
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
