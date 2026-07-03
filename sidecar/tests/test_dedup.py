"""Tests for duplicate grouping and the D6 explainable keeper (SPEC-01 2.2)."""

from syncbox.dedup import (
    DURATION_TOLERANCE_MS,
    FUZZY_CONFIDENCE,
    FUZZY_THRESHOLD,
    FUZZY_THRESHOLD_NO_DURATION,
    ISRC_CONFIDENCE,
    ISRC_DIVERGENT_CONFIDENCE,
    bitrate_bucket,
    choose_keeper,
    find_duplicate_groups,
)


def track(content_id, title, artist, duration_ms=200_000, isrc=None):
    return {
        "content_id": content_id,
        "title": title,
        "artist": artist,
        "duration_ms": duration_ms,
        "isrc": isrc,
    }


# --- grouping -----------------------------------------------------------------


def test_isrc_group_coherent_titles_99():
    groups = find_duplicate_groups(
        [
            track("a", "Strobe", "deadmau5", isrc=" usrc123 "),
            track("b", "Strobe (Original Mix)", "deadmau5", isrc="USRC123"),
            track("c", "Levels", "Avicii", isrc="OTHER1"),
        ]
    )
    assert len(groups) == 1
    group = groups[0]
    assert group.key == "a|b"
    assert group.confidence == ISRC_CONFIDENCE == 99
    assert group.method == "isrc"
    assert group.warning is False


def test_isrc_group_divergent_titles_60_with_warning():
    groups = find_duplicate_groups(
        [
            track("a", "Strobe", "deadmau5", isrc="X1"),
            track("b", "Some Totally Different Song", "Someone Else", isrc="X1"),
        ]
    )
    assert groups[0].confidence == ISRC_DIVERGENT_CONFIDENCE == 60
    assert groups[0].warning is True  # excluded from bulk resolution


def test_fuzzy_group_confidence_80_within_duration_tolerance():
    groups = find_duplicate_groups(
        [
            track("a", "Strobe", "deadmau5", duration_ms=200_000),
            track("b", "Strobe", "deadmau5", duration_ms=200_000 + DURATION_TOLERANCE_MS),
        ]
    )
    assert len(groups) == 1
    assert groups[0].confidence == FUZZY_CONFIDENCE == 80
    assert groups[0].method == "fuzzy"


def test_fuzzy_no_group_beyond_duration_tolerance():
    groups = find_duplicate_groups(
        [
            track("a", "Strobe", "deadmau5", duration_ms=200_000),
            track("b", "Strobe", "deadmau5", duration_ms=203_000),
        ]
    )
    assert groups == []


def test_unknown_duration_uses_stricter_threshold():
    assert FUZZY_THRESHOLD == 0.87 and FUZZY_THRESHOLD_NO_DURATION == 0.93
    # identical signatures pass even at 0.93
    groups = find_duplicate_groups(
        [
            track("a", "Strobe", "deadmau5", duration_ms=None),
            track("b", "Strobe", "deadmau5", duration_ms=200_000),
        ]
    )
    assert len(groups) == 1
    # mildly similar signatures that pass 0.87 but not 0.93 stay separate
    # when a duration is unknown
    groups = find_duplicate_groups(
        [
            track("a", "Strobe Club Edit Version", "deadmau5", duration_ms=None),
            track("b", "Strobe Club Edit", "deadmau5", duration_ms=200_000),
        ]
    )
    assert all(g.method != "fuzzy" or len(g.content_ids) < 2 for g in groups) or groups == []


def test_dismissed_groups_are_dropped_idempotently():
    tracks = [
        track("a", "Strobe", "deadmau5", isrc="X1"),
        track("b", "Strobe", "deadmau5", isrc="X1"),
    ]
    assert find_duplicate_groups(tracks, dismissed={"a|b"}) == []
    assert find_duplicate_groups(tracks, dismissed={"a|b", "a|b"}) == []  # idempotent


def test_isrc_members_not_regrouped_by_fuzzy():
    groups = find_duplicate_groups(
        [
            track("a", "Strobe", "deadmau5", isrc="X1"),
            track("b", "Strobe", "deadmau5", isrc="X1"),
        ]
    )
    assert [g.method for g in groups] == ["isrc"]


# --- keeper D6 ----------------------------------------------------------------


def keeper_track(content_id, **kw):
    base = {
        "content_id": content_id,
        "protected": False,
        "file_missing": False,
        "bit_rate": 320,
        "quality_verdict": "ok",
        "date_created_order": 100,
    }
    base.update(kw)
    return base


def test_protected_always_wins():
    keeper, reason = choose_keeper(
        [
            keeper_track("a", bit_rate=128, protected=True),
            keeper_track("b", bit_rate=320),
        ]
    )
    assert keeper["content_id"] == "a"
    assert reason == "protected"


def test_present_file_beats_missing():
    keeper, reason = choose_keeper(
        [
            keeper_track("a", file_missing=True, bit_rate=320),
            keeper_track("b", bit_rate=128),
        ]
    )
    assert keeper["content_id"] == "b"
    assert reason == "file_present"


def test_bitrate_bucket_no_lossless_preference():
    # FLAC 1411 and MP3 320 share the top tier (D6: lossless preference removed)
    assert bitrate_bucket(1411) == bitrate_bucket(320) == 4
    assert bitrate_bucket(256) == 3
    assert bitrate_bucket(192) == 2
    assert bitrate_bucket(128) == 1
    assert bitrate_bucket(96) == 0
    assert bitrate_bucket(None) == 0


def test_quality_bucket_decides():
    keeper, reason = choose_keeper(
        [keeper_track("a", bit_rate=192), keeper_track("b", bit_rate=320)]
    )
    assert keeper["content_id"] == "b"
    assert reason == "quality"


def test_a3_verdict_primes_over_declared_bitrate():
    # fake-FLAC: declared 1411 but flagged lossy -> loses to a genuine 320
    keeper, reason = choose_keeper(
        [
            keeper_track("fake", bit_rate=1411, quality_verdict="lossy_source_probable"),
            keeper_track("real", bit_rate=320),
        ]
    )
    assert keeper["content_id"] == "real"
    assert reason == "quality"


def test_incertain_is_neutral_never_a_penalty():
    # 'incertain' ties with 'ok' at the quality criterion -> falls to date
    keeper, reason = choose_keeper(
        [
            keeper_track("a", quality_verdict="incertain", date_created_order=50),
            keeper_track("b", quality_verdict="ok", date_created_order=100),
        ]
    )
    assert keeper["content_id"] == "a"  # older wins; verdict did not demote
    assert reason == "date"


def test_flagged_vs_flagged_falls_back_to_bucket():
    keeper, _ = choose_keeper(
        [
            keeper_track("a", bit_rate=320, quality_verdict="lossy_source_probable"),
            keeper_track("b", bit_rate=192, quality_verdict="lossy_source_probable"),
        ]
    )
    assert keeper["content_id"] == "a"


def test_deterministic_on_full_tie():
    tracks = [keeper_track("b"), keeper_track("a")]
    keeper1, reason = choose_keeper(tracks)
    keeper2, _ = choose_keeper(list(reversed(tracks)))
    assert keeper1["content_id"] == keeper2["content_id"]
    assert reason == "identical"
