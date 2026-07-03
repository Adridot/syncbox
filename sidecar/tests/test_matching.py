"""Tests for the D19 pipeline and ISRC+fuzzy matching (SPEC-01 2.1)."""

import pytest

from syncbox.matching import (
    AMBIGUITY_MARGIN,
    MIN_CONFIDENCE,
    WEIGHT_ARTIST,
    WEIGHT_DURATION,
    WEIGHT_TITLE,
    duration_score,
    fuzzy_confidence,
    match,
    normalize,
)


def rb(content_id, title, artist, duration_ms=200_000, isrc=None):
    return {
        "content_id": content_id,
        "title": title,
        "artist": artist,
        "duration_ms": duration_ms,
        "isrc": isrc,
    }


def sp(title, artist, duration_ms=200_000, isrc=None):
    return {"title": title, "artist": artist, "duration_ms": duration_ms, "isrc": isrc}


# --- D19 normalization --------------------------------------------------------


def test_normalize_pipeline():
    assert normalize("Rüfüs Du Sol") == "rufus du sol"
    assert normalize("Innerbloom (Frankey & Sandrino Remix)") == "innerbloom"
    assert normalize("Above & Beyond") == "above and beyond"
    assert normalize("Track [Extended Mix]") == "track"
    assert normalize("  Spaced   out !! ") == "spaced out"
    assert normalize(None) == ""


def test_weights_sum_to_one():
    assert WEIGHT_TITLE + WEIGHT_ARTIST + WEIGHT_DURATION == pytest.approx(1.0)
    assert (WEIGHT_TITLE, WEIGHT_ARTIST, WEIGHT_DURATION) == (0.52, 0.36, 0.12)


def test_duration_buckets_exact():
    assert duration_score(0) == 100
    assert duration_score(1500) == 100
    assert duration_score(1501) == 80
    assert duration_score(5000) == 80
    assert duration_score(5001) == 55
    assert duration_score(12000) == 55
    assert duration_score(12001) == 0
    assert duration_score(-1400) == 100  # absolute delta


# --- ISRC first ---------------------------------------------------------------


def test_isrc_exact_wins_with_confidence_100():
    result = match(
        sp("Totally Different Name", "Other Artist", isrc="usrc17607839"),
        [rb("c1", "Strobe", "deadmau5", isrc="USRC17607839")],
    )
    assert (result.status, result.method, result.confidence) == ("matched", "isrc", 100)
    assert result.content_id == "c1"


def test_isrc_collision_needs_both_duration_and_title_disagreement():
    # duration off by >15s BUT title agrees -> ISRC still wins
    ok_title = match(
        sp("Strobe", "deadmau5", duration_ms=300_000, isrc="X1"),
        [rb("c1", "Strobe", "deadmau5", duration_ms=200_000, isrc="X1")],
    )
    assert ok_title.method == "isrc"
    # title disagrees BUT duration close -> ISRC still wins
    ok_duration = match(
        sp("Completely Other", "Someone", duration_ms=200_500, isrc="X1"),
        [rb("c1", "Strobe", "deadmau5", duration_ms=200_000, isrc="X1")],
    )
    assert ok_duration.method == "isrc"
    # both disagree -> ISRC rejected, falls through (here: missing)
    rejected = match(
        sp("Completely Other", "Someone", duration_ms=300_000, isrc="X1"),
        [rb("c1", "Strobe", "deadmau5", duration_ms=200_000, isrc="X1")],
    )
    assert rejected.method != "isrc"


def test_isrc_missing_duration_means_blind_trust():
    result = match(
        sp("Completely Other", "Someone", duration_ms=0, isrc="X1"),
        [rb("c1", "Strobe", "deadmau5", duration_ms=200_000, isrc="X1")],
    )
    assert result.method == "isrc"


# --- fuzzy --------------------------------------------------------------------


def test_fuzzy_match_above_threshold():
    result = match(
        sp("Strobe", "deadmau5"),
        [rb("c1", "Strobe (Original Mix)", "deadmau5"), rb("c2", "Ghosts", "deadmau5")],
    )
    assert result.status == "matched"
    assert result.content_id == "c1"
    assert result.method == "fuzzy"
    assert result.confidence >= MIN_CONFIDENCE


def test_below_threshold_is_missing_with_zero_confidence():
    result = match(sp("Strobe", "deadmau5"), [rb("c1", "Levels", "Avicii")])
    assert (result.status, result.content_id, result.confidence) == ("missing", None, 0)


def test_no_candidates_is_missing():
    assert match(sp("Strobe", "deadmau5"), []).status == "missing"


def test_ambiguity_margin_returns_best_anyway():
    twins = [
        rb("c1", "Strobe", "deadmau5", duration_ms=200_000),
        rb("c2", "Strobe", "deadmau5", duration_ms=200_100),
    ]
    result = match(sp("Strobe", "deadmau5", duration_ms=200_000), twins)
    assert result.status == "ambiguous"
    assert result.content_id == "c1"  # best is still returned (SPEC-01 2.1)
    assert result.method == "fuzzy"


