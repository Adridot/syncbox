from app.maintenance import (
    parse_leading_artist,
    ACTION_DELETE,
    ACTION_KEEP,
    REASON_ALT_VERSION,
    REASON_DUP_OF_TAGGED,
    REASON_JUNK,
    REASON_UNIQUE_MAINSTREAM,
    TrackRow,
    classify_untagged,
    is_junk,
    normalize_title,
    select_base_index,
    song_key,
    summarize,
)


def track(content_id, artist, title, folder_path="/Music/x.mp3", is_tagged=False):
    return TrackRow(
        content_id=content_id,
        artist=artist,
        title=title,
        folder_path=folder_path,
        is_tagged=is_tagged,
    )


# --- normalization ---------------------------------------------------------


def test_normalize_title_drops_version_qualifiers_and_parentheticals():
    assert normalize_title("Titanium (feat. Sia)") == "titanium"
    assert normalize_title("Don't Stop Me Now (Remastered 2011)") == "don t stop me now"
    assert normalize_title("Levels (Radio Edit)") == "levels"


def test_song_key_ignores_accents_and_secondary_artists():
    assert song_key("Claude François", "Cette année-là") == song_key(
        "claude francois", "Cette annee-la"
    )


# --- junk detection --------------------------------------------------------


def test_is_junk_flags_spotify_placeholder_rows():
    assert is_junk("", "", "spotify:track:05OmZz1tixVBtXMx3cb4oc") is True


def test_is_junk_flags_rekordbox_samples_and_sfx():
    assert is_junk("rekordbox", "Breaks 1", "/Users/x/Music/rekordbox/breaks1.mp3") is True
    assert is_junk("", "reveil (4s)", "/Users/x/Music/reveil.mp3") is True
    assert is_junk("", "Discours frères soeurs mariée", "/Users/x/d.mp3") is True


def test_is_junk_keeps_real_music():
    assert is_junk("ABBA", "Dancing Queen", "/Users/x/Music/abba.mp3") is False


# --- classification --------------------------------------------------------


def test_dup_of_tagged_is_deleted_with_matched_title():
    tagged = [track("1", "ABBA", "Dancing Queen", is_tagged=True)]
    untagged = [track("2", "ABBA", "Dancing Queen (Radio Edit)")]
    [decision] = classify_untagged(tagged, untagged)
    assert decision.action == ACTION_DELETE
    assert decision.reason == REASON_DUP_OF_TAGGED
    assert decision.matched_tagged_title == "Dancing Queen"


def test_unique_mainstream_is_kept():
    untagged = [track("2", "Walk The Moon", "Shut Up and Dance")]
    [decision] = classify_untagged([], untagged)
    assert decision.action == ACTION_KEEP
    assert decision.reason == REASON_UNIQUE_MAINSTREAM


def test_alt_versions_keep_one_base_and_delete_the_rest():
    untagged = [
        track("a", "Gigi D'Agostino", "L'Amour Toujours (Hardstyle Remix)"),
        track("b", "Gigi D'Agostino", "L'Amour Toujours"),
        track("c", "Gigi D'Agostino", "L'Amour Toujours (Extended Mix)"),
    ]
    decisions = {d.content_id: d for d in classify_untagged([], untagged)}
    assert decisions["b"].action == ACTION_KEEP
    assert decisions["b"].reason == REASON_UNIQUE_MAINSTREAM
    assert decisions["a"].action == ACTION_DELETE
    assert decisions["a"].reason == REASON_ALT_VERSION
    assert decisions["c"].action == ACTION_DELETE


def test_select_base_index_prefers_cleanest_title():
    rows = [
        track("a", "X", "Song (Remix)"),
        track("b", "X", "Song"),
    ]
    assert select_base_index(rows) == 1


def test_junk_is_never_kept_and_summary_counts_match():
    untagged = [
        track("j", "", "", folder_path="spotify:track:abc"),
        track("k", "Queen", "Don't Stop Me Now"),
    ]
    decisions = classify_untagged([], untagged)
    junk = [d for d in decisions if d.content_id == "j"][0]
    assert junk.action == ACTION_DELETE
    assert junk.reason == REASON_JUNK

    counts = summarize(decisions)
    assert counts.get(ACTION_DELETE, 0) == 1
    assert counts.get(ACTION_KEEP, 0) == 1
    assert counts.get(REASON_UNIQUE_MAINSTREAM, 0) == 1


def test_parse_leading_artist():
    assert parse_leading_artist("Maitre Gims - Zombie (Dj Last One)") == "Maitre Gims"
    assert parse_leading_artist("50 Cent - P.I.M.P. (Electro Remix)") == "50 Cent"
    # no separator -> cannot determine
    assert parse_leading_artist("Amare") == ""
    assert parse_leading_artist("Et je suis pas venu ici pour souffrir ok !") == ""
    # only splits when both sides are non-empty
    assert parse_leading_artist("Artist - ") == ""
    # first separator wins
    assert parse_leading_artist("A - B - C") == "A"


def test_no_decision_is_dropped():
    untagged = [track(str(i), "Artist", f"Song {i}") for i in range(5)]
    decisions = classify_untagged([], untagged)
    assert {d.content_id for d in decisions} == {str(i) for i in range(5)}
