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


def test_isrc_match_rejected_when_durations_differ_wildly() -> None:
    # Real-world bug: Spotify "Alicante" (3:13) carried the same ISRC as the
    # Rekordbox track "Le Sang de la veine" (4:30). Different songs, so the
    # blind ISRC match must be refused and fall through to metadata (-> missing).
    spotify = SpotifyTrack(
        id="sp1",
        uri="spotify:track:sp1",
        title="Alicante",
        artists=["Gambino"],
        durationMs=193777,
        isrc="TCACT1688684",
    )
    rekordbox = [
        RekordboxTrack(
            contentId="rb1",
            title="Le Sang de la veine",
            artist="Gambino",
            durationMs=270000,
            isrc="TCACT1688684",
        )
    ]

    result = match_spotify_track(spotify, rekordbox)

    assert result.method != "isrc"
    assert result.status == "missing"


def test_isrc_match_kept_when_same_title_different_duration() -> None:
    # Real case: Spotify "Peña Baiona" (Harmonie Bayonnaise, 5:07) shares the
    # ISRC of the Rekordbox "Peña Baiona" (Marc Lartigau, 4:11). Same song,
    # different edit -> must still match despite the 56s gap and different artist.
    spotify = SpotifyTrack(
        id="sp1",
        uri="spotify:track:sp1",
        title="Peña Baiona",
        artists=["Harmonie Bayonnaise", "Les Socios", "Irrintzina"],
        durationMs=307160,
        isrc="FRZ510300044",
    )
    rekordbox = [
        RekordboxTrack(
            contentId="rb1",
            title="Peña Baiona",
            artist="Marc Lartigau",
            durationMs=251000,
            isrc="FRZ510300044",
        )
    ]

    result = match_spotify_track(spotify, rekordbox)

    assert result.status == "matched"
    assert result.method == "isrc"
    assert result.rekordbox_content_id == "rb1"


def test_isrc_match_kept_when_duration_unknown() -> None:
    spotify = SpotifyTrack(
        id="sp1",
        uri="spotify:track:sp1",
        title="Whatever",
        artists=["Artist"],
        durationMs=200000,
        isrc="FR1234567890",
    )
    rekordbox = [
        RekordboxTrack(
            contentId="rb1",
            title="Whatever",
            artist="Artist",
            durationMs=None,
            isrc="FR1234567890",
        )
    ]

    result = match_spotify_track(spotify, rekordbox)

    assert result.status == "matched"
    assert result.method == "isrc"


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