def test_fuzzy_confidence_is_weighted_sum():
    track = sp("Strobe", "deadmau5", duration_ms=200_000)
    candidate = rb("c1", "Strobe", "deadmau5", duration_ms=200_000)
    assert fuzzy_confidence(track, candidate) == round(
        100 * WEIGHT_TITLE + 100 * WEIGHT_ARTIST + 100 * WEIGHT_DURATION
    )
    # unknown duration contributes 0, not an error
    assert fuzzy_confidence(
        sp("Strobe", "deadmau5", duration_ms=0), candidate
    ) == round(100 * WEIGHT_TITLE + 100 * WEIGHT_ARTIST)


def test_thresholds_are_parameters_but_default_to_spec():
    assert MIN_CONFIDENCE == 82
    assert AMBIGUITY_MARGIN == 6
    twins = [
        rb("c1", "Strobe", "deadmau5"),
        rb("c2", "Strobe", "deadmau5"),
    ]
    # margin 0: no ambiguity possible
    result = match(sp("Strobe", "deadmau5"), twins, ambiguity_margin=0)
    assert result.status == "matched"


# --- G4: policy / weights / candidate scoring (M4.2) ---------------------------


def test_isrc_policy_trust_isrc_never_rejects():
    from syncbox.matching import ISRC_COLLISION_POLICIES

    assert ISRC_COLLISION_POLICIES == ("guarded", "trust_isrc", "strict")
    # both duration and title disagree: guarded rejects, trust_isrc keeps
    colliding = sp("Completely Other", "Someone", duration_ms=300_000, isrc="X1")
    candidate = [rb("c1", "Strobe", "deadmau5", duration_ms=200_000, isrc="X1")]
    assert match(colliding, candidate).method != "isrc"
    trusted = match(colliding, candidate, isrc_collision_policy="trust_isrc")
    assert (trusted.method, trusted.confidence) == ("isrc", 100)


def test_isrc_policy_strict_rejects_on_either_disagreement():
    candidate = [rb("c1", "Strobe", "deadmau5", duration_ms=200_000, isrc="X1")]
    # duration off alone: guarded keeps, strict rejects
    duration_off = sp("Strobe", "deadmau5", duration_ms=300_000, isrc="X1")
    assert match(duration_off, candidate).method == "isrc"
    assert match(duration_off, candidate, isrc_collision_policy="strict").method != "isrc"
    # title off alone: guarded keeps, strict rejects
    title_off = sp("Completely Other", "Someone", duration_ms=200_500, isrc="X1")
    assert match(title_off, candidate).method == "isrc"
    assert match(title_off, candidate, isrc_collision_policy="strict").method != "isrc"
    # strict with missing duration: title alone decides
    no_duration_bad_title = sp("Completely Other", "Someone", duration_ms=0, isrc="X1")
    assert match(no_duration_bad_title, candidate, isrc_collision_policy="strict").method != "isrc"
    no_duration_good_title = sp("Strobe", "deadmau5", duration_ms=0, isrc="X1")
    assert match(no_duration_good_title, candidate, isrc_collision_policy="strict").method == "isrc"


def test_custom_weights_change_the_verdict():
    # title matches, artist does not: default weights fail the threshold,
    # title-only weights pass it (proves weights are consumed, G4)
    track = sp("Strobe", "Someone Else", duration_ms=0)
    candidate = [rb("c1", "Strobe", "deadmau5", duration_ms=0)]
    assert match(track, candidate).status == "missing"
    weighted = match(
        track, candidate, weights={"title": 1.0, "artist": 0.0, "duration": 0.0}
    )
    assert weighted.status == "matched"
    assert weighted.confidence == 100


def test_score_candidates_pins_isrc_and_sorts_best_first():
    from syncbox.matching import score_candidates

    track = sp("Strobe", "deadmau5", isrc="X1")
    scored = score_candidates(
        track,
        [
            rb("far", "Ghosts n Stuff", "Someone"),
            rb("close", "Strobe (Club Edit)", "deadmau5"),
            rb("exact", "Whatever Name", "Whoever", isrc="x1"),  # ISRC, case-insensitive
        ],
    )
    confidences = [confidence for confidence, _ in scored]
    assert confidences == sorted(confidences, reverse=True)
    assert scored[0][1]["content_id"] == "exact"
    assert scored[0][0] == 100
    # colliding ISRC candidate is NOT pinned (falls back to its fuzzy score)
    colliding = score_candidates(
        sp("Completely Other", "Someone", duration_ms=300_000, isrc="X1"),
        [rb("exact", "Strobe", "deadmau5", duration_ms=200_000, isrc="X1")],
    )
    assert colliding[0][0] < 100
