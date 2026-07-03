"""Tests for untagged categorization (SPEC-UNIFIED 5.8, SPEC-01 2.4, D7)."""

from syncbox.untagged import base_title, categorize, is_junk, song_key


def track(title, artist="deadmau5"):
    return {"title": title, "artist": artist}


# --- junk: universal structural rules + user patterns ---------------------------


def test_structural_junk_rules():
    assert is_junk(track("spotify:track:4uLU6hMCjMI75M1A2tKUQC"))
    assert is_junk(track(""))
    assert is_junk(track("   "))
    assert is_junk(track("Real Title", artist="rekordbox"))
    assert is_junk(track("Real Title", artist="ReKordBox"))
    assert not is_junk(track("Strobe"))


def test_user_configurable_patterns():
    assert is_junk(track("Strobe [PREVIEW]"), user_patterns=[r"\[preview\]"])
    assert not is_junk(track("Strobe"), user_patterns=[r"\[preview\]"])


# --- D7 keys --------------------------------------------------------------------


def test_song_key_keeps_full_artist_b5():
    key = song_key("Artist A & Artist B", "Song")
    assert key == ("artist a and artist b", "song")  # never just 'artist'


def test_base_title_cuts_feat_non_greedily_b7():
    assert base_title("Song feat. Somebody") == "song"
    assert base_title("Song featuring Somebody Else") == "song"
    # 'defeat' must not trigger the feat cut
    assert base_title("Defeat of the Empire") == "defeat of the empire"


# --- categories ----------------------------------------------------------------


TAGGED = [track("Strobe"), track("Ghosts n Stuff", artist="deadmau5")]


def test_dup_of_tagged_when_keys_match():
    out = categorize([track("Strobe")], TAGGED)
    assert out[0]["category"] == "dup_of_tagged"


def test_parenthesized_qualifier_is_dup_via_d19():
    # D19 strips parens content, so '(Extended Mix)' collapses to the same key
    out = categorize([track("Strobe (Extended Mix)")], TAGGED)
    assert out[0]["category"] == "dup_of_tagged"


def test_alt_version_when_base_matches_but_key_differs():
    out = categorize([track("Strobe feat. Somebody")], TAGGED)
    assert out[0]["category"] == "alt_version"


def test_different_artist_is_not_dup_b5():
    out = categorize([track("Strobe", artist="Someone Else")], TAGGED)
    assert out[0]["category"] == "review"


def test_sort_order_junk_dup_alt_review_then_artist_title():
    out = categorize(
        [
            track("Zebra Song", artist="zz"),  # review
            track("Strobe feat. X"),  # alt_version
            track("Strobe"),  # dup_of_tagged
            track("spotify:track:abc"),  # junk
            track("Aardvark Song", artist="aa"),  # review (before zebra)
        ],
        TAGGED,
    )
    assert [t["category"] for t in out] == [
        "junk",
        "dup_of_tagged",
        "alt_version",
        "review",
        "review",
    ]
    assert out[3]["title"] == "Aardvark Song"
