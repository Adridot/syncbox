import asyncio
from pathlib import Path
from typing import Any

from app.acquisition import DeezerResolveResult, DeezerTrackCandidate
from app.db import LocalDatabase
from app.library import (
    download_library_tracks,
    refresh_library_review_state,
    sync_library_source,
)
from app.models import DeemixStatus, LibrarySourceIn, TagRuleIn
from app.rekordbox import RekordboxAdapter


def test_tag_rules_migrate_to_library_sources(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    database.upsert_tag_rule(
        TagRuleIn(
            sourcePlaylistId="spotify-playlist",
            sourcePlaylistName="Techno",
            tags=["Techno"],
            enabled=True,
        )
    )

    database.migrate()
    sources = database.list_library_sources()

    assert len(sources) == 1
    assert sources[0].spotify_playlist_id == "spotify-playlist"
    assert sources[0].tags == ["Techno"]


def test_library_sync_uses_snapshot_and_marks_removed_tracks(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    source = database.upsert_library_source(
        LibrarySourceIn(
            spotifyPlaylistId="playlist",
            spotifyPlaylistName="Permanent",
            tags=["Peak Time"],
            trackCount=0,
            enabled=True,
        )
    )
    first_client = FakeSpotifyClient(
        snapshot_id="snapshot-1",
        items=[spotify_item("sp-1", "Known Song", "Artist", "ISRC-1")],
    )

    first_review = asyncio.run(
        sync_library_source(
            database,
            FakeRekordboxAdapter(tmp_path),
            first_client,
            source.id,
        )
    )
    assert first_review.matched_tracks == 1
    assert first_review.source.spotify_snapshot_id == "snapshot-1"

    second_client = FakeSpotifyClient(snapshot_id="snapshot-2", items=[])
    second_review = asyncio.run(
        sync_library_source(
            database,
            FakeRekordboxAdapter(tmp_path),
            second_client,
            source.id,
        )
    )
    proposals = database.list_proposals()

    assert second_review.removed_tracks == 1
    assert second_review.source.spotify_snapshot_id == "snapshot-2"
    assert proposals[0].proposal_type == "remove_from_rekordbox"
    assert proposals[0].payload["sourceId"] == source.id


def test_library_sync_detects_imported_track_deleted_from_rekordbox(
    tmp_path: Path,
) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    source = database.upsert_library_source(
        LibrarySourceIn(
            spotifyPlaylistId="playlist",
            spotifyPlaylistName="Permanent",
            tags=["Peak Time"],
            trackCount=0,
            enabled=True,
        )
    )
    client = FakeSpotifyClient(
        snapshot_id="snapshot-1",
        items=[spotify_item("sp-1", "Known Song", "Artist", "ISRC-1")],
    )
    first_review = asyncio.run(
        sync_library_source(
            database,
            FakeRekordboxAdapter(tmp_path),
            client,
            source.id,
        )
    )
    database.mark_library_tracks_imported(source.id, ["sp-1"])
    assert first_review.matched_tracks == 1

    second_review = asyncio.run(
        sync_library_source(
            database,
            FakeRekordboxAdapter(tmp_path, tracks=[]),
            client,
            source.id,
        )
    )

    assert second_review.missing_tracks == 1
    assert second_review.tracks[0].status == "missing"
    assert second_review.tracks[0].rekordbox_content_id is None
    assert (
        second_review.tracks[0].reason
        == "Previously imported track is missing from the Rekordbox collection."
    )


def test_library_download_is_manual_and_compacts_payload(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    source = database.upsert_library_source(
        LibrarySourceIn(
            spotifyPlaylistId="playlist",
            spotifyPlaylistName="Permanent",
            tags=["Peak Time"],
            trackCount=1,
            enabled=True,
        )
    )
    database.upsert_library_tracks(
        source.id,
        [
            {
                "spotify_track_id": "sp-1",
                "spotify_uri": "spotify:track:sp-1",
                "title": "New Song",
                "artists": ["Artist"],
                "duration_ms": 180000,
                "isrc": "ISRC-1",
                "status": "new",
                "tags": ["Peak Time"],
                "reason": "New Spotify track needs download or manual matching.",
            }
        ],
    )

    response = asyncio.run(
        download_library_tracks(
            database,
            RekordboxAdapter(tmp_path / "rekordbox", tmp_path / "storage"),
            request=type(
                "DownloadRequest",
                (),
                {"source_id": source.id, "spotify_track_ids": ["sp-1"]},
            )(),
            deemix_client=FakeDeemixClient(),
            deezer_resolver=FakeResolver(),
        )
    )

    job = response["jobs"][0]
    assert response["queued"] == 1
    assert job.status == "queued"
    assert job.payload["id"] == "dz-1"
    assert "track_token" not in job.payload
    assert "available_countries" not in job.payload


def test_library_review_reconciles_completed_deemix_files(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    source = create_new_library_source(database)
    adapter = RekordboxAdapter(tmp_path / "rekordbox", tmp_path / "storage")
    file_path = Path(adapter.storage_layout().permanent) / "Artist - New Song.mp3"
    database.upsert_library_acquisition_job(
        source.id,
        {
            "spotify_track_id": "sp-1",
            "provider": "deemix",
            "deezer_track_id": "dz-1",
            "status": "downloading",
            "confidence": 100,
            "match_method": "isrc",
            "download_id": "download-1",
            "output_dir": adapter.storage_layout().permanent,
            "payload": {},
        },
    )
    monkeypatch.setattr(
        "app.library.scan_audio_files",
        lambda _path: [
            {
                "file_path": str(file_path),
                "title": "New Song",
                "artist": "Artist",
                "duration_ms": 180000,
                "isrc": "ISRC-1",
                "status": "unmatched",
            }
        ],
    )

    review = asyncio.run(
        refresh_library_review_state(
            database,
            adapter,
            source.id,
            deemix_client=FakeCompletedDeemixClient(),
        )
    )
    job = database.get_library_acquisition_job(source.id, "sp-1")

    assert review.ready_tracks == 1
    assert review.tracks[0].status == "ready"
    assert review.tracks[0].staging_file_path == str(file_path)
    assert job is not None
    assert job.status == "ready"


def test_library_download_does_not_requeue_active_completed_job(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    source = create_new_library_source(database)
    adapter = RekordboxAdapter(tmp_path / "rekordbox", tmp_path / "storage")
    file_path = Path(adapter.storage_layout().permanent) / "Artist - New Song.mp3"
    database.upsert_library_acquisition_job(
        source.id,
        {
            "spotify_track_id": "sp-1",
            "provider": "deemix",
            "deezer_track_id": "dz-1",
            "status": "queued",
            "confidence": 100,
            "match_method": "isrc",
            "download_id": "download-1",
            "output_dir": adapter.storage_layout().permanent,
            "payload": {},
        },
    )
    monkeypatch.setattr(
        "app.library.scan_audio_files",
        lambda _path: [
            {
                "file_path": str(file_path),
                "title": "New Song",
                "artist": "Artist",
                "duration_ms": 180000,
                "isrc": "ISRC-1",
                "status": "unmatched",
            }
        ],
    )

    response = asyncio.run(
        download_library_tracks(
            database,
            adapter,
            request=type(
                "DownloadRequest",
                (),
                {"source_id": source.id, "spotify_track_ids": ["sp-1"]},
            )(),
            deemix_client=FakeCompletedDeemixClient(),
            deezer_resolver=FakeResolver(),
        )
    )

    assert response["created"] == 0
    assert response["queued"] == 0
    assert response["ready"] == 1
    assert response["review"].ready_tracks == 1


def test_library_refresh_keeps_ready_job_status_consistent(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    source = create_new_library_source(database)
    adapter = RekordboxAdapter(tmp_path / "rekordbox", tmp_path / "storage")
    file_path = Path(adapter.storage_layout().permanent) / "Artist - New Song.mp3"
    database.update_library_track(
        source.id,
        "sp-1",
        status="ready",
        staging_file_path=str(file_path),
        match_method="staging:isrc",
        confidence=100,
        reason="Downloaded audio file matched this Spotify track.",
    )
    database.upsert_library_acquisition_job(
        source.id,
        {
            "spotify_track_id": "sp-1",
            "provider": "deemix",
            "deezer_track_id": "dz-1",
            "status": "downloaded",
            "confidence": 100,
            "match_method": "isrc",
            "download_id": "download-1",
            "output_dir": adapter.storage_layout().permanent,
            "payload": {},
        },
    )
    monkeypatch.setattr(
        "app.library.scan_audio_files",
        lambda _path: [
            {
                "file_path": str(file_path),
                "title": "New Song",
                "artist": "Artist",
                "duration_ms": 180000,
                "isrc": "ISRC-1",
                "status": "unmatched",
            }
        ],
    )

    review = asyncio.run(
        refresh_library_review_state(
            database,
            adapter,
            source.id,
            deemix_client=FakeCompletedDeemixClient(),
        )
    )
    job = database.get_library_acquisition_job(source.id, "sp-1")

    assert review.ready_tracks == 1
    assert job is not None
    assert job.status == "ready"


def create_new_library_source(database: LocalDatabase):
    source = database.upsert_library_source(
        LibrarySourceIn(
            spotifyPlaylistId="playlist",
            spotifyPlaylistName="Permanent",
            tags=["Peak Time"],
            trackCount=1,
            enabled=True,
        )
    )
    database.upsert_library_tracks(
        source.id,
        [
            {
                "spotify_track_id": "sp-1",
                "spotify_uri": "spotify:track:sp-1",
                "title": "New Song",
                "artists": ["Artist"],
                "duration_ms": 180000,
                "isrc": "ISRC-1",
                "status": "new",
                "tags": ["Peak Time"],
                "reason": "New Spotify track needs download or manual matching.",
            }
        ],
    )
    return source


class FakeRekordboxAdapter:
    def __init__(
        self,
        tmp_path: Path,
        tracks: list[dict[str, Any]] | None = None,
    ) -> None:
        self.tmp_path = tmp_path
        self.tracks = tracks

    def read_library_snapshot(self) -> dict[str, Any]:
        if self.tracks is not None:
            return {
                "available": True,
                "tracks": self.tracks,
            }
        return {
            "available": True,
            "tracks": [
                {
                    "contentId": "rb-1",
                    "title": "Known Song",
                    "artist": "Artist",
                    "durationMs": 180000,
                    "isrc": "ISRC-1",
                    "filePath": str(self.tmp_path / "known.mp3"),
                }
            ],
        }

    def read_library_snapshot_cached(self) -> dict[str, Any]:
        return self.read_library_snapshot()

    def storage_layout(self) -> Any:
        return type(
            "StorageLayout",
            (),
            {"permanent": str(self.tmp_path / "storage" / "_rekordbox_sync" / "permanent")},
        )()


class FakeSpotifyClient:
    def __init__(self, *, snapshot_id: str, items: list[dict[str, Any]]) -> None:
        self.snapshot_id = snapshot_id
        self.items = items

    async def get_playlist(self, playlist_id: str) -> dict[str, Any]:
        return {
            "id": playlist_id,
            "name": "Permanent",
            "snapshot_id": self.snapshot_id,
            "images": [{"url": "https://example.com/cover.jpg"}],
        }

    async def get_playlist_items(self, playlist_id: str) -> list[dict[str, Any]]:
        return self.items


class FakeResolver:
    async def resolve(self, track: Any) -> DeezerResolveResult:
        candidate = DeezerTrackCandidate(
            id="dz-1",
            title=track.title,
            artist=", ".join(track.artists),
            album="Album",
            duration_ms=track.duration_ms,
            payload={},
        )
        return DeezerResolveResult(
            status="resolved",
            confidence=100,
            match_method="isrc",
            candidate=candidate,
            payload={
                "id": "dz-1",
                "title": track.title,
                "artist": {"name": "Artist"},
                "album": {"title": "Album"},
                "duration": 180,
                "track_token": "secret",
                "available_countries": ["FR"],
            },
        )


class FakeDeemixClient:
    async def status(self) -> DeemixStatus:
        return DeemixStatus(
            baseUrl="http://127.0.0.1:6595",
            available=True,
            authenticated=True,
            detail="Deemix local API is reachable and authenticated.",
        )

    async def update_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        return {"success": True}

    async def download_batch(
        self,
        track_ids: list[str],
        playlist_name: str,
        playlist_cover_url: str | None = None,
    ) -> dict[str, Any]:
        return {"downloadIds": ["download-1"]}

    async def queue(self) -> dict[str, Any]:
        return {"items": [{"id": "download-1", "status": "queued"}]}


class FakeCompletedDeemixClient(FakeDeemixClient):
    async def download_batch(
        self,
        track_ids: list[str],
        playlist_name: str,
        playlist_cover_url: str | None = None,
    ) -> dict[str, Any]:
        raise AssertionError("Completed active jobs must not be downloaded again.")

    async def queue(self) -> dict[str, Any]:
        return {
            "items": [
                {
                    "id": "download-1",
                    "trackId": "dz-1",
                    "status": "completed",
                }
            ]
        }


def spotify_item(
    track_id: str,
    title: str,
    artist: str,
    isrc: str | None = None,
) -> dict[str, Any]:
    return {
        "track": {
            "id": track_id,
            "uri": f"spotify:track:{track_id}",
            "name": title,
            "artists": [{"name": artist}],
            "duration_ms": 180000,
            "external_ids": {"isrc": isrc} if isrc else {},
            "type": "track",
            "is_local": False,
        }
    }
