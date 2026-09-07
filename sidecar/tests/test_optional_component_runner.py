from pathlib import Path
import asyncio
import runpy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


REPO = Path(__file__).resolve().parents[2]


def test_downloaded_filename_contains_only_artist_and_title():
    source = (REPO / "scripts/run_b1_deezer_acquisition.py").read_text()

    assert 'config.session.filepaths.track_format = "{artist} - {title}"' in source


def test_downloaded_file_metadata_is_verified():
    namespace = __import__("runpy").run_path(
        str(REPO / "scripts/run_b1_deezer_acquisition.py")
    )

    class Album:
        album = "Album"
        albumartist = "Album Artist"

    class Metadata:
        title = "Title"
        artist = "Artist"
        album = Album()
        isrc = "FRABC2600001"
        tracknumber = 7
        discnumber = 2

    class Audio:
        tags = {
            "title": ["Title"],
            "artist": ["Artist"],
            "album": ["Album"],
            "albumartist": ["Album Artist"],
            "isrc": ["FRABC2600001"],
            "tracknumber": ["7/12"],
            "discnumber": ["2/2"],
        }

    result = namespace["_embedded_metadata"](Audio(), Metadata())
    assert result["metadata_embedded"] is True

    Audio.tags = {}
    with pytest.raises(namespace["PocFailed"], match="metadata_missing"):
        namespace["_embedded_metadata"](Audio(), Metadata())


@pytest.mark.parametrize(
    "exact_item,effective_id,quality,expected_error",
    [
        (True, "123", 1, None),
        (True, "123", 0, None),
        (True, "456", 1, "streamrip_exact_item_unavailable"),
        (False, "456", 1, None),
        (False, "456", 0, None),
        (True, None, 1, "streamrip_effective_item_missing"),
    ],
)
def test_download_checks_effective_identity_before_audio(
    tmp_path, monkeypatch, exact_item, effective_id, quality, expected_error
):
    namespace = runpy.run_path(str(REPO / "scripts/run_b1_deezer_acquisition.py"))
    download = namespace["_download"]
    settings = SimpleNamespace(**{
        name: SimpleNamespace() for name in (
            "deezer", "downloads", "filepaths", "artwork", "database",
            "conversion", "cli", "misc",
        )
    })
    client = SimpleNamespace(login=AsyncMock(), session=SimpleNamespace(close=AsyncMock()))
    output = tmp_path / "track.mp3"

    async def rip():
        output.write_bytes(b"fixture audio")

    track = SimpleNamespace(
        downloadable=SimpleNamespace(id=effective_id, quality=quality),
        meta=SimpleNamespace(isrc="FRABC2600001"),
        rip=AsyncMock(side_effect=rip), download_path=str(output),
    )
    component = {
        "Config": SimpleNamespace(defaults=lambda: SimpleNamespace(session=settings)),
        "streamrip_db": SimpleNamespace(Dummy=lambda: None, Database=lambda *args: None),
        "DeezerClient": lambda config: client,
        "PendingSingle": lambda *args: SimpleNamespace(resolve=AsyncMock(return_value=track)),
        "certifi": None,
        "MutagenFile": lambda *args, **kwargs: SimpleNamespace(info=SimpleNamespace(length=180)),
        "Image": None,
    }
    monkeypatch.setitem(download.__globals__, "_resolve_track", lambda *args: 180)
    monkeypatch.setitem(download.__globals__, "_resolve_isrc", lambda *args: (123, 180))
    monkeypatch.setitem(download.__globals__, "_embedded_metadata", lambda *args: {})
    monkeypatch.setitem(download.__globals__, "_embedded_artwork", lambda *args: {})
    operation = download(
        component, "fixture credential", None if exact_item else "FRABC2600001",
        tmp_path, track_id=123 if exact_item else None, exact_item=exact_item,
    )
    if expected_error:
        with pytest.raises(namespace["PocFailed"], match=expected_error):
            asyncio.run(operation)
        track.rip.assert_not_awaited()
        assert not output.exists()
    else:
        result = asyncio.run(operation)
        track.rip.assert_awaited_once()
        assert result["deezer_track_id"] == 123
        assert result["effective_deezer_track_id"] == int(effective_id)
        assert result["quality"] == quality
        assert result["exact_item"] is exact_item
        assert result["protocol_version"] == 2
    assert settings.deezer.arl == ""
    assert settings.deezer.quality == 1
    assert settings.deezer.lower_quality_if_not_available is True
    client.session.close.assert_awaited_once()


@pytest.mark.parametrize("selector", [[], ["--track-id", "0"], ["--track-id", "-1"]])
def test_exact_item_requires_explicit_positive_id(selector, capsys):
    namespace = runpy.run_path(str(REPO / "scripts/run_b1_deezer_acquisition.py"))
    assert namespace["main"](["--exact-item", *selector]) == 2
    assert "exact_item_requires_track_id" in capsys.readouterr().out
