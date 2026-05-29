from app.spotify import (
    parse_playlist_id,
    parse_track_id,
    playlist_items_to_tracks,
    summarize_playlist_page,
    track_payload_to_spotify_track,
)


def test_parse_track_id_from_url() -> None:
    assert parse_track_id("https://open.spotify.com/track/abc123?si=xyz") == "abc123"


def test_parse_track_id_from_uri_and_raw() -> None:
    assert parse_track_id("spotify:track:abc123") == "abc123"
    assert parse_track_id("abc123") == "abc123"


def test_track_payload_to_spotify_track_valid() -> None:
    track = track_payload_to_spotify_track(
        {
            "id": "t1",
            "uri": "spotify:track:t1",
            "name": "Song",
            "artists": [{"name": "Artist A"}, {"name": "Artist B"}],
            "duration_ms": 200000,
            "external_ids": {"isrc": "USRC11111111"},
            "type": "track",
        }
    )
    assert track is not None
    assert track.id == "t1"
    assert track.artists == ["Artist A", "Artist B"]
    assert track.isrc == "USRC11111111"


def test_track_payload_to_spotify_track_rejects_local_and_missing() -> None:
    assert track_payload_to_spotify_track({"id": "x", "uri": "u", "is_local": True}) is None
    assert track_payload_to_spotify_track({"id": None, "uri": None}) is None
    assert track_payload_to_spotify_track({"type": "episode", "id": "e", "uri": "u"}) is None


def test_parse_playlist_id_from_url() -> None:
    playlist_id = parse_playlist_id(
        "https://open.spotify.com/playlist/abc123?si=tracking"
    )

    assert playlist_id == "abc123"


def test_parse_playlist_id_from_uri() -> None:
    assert parse_playlist_id("spotify:playlist:abc123") == "abc123"


def test_summarize_playlist_page_prefers_items_total() -> None:
    page = summarize_playlist_page(
        {
            "limit": 50,
            "offset": 0,
            "total": 1,
            "next": None,
            "items": [
                {
                    "id": "playlist-id",
                    "name": "Client Dinner",
                    "owner": {"display_name": "Adrien"},
                    "items": {"total": 42},
                    "tracks": {"total": 7},
                    "public": False,
                    "snapshot_id": "snapshot",
                    "images": [{"url": "https://images.example/cover.jpg"}],
                    "external_urls": {
                        "spotify": "https://open.spotify.com/playlist/playlist-id"
                    },
                }
            ],
        }
    )

    assert page["items"][0]["trackCount"] == 42
    assert page["items"][0]["name"] == "Client Dinner"
    assert page["items"][0]["imageUrl"] == "https://images.example/cover.jpg"
    assert page["nextOffset"] is None


def test_playlist_items_to_tracks_skips_local_items() -> None:
    tracks = playlist_items_to_tracks(
        [
            {
                "track": {
                    "id": "track-1",
                    "uri": "spotify:track:track-1",
                    "name": "Track",
                    "artists": [{"name": "Artist"}],
                    "duration_ms": 180000,
                    "external_ids": {"isrc": "USRC17607839"},
                    "is_local": False,
                    "type": "track",
                }
            },
            {
                "track": {
                    "id": None,
                    "uri": None,
                    "name": "Local",
                    "artists": [],
                    "duration_ms": 180000,
                    "is_local": True,
                    "type": "track",
                }
            },
        ]
    )

    assert len(tracks) == 1
    assert tracks[0].isrc == "USRC17607839"
