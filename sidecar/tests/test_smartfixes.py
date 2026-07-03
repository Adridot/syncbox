"""Tests for the Smart Fixes fixed catalog and planner (SPEC-UNIFIED 5.11)."""

from syncbox.smartfixes import (
    collapse_whitespace,
    compose,
    fix_mojibake,
    plan,
    strip_trailing_url,
)


def test_strip_trailing_url():
    assert strip_trailing_url("Track - www.dj-leaks.example") == "Track"
    assert strip_trailing_url("Track (https://leak.example/x)") == "Track"
    assert strip_trailing_url("Track") == "Track"
    assert strip_trailing_url("Track - Remix") == "Track - Remix"  # not a URL


def test_collapse_whitespace():
    assert collapse_whitespace("KAROL G ") == "KAROL G"
    assert collapse_whitespace("El          Chojin") == "El Chojin"
    assert collapse_whitespace("A B") == "A B"  # NBSP
    assert collapse_whitespace(" ok ") == "ok"


def test_fix_mojibake_only_when_reversible_and_marked():
    assert fix_mojibake("CafÃ© del Mar") == "Café del Mar"
    assert fix_mojibake("Café del Mar") == "Café del Mar"  # already clean
    assert fix_mojibake("Plain ASCII") == "Plain ASCII"


def test_no_casing_fix_in_v1_catalog():
    # POC #9: 13 real all-caps stylizations would be destroyed by a naive fix.
    assert compose("title", "DAKITI") == "DAKITI"
    assert compose("title", "#SELFIE") == "#SELFIE"


def test_compose_is_idempotent_fixpoint():
    samples = [
        "SÃ¸ren  - www.leak.example",
        "  KAROL G ",
        "Track - www.x.example",
        "Café  del  Mar",
        "clean",
    ]
    for value in samples:
        once = compose("title", value)
        assert compose("title", once) == once


def test_composed_order_url_before_whitespace():
    # URL strip first, then whitespace cleanup composes to one final result
    assert compose("title", "Track   - www.leak.example") == "Track"


def make_row(content_id, title, artist="Artist", protected=False):
    return {
        "content_id": content_id,
        "title": title,
        "artist": artist,
        "protected": protected,
    }


def test_plan_emits_exact_payload_without_noops():
    payload, skipped = plan(
        [make_row("c1", "Track  x"), make_row("c2", "Clean Title")]
    )
    assert payload == [
        {"content_id": "c1", "field": "title", "before": "Track  x", "after": "Track x"}
    ]
    assert skipped == []


def test_plan_excludes_protected_by_default_and_names_them():
    payload, skipped = plan(
        [make_row("c1", "Dirty  Title", artist="KAROL G ", protected=True)]
    )
    assert payload == []
    assert skipped == [{"content_id": "c1", "name": "KAROL G  - Dirty  Title"}]


def test_protected_opt_in_is_per_call_only():
    rows = [make_row("c1", "Dirty  Title", protected=True)]
    payload, skipped = plan(rows, include_protected_ids={"c1"})
    assert len(payload) == 1 and skipped == []
    # next call without the opt-in: excluded again (never remembered)
    payload2, skipped2 = plan(rows)
    assert payload2 == [] and len(skipped2) == 1


def test_plan_handles_none_fields():
    payload, skipped = plan([make_row("c1", None, artist=None)])
    assert payload == [] and skipped == []
