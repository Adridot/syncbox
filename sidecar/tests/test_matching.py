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
