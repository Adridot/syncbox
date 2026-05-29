from app.matching import match_spotify_track, normalize_text
from app.models import RekordboxTrack, SpotifyTrack


def test_normalize_text_removes_accents_and_brackets() -> None:
    assert normalize_text("C'est La Vie (Extended Mix)") == "c est la vie"


def test_match_by_isrc_wins() -> None:
    spotify = SpotifyTrack(
        id="sp1",
        uri="spotify:track:sp1",
        title="Different Title",
        artists=["Artist"],
        durationMs=180000,
        isrc="FR1234567890",
    )
    rekordbox = [
        RekordboxTrack(
            contentId="rb1",
            title="Original Title",
            artist="Artist",
            durationMs=181000,
            isrc="FR1234567890",
        )
    ]

    result = match_spotify_track(spotify, rekordbox)

    assert result.status == "matched"
    assert result.method == "isrc"
    assert result.rekordbox_content_id == "rb1"
    assert result.confidence == 100


def test_metadata_ambiguous_when_candidates_are_too_close() -> None:
    spotify = SpotifyTrack(
        id="sp1",
        uri="spotify:track:sp1",
        title="One More Time",
        artists=["Daft Punk"],
        durationMs=320000,
    )
    rekordbox = [
        RekordboxTrack(
            contentId="rb1",
            title="One More Time",
            artist="Daft Punk",
            durationMs=320500,
        ),
        RekordboxTrack(
            contentId="rb2",
            title="One More Time",
            artist="Daft Punk",
            durationMs=320700,
        ),
    ]

    result = match_spotify_track(spotify, rekordbox)

    assert result.status == "ambiguous"
    assert result.method == "metadata"


def test_missing_when_score_is_low() -> None:
    spotify = SpotifyTrack(
        id="sp1",
        uri="spotify:track:sp1",
        title="House Track",
        artists=["Known Artist"],
        durationMs=180000,
    )
    rekordbox = [
        RekordboxTrack(
            contentId="rb1",
            title="Rock Ballad",
            artist="Other Artist",
            durationMs=260000,
        )
    ]

    result = match_spotify_track(spotify, rekordbox)

    assert result.status == "missing"

