"""Tests for dashboard readouts (SPEC-UNIFIED 11.3)."""

from datetime import datetime

from syncbox.readouts import (
    added_this_month,
    genre_distribution,
    keys_analyzed,
    never_played,
    quality_readout,
    to_camelot,
)


def test_camelot_mapping_and_enharmonics():
    assert to_camelot("Am") == "8A"
    assert to_camelot("C") == "8B"
    assert to_camelot("Dbm") == "12A"
    assert to_camelot("C#m") == "12A"
    assert to_camelot("G#m") == "1A"
    assert to_camelot("Abm") == "1A"
    assert to_camelot("F#") == "2B"


def test_camelot_passthrough_mixed_in_key_tags():
    assert to_camelot("8A") == "8A"
    assert to_camelot("12b") == "12B"
    assert to_camelot("4A") == "4A"  # real value measured in POC #5


def test_unmapped_keys_are_excluded():
    assert to_camelot("H") is None
    assert to_camelot("") is None
    assert to_camelot(None) is None
    assert to_camelot("13A") is None  # out of wheel range


def test_keys_analyzed_pct():
    rows = [{"key_name": "Am"}, {"key_name": "4A"}, {"key_name": None}, {"key_name": "?"}]
    assert keys_analyzed(rows) == {"total": 4, "analyzed": 2, "pct": 50}
    assert keys_analyzed([]) == {"total": 0, "analyzed": 0, "pct": 0}


def test_never_played_handles_varchar_counts():
    # pyrekordbox maps DJPlayCount as VARCHAR on some rows (poc/05 caveat 5)
    rows = [
        {"play_count": None},
        {"play_count": 0},
        {"play_count": "0"},
        {"play_count": "3"},
        {"play_count": 5},
    ]
    assert never_played(rows) == 3


def test_added_this_month_and_last_import():
    now = datetime(2026, 7, 3, 1, 0)
    rows = [
        {"date_created": "2026-07-01 10:00:00 +00:00"},
        {"date_created": "2026-06-28"},
        {"date_created": datetime(2026, 7, 2, 12, 0)},
        {"date_created": None},
        {"date_created": "garbage"},
    ]
    out = added_this_month(rows, now)
    assert out["added_this_month"] == 2
    assert out["last_import"].startswith("2026-07-02")


def test_genre_distribution_top():
    rows = [{"genre": "House"}, {"genre": "House"}, {"genre": "Techno"}, {"genre": None}]
    assert genre_distribution(rows) == [
        {"genre": "House", "count": 2},
        {"genre": "Techno", "count": 1},
    ]


def test_quality_readout_speaks_badge_vocabulary():
    rows = [
        {"quality_verdict": "lossy_source_probable"},
        {"quality_verdict": "incertain"},
        {"quality_verdict": "ok"},
        {},  # verdict absent -> neutral ok
    ]
    assert quality_readout(rows) == {
        "lossy_source_probable": 1,
        "incertain": 1,
        "ok": 2,
    }
