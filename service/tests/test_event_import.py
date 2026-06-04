import asyncio
from pathlib import Path
from types import SimpleNamespace

from app import event_import
from app.audio import scan_audio_files
from app.db import LocalDatabase
from app.event_import import (
    add_spotify_track_to_event,
    build_event_track_rows,
    create_manual_event,
    scan_event_staging,
)
from app.models import RekordboxTrack, SpotifyTrack


class FakeAdapter:
    """Minimal RekordboxAdapter stand-in for event scaffolding/matching tests."""

    def __init__(self, events_dir: Path, tracks: list[dict] | None = None) -> None:
        self._events_dir = events_dir
        self._tracks = tracks or []

    def ensure_storage_layout(self):
        self._events_dir.mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(events=str(self._events_dir))

    def read_library_snapshot(self):
        return {"available": True, "tracks": self._tracks}

    def read_library_snapshot_cached(self):
        return self.read_library_snapshot()


class FakeSpotifyClient:
    def __init__(self, track_payload: dict) -> None:
        self._payload = track_payload
        self.requested_id: str | None = None

    async def get_track(self, track_id: str) -> dict:
        self.requested_id = track_id
        return self._payload


def test_create_manual_event_is_empty_and_unlinked(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    adapter = FakeAdapter(tmp_path / "events")

    review = create_manual_event(database, adapter, "  Soirée Test  ")

    assert review.event_name == "Soirée Test"
    assert review.spotify_playlist_id.startswith("manual:")
    assert review.tracks == []


def test_add_spotify_track_matches_collection_then_adds_additively(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    # First track already exists in the Rekordbox snapshot (matched by ISRC).
    adapter = FakeAdapter(
        tmp_path / "events",
        tracks=[
            {
                "contentId": "rb-1",
                "title": "Known Song",
                "artist": "Known Artist",
                "durationMs": 181000,
                "isrc": "USRC10000001",
            }
        ],
    )
    review = create_manual_event(database, adapter, "Manual Event")
    event_id = review.id

    # Spotify ids are 22-char base62 strings (validated before the API call).
    id_known = "1xV89fEoj4JNCrbMq5rA7G"
    id_new = "5vNRhkKd0yEAg8suGBpjeY"
    matched_client = FakeSpotifyClient(
        {
            "id": id_known,
            "uri": f"spotify:track:{id_known}",
            "name": "Known Song",
            "artists": [{"name": "Known Artist"}],
            "duration_ms": 180000,
            "external_ids": {"isrc": "USRC10000001"},
            "type": "track",
        }
    )
    review = asyncio.run(
        add_spotify_track_to_event(
            database, adapter, matched_client, event_id,
            f"https://open.spotify.com/track/{id_known}",
        )
    )
    assert matched_client.requested_id == id_known
    assert len(review.tracks) == 1
    assert review.tracks[0].status == "matched"
    assert review.tracks[0].rekordbox_content_id == "rb-1"

    # A second, unknown track is appended without dropping the first (UPSERT).
    missing_client = FakeSpotifyClient(
        {
            "id": id_new,
            "uri": f"spotify:track:{id_new}",
            "name": "New Song",
            "artists": [{"name": "Someone"}],
            "duration_ms": 200000,
            "external_ids": {"isrc": "USRC10000002"},
            "type": "track",
        }
    )
    review = asyncio.run(
        add_spotify_track_to_event(
            database, adapter, missing_client, event_id, f"spotify:track:{id_new}"
        )
    )
    statuses = {t.spotify_track_id: t.status for t in review.tracks}
    assert statuses == {id_known: "matched", id_new: "missing"}


def test_add_spotify_track_rejects_invalid_link(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    adapter = FakeAdapter(tmp_path / "events")
    event_id = create_manual_event(database, adapter, "Manual Event").id

    client = FakeSpotifyClient({})
    try:
        asyncio.run(
            add_spotify_track_to_event(database, adapter, client, event_id, "not-a-link")
        )
        assert False, "expected ValueError for an invalid link"
    except ValueError:
        pass
    assert client.requested_id is None  # never called Spotify


def test_event_track_rows_mark_duplicate_spotify_tracks() -> None:
    spotify_track = SpotifyTrack(
        id="spotify-1",
        uri="spotify:track:spotify-1",
        title="Same Song",
        artists=["Artist"],
        durationMs=180000,
        isrc="USRC17607839",
    )

    rows = build_event_track_rows(1, [spotify_track, spotify_track], [])

    assert rows[0]["status"] == "missing"
    assert rows[1]["status"] == "ignored"


def test_event_track_rows_match_rekordbox_by_isrc() -> None:
    spotify_track = SpotifyTrack(
        id="spotify-1",
        uri="spotify:track:spotify-1",
        title="Song",
        artists=["Artist"],
        durationMs=180000,
        isrc="USRC17607839",
    )
    rekordbox_track = RekordboxTrack(
        contentId="rb-1",
        title="Different Title",
        artist="Other",
        durationMs=170000,
        isrc="USRC17607839",
    )

    rows = build_event_track_rows(1, [spotify_track], [rekordbox_track])

    assert rows[0]["status"] == "matched"
    assert rows[0]["rekordbox_content_id"] == "rb-1"
    assert rows[0]["payload"]["rekordbox"]["title"] == "Different Title"
    assert rows[0]["payload"]["rekordbox"]["artist"] == "Other"


def test_event_review_returns_rekordbox_track_details(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    event_id = database.create_event_import(
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
    database.upsert_event_tracks(
        event_id,
        [
            {
                "spotify_track_id": "spotify-1",
                "spotify_uri": "spotify:track:spotify-1",
                "title": "Requested Song",
                "artists": ["Requested Artist"],
                "duration_ms": 180000,
                "status": "ambiguous",
                "rekordbox_content_id": "rb-1",
                "reason": "Top metadata matches are too close for automatic linking.",
                "payload": {
                    "rekordbox": {
                        "title": "Existing Song",
                        "artist": "Existing Artist",
                        "filePath": "/music/existing-song.mp3",
                    }
                },
            }
        ],
    )

    review = database.get_event_review(event_id)

    assert review is not None
    assert review.tracks[0].title == "Requested Song"
    assert review.tracks[0].rekordbox_title == "Existing Song"
    assert review.tracks[0].rekordbox_artist == "Existing Artist"
    assert review.tracks[0].rekordbox_file_path == "/music/existing-song.mp3"


def test_event_tracks_can_be_marked_applied(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    event_id = database.create_event_import(
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
    database.upsert_event_tracks(
        event_id,
        [
            {
                "spotify_track_id": "spotify-1",
                "spotify_uri": "spotify:track:spotify-1",
                "title": "Existing Song",
                "artists": ["Artist"],
                "duration_ms": 180000,
                "status": "matched",
                "rekordbox_content_id": "rb-1",
                "reason": "ISRC matched exactly.",
            },
            {
                "spotify_track_id": "spotify-2",
                "spotify_uri": "spotify:track:spotify-2",
                "title": "Unresolved Song",
                "artists": ["Artist"],
                "duration_ms": 180000,
                "status": "missing",
                "reason": "No match.",
            },
        ],
    )

    database.mark_event_tracks_applied(event_id, ["spotify-1"])
    review = database.get_event_review(event_id)

    assert review is not None
    assert review.applied_tracks == 1
    assert review.matched_tracks == 0
    assert review.missing_tracks == 1
    assert review.tracks[0].status == "applied"


def test_scan_audio_files_ignores_non_audio(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "track.mp3").write_bytes(b"fake")
    (audio_dir / "notes.txt").write_text("ignore", encoding="utf-8")

    files = scan_audio_files(audio_dir)

    assert len(files) == 1
    assert files[0]["title"] == "track"


def test_scan_event_staging_matches_missing_track(tmp_path: Path, monkeypatch) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    audio_dir = tmp_path / "event" / "audio"
    audio_dir.mkdir(parents=True)
    track_path = audio_dir / "New Song.mp3"
    track_path.write_bytes(b"fake")
    event_id = database.create_event_import(
        {
            "event_name": "Client Event",
            "event_slug": "client-event",
            "spotify_playlist_id": "playlist",
            "spotify_playlist_name": "Client Playlist",
            "default_tag": "Client Event",
            "event_dir": str(tmp_path / "event"),
            "audio_dir": str(audio_dir),
            "playlist_path": str(tmp_path / "event" / "client-event.m3u8"),
        }
    )
    database.upsert_event_tracks(
        event_id,
        [
            {
                "spotify_track_id": "spotify-1",
                "spotify_uri": "spotify:track:spotify-1",
                "title": "New Song",
                "artists": ["Artist"],
                "duration_ms": 180000,
                "status": "missing",
                "reason": "No match.",
            }
        ],
    )
    monkeypatch.setattr(
        event_import,
        "scan_audio_files",
        lambda _, *, fresh=False: [
            {
                "file_path": str(track_path),
                "title": "New Song",
                "artist": "Artist",
                "duration_ms": 180000,
                "isrc": None,
                "status": "unmatched",
            }
        ],
    )

    review = scan_event_staging(database, event_id)

    assert review.staging_files[0].status == "matched"
    assert review.tracks[0].status == "ready"
    assert review.tracks[0].staging_file_path == str(track_path)


def test_scan_event_staging_invalidates_removed_ready_file(tmp_path: Path) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    audio_dir = tmp_path / "event" / "audio"
    audio_dir.mkdir(parents=True)
    removed_path = audio_dir / "Removed Song.mp3"
    event_id = database.create_event_import(
        {
            "event_name": "Client Event",
            "event_slug": "client-event",
            "spotify_playlist_id": "playlist",
            "spotify_playlist_name": "Client Playlist",
            "default_tag": "Client Event",
            "event_dir": str(tmp_path / "event"),
            "audio_dir": str(audio_dir),
            "playlist_path": str(tmp_path / "event" / "client-event.m3u8"),
        }
    )
    database.upsert_event_tracks(
        event_id,
        [
            {
                "spotify_track_id": "spotify-1",
                "spotify_uri": "spotify:track:spotify-1",
                "title": "Removed Song",
                "artists": ["Artist"],
                "duration_ms": 180000,
                "status": "ready",
                "staging_file_path": str(removed_path),
                "reason": "Staged audio file matched this Spotify track.",
            }
        ],
    )
    database.upsert_staging_files(
        event_id,
        [
            {
                "file_path": str(removed_path),
                "title": "Removed Song",
                "artist": "Artist",
                "duration_ms": 180000,
                "isrc": None,
                "matched_spotify_track_id": "spotify-1",
                "status": "matched",
            }
        ],
    )
    database.upsert_acquisition_job(
        event_id,
        {
            "spotify_track_id": "spotify-1",
            "provider": "deemix",
            "deezer_track_id": "3135556",
            "status": "ready",
            "confidence": 100,
            "match_method": "isrc",
            "output_dir": str(audio_dir),
        },
    )

    review = scan_event_staging(database, event_id)
    job = database.get_acquisition_job(event_id, "spotify-1")

    assert review.tracks[0].status == "missing"
    assert review.tracks[0].staging_file_path is None
    assert review.staging_files == []
    assert job is not None
    assert job.status == "acquisition_failed"
    assert job.error == "Staged file is missing from the event folder."


def test_scan_event_staging_revalidates_stale_automatic_match(
    tmp_path: Path, monkeypatch
) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    audio_dir = tmp_path / "event" / "audio"
    audio_dir.mkdir(parents=True)
    wrong_path = audio_dir / "Different Song.mp3"
    wrong_path.write_bytes(b"fake")
    event_id = database.create_event_import(
        {
            "event_name": "Client Event",
            "event_slug": "client-event",
            "spotify_playlist_id": "playlist",
            "spotify_playlist_name": "Client Playlist",
            "default_tag": "Client Event",
            "event_dir": str(tmp_path / "event"),
            "audio_dir": str(audio_dir),
            "playlist_path": str(tmp_path / "event" / "client-event.m3u8"),
        }
    )
    database.upsert_event_tracks(
        event_id,
        [
            {
                "spotify_track_id": "spotify-1",
                "spotify_uri": "spotify:track:spotify-1",
                "title": "Requested Song",
                "artists": ["Artist"],
                "duration_ms": 180000,
                "status": "ready",
                "staging_file_path": str(wrong_path),
                "match_method": "staging:metadata",
                "confidence": 54,
                "reason": "Staged audio file matched this Spotify track.",
            }
        ],
    )
    monkeypatch.setattr(
        event_import,
        "scan_audio_files",
        lambda _, *, fresh=False: [
            {
                "file_path": str(wrong_path),
                "title": "Different Song",
                "artist": "Artist",
                "duration_ms": 180000,
                "isrc": None,
                "status": "unmatched",
            }
        ],
    )

    review = scan_event_staging(database, event_id)

    assert review.tracks[0].status == "missing"
    assert review.tracks[0].staging_file_path is None
    assert review.staging_files[0].status == "unmatched"
    assert review.staging_files[0].matched_spotify_track_id is None


def test_scan_event_staging_assigns_each_file_once(
    tmp_path: Path, monkeypatch
) -> None:
    database = LocalDatabase(tmp_path / "app.sqlite3")
    database.migrate()
    audio_dir = tmp_path / "event" / "audio"
    audio_dir.mkdir(parents=True)
    track_path = audio_dir / "Shared Song.mp3"
    track_path.write_bytes(b"fake")
    event_id = database.create_event_import(
        {
            "event_name": "Client Event",
            "event_slug": "client-event",
            "spotify_playlist_id": "playlist",
            "spotify_playlist_name": "Client Playlist",
            "default_tag": "Client Event",
            "event_dir": str(tmp_path / "event"),
            "audio_dir": str(audio_dir),
            "playlist_path": str(tmp_path / "event" / "client-event.m3u8"),
        }
    )
    database.upsert_event_tracks(
        event_id,
        [
            {
                "spotify_track_id": "spotify-1",
                "spotify_uri": "spotify:track:spotify-1",
                "title": "Shared Song",
                "artists": ["Artist"],
                "duration_ms": 180000,
                "status": "missing",
                "reason": "No match.",
            },
            {
                "spotify_track_id": "spotify-2",
                "spotify_uri": "spotify:track:spotify-2",
                "title": "Shared Song",
                "artists": ["Artist"],
                "duration_ms": 180000,
                "status": "missing",
                "reason": "No match.",
            },
        ],
    )
    monkeypatch.setattr(
        event_import,
        "scan_audio_files",
        lambda _, *, fresh=False: [
            {
                "file_path": str(track_path),
                "title": "Shared Song",
                "artist": "Artist",
                "duration_ms": 180000,
                "isrc": None,
                "status": "unmatched",
            }
        ],
    )

    review = scan_event_staging(database, event_id)
    statuses = {track.spotify_track_id: track.status for track in review.tracks}
    ready_tracks = [track for track in review.tracks if track.status == "ready"]

    assert statuses["spotify-1"] == "ready"
    assert statuses["spotify-2"] == "missing"
    assert len(ready_tracks) == 1
    assert ready_tracks[0].staging_file_path == str(track_path)
    assert review.staging_files[0].matched_spotify_track_id == "spotify-1"
