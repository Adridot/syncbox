from pathlib import Path

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
