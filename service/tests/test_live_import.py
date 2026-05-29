from pathlib import Path

from app.live_import import build_live_import_package, safe_event_slug


def test_safe_event_slug_normalizes_names() -> None:
    assert safe_event_slug("Mariage été 2026 !!!") == "mariage-ete-2026"


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
