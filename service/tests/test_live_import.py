from pathlib import Path

from app.live_import import (
    build_live_import_package,
    claim_event_dir,
    safe_event_slug,
)


def test_safe_event_slug_normalizes_names() -> None:
    assert safe_event_slug("Mariage été 2026 !!!") == "mariage-ete-2026"


def test_claim_event_dir_atomically_creates_fresh_folders(tmp_path: Path) -> None:
    events_root = tmp_path / "events"
    # Each claim CREATES the folder, so the next claim must pick the next suffix.
    assert claim_event_dir(events_root, "Test") == ("test", events_root / "test")
    assert claim_event_dir(events_root, "Test") == ("test-2", events_root / "test-2")
    assert claim_event_dir(events_root, "Test") == ("test-3", events_root / "test-3")
    assert (events_root / "test").is_dir()


def test_build_live_import_package_unique_never_reuses_a_folder(tmp_path: Path) -> None:
    events_root = tmp_path / "events"
    first = build_live_import_package(events_root, "Test", unique=True)
    second = build_live_import_package(events_root, "Test", unique=True)
    assert first["eventSlug"] == "test"
    assert second["eventSlug"] == "test-2"
    assert first["eventDir"] != second["eventDir"]


def test_build_live_import_package_default_reuses_named_folder(tmp_path: Path) -> None:
    # Live M3U8 import keeps targeting the same named folder (default unique=False).
    events_root = tmp_path / "events"
    first = build_live_import_package(events_root, "Test")
    second = build_live_import_package(events_root, "Test")
    assert first["eventSlug"] == second["eventSlug"] == "test"


def test_live_import_package_writes_m3u8_from_audio_files(tmp_path: Path) -> None:
    events_root = tmp_path / "events"
    audio_dir = events_root / "client-event" / "audio"
    audio_dir.mkdir(parents=True)
    track_path = audio_dir / "track.mp3"
    ignored_path = audio_dir / "notes.txt"
    track_path.write_bytes(b"fake")
    ignored_path.write_text("ignore", encoding="utf-8")

    package = build_live_import_package(events_root, "Client Event")

    assert package["trackCount"] == 1
    assert package["audioFiles"] == [str(track_path)]
    playlist_path = Path(str(package["playlistPath"]))
    assert playlist_path.read_text(encoding="utf-8").splitlines() == [
        "#EXTM3U",
        str(track_path),
    ]
