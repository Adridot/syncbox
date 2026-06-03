import asyncio
from pathlib import Path
from typing import Any

import httpx

from app import event_import
from app.acquisition import (
    DeemixClient,
    DeezerResolveResult,
    DeezerResolver,
    DeezerTrackCandidate,
    deemix_event_settings,
    ensure_deemix_authenticated,
    refresh_acquisition_jobs,
    run_auto_acquisition,
)
from app.db import LocalDatabase
from app.models import DeemixStatus, EventTrackReview


def test_login_arl_posts_arl_body(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200
        text = ""
        reason_phrase = "OK"

        def json(self) -> dict[str, Any]:
            return {"success": True}

    async def fake_request(self, method, url, **kwargs):  # type: ignore[no-untyped-def]
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    result = asyncio.run(DeemixClient().login_arl("my-arl"))

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/api/auth/login")
    assert captured["json"] == {"arl": "my-arl"}
    assert result == {"success": True}


def test_ensure_deemix_authenticated_logs_in_when_arl_stored(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()

    class StubClient:
        def __init__(self, authenticated: bool) -> None:
            self._authenticated = authenticated
            self.logged_in_with: str | None = None

        async def status(self) -> DeemixStatus:
            return DeemixStatus(
                baseUrl="x",
                available=True,
                authenticated=self._authenticated,
                detail="stub",
            )

        async def login_arl(self, arl: str) -> dict[str, Any]:
            self.logged_in_with = arl
            return {"success": True}

    # No ARL stored -> no login attempted.
    client = StubClient(authenticated=False)
    asyncio.run(ensure_deemix_authenticated(database, client))
    assert client.logged_in_with is None

    # ARL stored + not authenticated -> push it.
    database.set_setting("deemix_arl", "stored-arl")
    client = StubClient(authenticated=False)
    asyncio.run(ensure_deemix_authenticated(database, client))
    assert client.logged_in_with == "stored-arl"

    # Already authenticated -> skip the login.
    client = StubClient(authenticated=True)
    asyncio.run(ensure_deemix_authenticated(database, client))
    assert client.logged_in_with is None


def test_deezer_resolver_matches_isrc_exactly() -> None:
    resolver = FakeDeezerResolver(
        {
            "/track/isrc:USRC17607839": {
                "id": 3135556,
                "title": "Song",
                "artist": {"name": "Artist"},
                "album": {"title": "Album"},
                "duration": 180,
            }
        }
    )

    result = asyncio.run(resolver.resolve(track_review(isrc="USRC17607839")))

    assert result.status == "resolved"
    assert result.match_method == "isrc"
    assert result.confidence == 100
    assert result.candidate is not None
    assert result.candidate.id == "3135556"


def test_deezer_resolver_uses_metadata_thresholds() -> None:
    auto_result = asyncio.run(
        FakeDeezerResolver(
            {
                "/search": {
                    "data": [
                        {
                            "id": 1,
                            "title": "Song",
                            "artist": {"name": "Other Artist"},
                            "duration": 180,
                        }
                    ]
                }
            }
        ).resolve_by_metadata(track_review())
    )
    ambiguous_result = asyncio.run(
        FakeDeezerResolver(
            {
                "/search": {
                    "data": [
                        {
                            "id": 2,
                            "title": "Song",
                            "artist": {"name": "Other"},
                            "duration": 180,
                        }
                    ]
                }
            }
        ).resolve_by_metadata(track_review())
    )
    failed_result = asyncio.run(
        FakeDeezerResolver(
            {
                "/search": {
                    "data": [
                        {
                            "id": 3,
                            "title": "Song",
                            "artist": {"name": "Random Name"},
                            "duration": 180,
                        }
                    ]
                }
            }
        ).resolve_by_metadata(track_review())
    )

    assert auto_result.status == "resolved"
    assert ambiguous_result.status == "acquisition_ambiguous"
    assert failed_result.status == "acquisition_failed"


def test_acquisition_jobs_are_persisted(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    event_id = create_event(database, tmp_path)

    job = database.upsert_acquisition_job(
        event_id,
        {
            "spotify_track_id": "spotify-missing",
            "provider": "deemix",
            "deezer_track_id": "3135556",
            "status": "queued",
            "confidence": 100,
            "match_method": "isrc",
            "download_id": "download-1",
            "output_dir": str(tmp_path / "event" / "audio"),
            "payload": {"source": "test"},
        },
    )

    jobs = database.list_acquisition_jobs(event_id)

    assert job.id is not None
    assert len(jobs) == 1
    assert jobs[0].spotify_track_id == "spotify-missing"
    assert jobs[0].payload == {"source": "test"}


def test_auto_acquisition_queues_only_missing_tracks(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    event_id = create_event(database, tmp_path)
    database.upsert_event_tracks(
        event_id,
        [
            event_track("spotify-matched", "Existing Song", "matched"),
            event_track("spotify-ready", "Ready Song", "ready", staging_file_path="ready.mp3"),
            event_track("spotify-applied", "Applied Song", "applied"),
            event_track("spotify-missing", "Missing Song", "missing"),
        ],
    )
    deemix_client = FakeDeemixClient()

    response = asyncio.run(
        run_auto_acquisition(
            database,
            event_id,
            deemix_client=deemix_client,
            deezer_resolver=FakeAutoResolver(),
        )
    )

    assert response.created == 1
    assert response.queued == 1
    assert deemix_client.downloaded_track_ids == ["dz-spotify-missing"]
    assert deemix_client.settings_payload["downloadPath"] == str(tmp_path / "event" / "audio")
    assert deemix_client.settings_payload["quality"] == "MP3_320"
    assert [job.spotify_track_id for job in response.jobs] == ["spotify-missing"]


def test_deemix_offline_marks_jobs_failed(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    event_id = create_event(database, tmp_path)
    database.upsert_event_tracks(
        event_id,
        [event_track("spotify-missing", "Missing Song", "missing")],
    )

    response = asyncio.run(
        run_auto_acquisition(
            database,
            event_id,
            deemix_client=FakeDeemixClient(available=False, authenticated=False),
            deezer_resolver=FakeAutoResolver(),
        )
    )

    assert response.failed == 1
    assert response.jobs[0].status == "acquisition_failed"
    assert "not reachable" in str(response.jobs[0].error)


def test_completed_queue_scans_staging_and_marks_ready(tmp_path: Path, monkeypatch) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    event_id = create_event(database, tmp_path)
    audio_dir = tmp_path / "event" / "audio"
    audio_dir.mkdir(parents=True)
    track_path = audio_dir / "Missing Song.mp3"
    track_path.write_bytes(b"fake")
    database.upsert_event_tracks(
        event_id,
        [event_track("spotify-missing", "Missing Song", "missing")],
    )
    database.upsert_acquisition_job(
        event_id,
        {
            "spotify_track_id": "spotify-missing",
            "provider": "deemix",
            "deezer_track_id": "3135556",
            "status": "queued",
            "confidence": 100,
            "match_method": "isrc",
            "download_id": "download-1",
            "output_dir": str(audio_dir),
        },
    )
    monkeypatch.setattr(
        event_import,
        "scan_audio_files",
        lambda _: [
            {
                "file_path": str(track_path),
                "title": "Missing Song",
                "artist": "Artist",
                "duration_ms": 180000,
                "isrc": None,
                "status": "unmatched",
            }
        ],
    )

    jobs = asyncio.run(
        refresh_acquisition_jobs(
            database,
            event_id,
            deemix_client=FakeDeemixClient(queue_status="completed"),
        )
    )
    review = database.get_event_review(event_id)

    assert review is not None
    assert review.tracks[0].status == "ready"
    assert jobs[0].status == "ready"


def test_deemix_event_settings_force_event_audio_output(tmp_path: Path) -> None:
    settings = deemix_event_settings(tmp_path / "audio")

    assert settings["downloadPath"] == str(tmp_path / "audio")
    assert settings["quality"] == "MP3_320"
    assert settings["createArtistFolder"] is False
    assert settings["createAlbumFolder"] is False
    assert settings["overwriteFiles"] == "rename"


class FakeDeezerResolver(DeezerResolver):
    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self.responses = responses

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.responses.get(path, {})


class FakeAutoResolver:
    async def resolve(self, track: EventTrackReview) -> DeezerResolveResult:
        candidate = DeezerTrackCandidate(
            id=f"dz-{track.spotify_track_id}",
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
            payload={"id": candidate.id},
        )


class FakeDeemixClient:
    def __init__(
        self,
        *,
        available: bool = True,
        authenticated: bool = True,
        queue_status: str = "queued",
    ) -> None:
        self.available = available
        self.authenticated = authenticated
        self.queue_status = queue_status
        self.settings_payload: dict[str, Any] = {}
        self.downloaded_track_ids: list[str] = []

    async def status(self) -> DeemixStatus:
        return DeemixStatus(
            baseUrl="http://127.0.0.1:6595",
            available=self.available,
            authenticated=self.authenticated,
            detail=(
                "Deemix local API is reachable and authenticated."
                if self.available and self.authenticated
                else "Deemix local API is not reachable."
            ),
        )

    async def update_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        self.settings_payload = settings
        return {"success": True}

    async def download_batch(
        self,
        track_ids: list[str],
        playlist_name: str,
        playlist_cover_url: str | None = None,
    ) -> dict[str, Any]:
        self.downloaded_track_ids = track_ids
        return {"downloadIds": ["download-1"]}

    async def queue(self) -> dict[str, Any]:
        return {"items": [{"id": "download-1", "status": self.queue_status}]}


def track_review(isrc: str | None = None) -> EventTrackReview:
    return EventTrackReview(
        id=1,
        eventId=1,
        spotifyTrackId="spotify-missing",
        spotifyUri="spotify:track:spotify-missing",
        title="Song",
        artists=["Artist"],
        durationMs=180000,
        isrc=isrc,
        status="missing",
        confidence=0,
        reason="No match.",
    )


def create_event(database: LocalDatabase, tmp_path: Path) -> int:
    return database.create_event_import(
        {
            "event_name": "Client Event",
            "event_slug": "client-event",
            "spotify_playlist_id": "playlist",
            "spotify_playlist_name": "Client Playlist",
            "default_tag": "Client Event",
            "event_dir": str(tmp_path / "event"),
            "audio_dir": str(tmp_path / "event" / "audio"),
            "playlist_path": str(tmp_path / "event" / "client-event.m3u8"),
        }
    )


def event_track(
    spotify_track_id: str,
    title: str,
    status: str,
    *,
    staging_file_path: str | None = None,
) -> dict[str, Any]:
    return {
        "spotify_track_id": spotify_track_id,
        "spotify_uri": f"spotify:track:{spotify_track_id}",
        "title": title,
        "artists": ["Artist"],
        "duration_ms": 180000,
        "status": status,
        "staging_file_path": staging_file_path,
        "reason": "Test row.",
    }
