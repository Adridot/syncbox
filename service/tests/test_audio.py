from pathlib import Path

from app.audio import find_downloaded_file


def test_find_downloaded_file_matches_basic_name(tmp_path: Path) -> None:
    f = tmp_path / "Gambino - Alicante.mp3"
    f.write_bytes(b"x")
    assert find_downloaded_file(tmp_path, isrc=None, title="Alicante", artist="Gambino") == str(f)


def test_find_downloaded_file_handles_trailing_dot_title(tmp_path: Path) -> None:
    # Deemix strips the trailing dot from "APT." -> file is "Rosé - APT.mp3".
    f = tmp_path / "Rosé - APT.mp3"
    f.write_bytes(b"x")
    assert find_downloaded_file(tmp_path, isrc=None, title="APT.", artist="Rosé") == str(f)


def test_find_downloaded_file_handles_rename_suffix(tmp_path: Path) -> None:
    f = tmp_path / "Artist - Song (1).mp3"
    f.write_bytes(b"x")
    assert find_downloaded_file(tmp_path, isrc=None, title="Song", artist="Artist") == str(f)


def test_find_downloaded_file_keeps_artist_trailing_dot(tmp_path: Path) -> None:
    # Deemix only strips the trailing dot from the *final* component (title), so an
    # interior artist keeps it: "Boney M." -> "Boney M. - Ma Baker.mp3".
    f = tmp_path / "Boney M. - Ma Baker.mp3"
    f.write_bytes(b"x")
    assert find_downloaded_file(tmp_path, isrc=None, title="Ma Baker", artist="Boney M.") == str(f)


def test_find_downloaded_file_returns_none_when_absent(tmp_path: Path) -> None:
    assert find_downloaded_file(tmp_path, isrc=None, title="Nope", artist="Nobody") is None
