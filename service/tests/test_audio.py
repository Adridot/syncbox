from pathlib import Path

from app import audio
from app.audio import find_downloaded_file, scan_audio_files


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


def test_find_downloaded_file_replaces_illegal_chars_with_underscore(tmp_path: Path) -> None:
    # Regression (cloud "missing"): Deemix REPLACES illegal filename chars with
    # "_", it doesn't drop them — "AC/DC" -> "AC_DC".
    f = tmp_path / "AC_DC - Hells Bells.mp3"
    f.write_bytes(b"x")
    assert find_downloaded_file(tmp_path, isrc=None, title="Hells Bells", artist="AC/DC") == str(f)


def test_find_downloaded_file_converts_spotify_dash_suffix_to_deezer_parens(tmp_path: Path) -> None:
    # Regression: Spotify writes "Song - Radio Edit" but Deezer/Deemix names the
    # file "Artist - Song (Radio Edit).mp3". Must match from the Spotify title.
    f = tmp_path / "Artist - Song (Radio Edit).mp3"
    f.write_bytes(b"x")
    assert find_downloaded_file(tmp_path, isrc=None, title="Song - Radio Edit", artist="Artist") == str(f)


def test_find_downloaded_file_combines_paren_suffix_and_underscore(tmp_path: Path) -> None:
    # Regression ("What A Life"): the real cracked case — Spotify dash-suffix +
    # quotes that Deemix turned into "_". Found from the Spotify title alone.
    f = tmp_path / "Scarlet Pleasure - What A Life (From the Motion Picture _Another Round_).mp3"
    f.write_bytes(b"x")
    found = find_downloaded_file(
        tmp_path,
        isrc=None,
        title='What A Life - From the Motion Picture "Another Round"',
        artist="Scarlet Pleasure",
    )
    assert found == str(f)


def test_find_downloaded_file_returns_none_when_absent(tmp_path: Path) -> None:
    assert find_downloaded_file(tmp_path, isrc=None, title="Nope", artist="Nobody") is None


def test_scan_audio_files_fresh_bypasses_the_cache(tmp_path: Path, monkeypatch) -> None:
    # Regression (cloud "downloaded" stuck): a just-landed file must be visible
    # when fresh=True even if the cache holds a (same-signature) stale listing.
    audio._SCAN_CACHE.clear()
    folder = tmp_path / "audio"
    folder.mkdir()
    (folder / "a.mp3").write_bytes(b"x")

    calls = {"n": 0}
    real_uncached = audio._scan_audio_files_uncached

    def counting(path: Path):
        calls["n"] += 1
        return real_uncached(path)

    monkeypatch.setattr(audio, "_scan_audio_files_uncached", counting)

    scan_audio_files(folder)
    assert calls["n"] == 1
    scan_audio_files(folder)  # same signature -> served from cache
    assert calls["n"] == 1
    scan_audio_files(folder, fresh=True)  # fresh -> always re-reads the folder
    assert calls["n"] == 2


def test_locate_downloaded_track_file_prefers_deezer_then_spotify(tmp_path: Path) -> None:
    from app.audio import locate_downloaded_track_file

    # Deemix named the file with the Deezer title (differs from Spotify's).
    (tmp_path / "Kim Wilde - Cambodia.mp3").write_bytes(b"x")
    assert locate_downloaded_track_file(
        [tmp_path],
        deezer_title="Cambodia",
        deezer_artist="Kim Wilde",
        fallback_title="Cambodia - Single Version",
        fallback_artist="Kim Wilde",
    ) == str(tmp_path / "Kim Wilde - Cambodia.mp3")


def test_locate_downloaded_track_file_spotify_fallback(tmp_path: Path) -> None:
    from app.audio import locate_downloaded_track_file

    # No Deezer metadata (e.g. job payload missing): fall back to Spotify names.
    (tmp_path / "Artist - Song.mp3").write_bytes(b"x")
    assert locate_downloaded_track_file(
        [tmp_path], fallback_title="Song", fallback_artist="Artist"
    ) == str(tmp_path / "Artist - Song.mp3")


def test_locate_downloaded_track_file_searches_multiple_folders(tmp_path: Path) -> None:
    from app.audio import locate_downloaded_track_file

    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    (second / "Artist - Song.mp3").write_bytes(b"x")
    assert locate_downloaded_track_file(
        [first, second], fallback_title="Song", fallback_artist="Artist"
    ) == str(second / "Artist - Song.mp3")


def test_locate_downloaded_track_file_returns_none_when_absent(tmp_path: Path) -> None:
    from app.audio import locate_downloaded_track_file

    assert locate_downloaded_track_file(
        [tmp_path], fallback_title="Nope", fallback_artist="Nobody"
    ) is None
