"""Tests for the conservative Smart Fixes catalog and exact planner."""

import pytest

from syncbox import smartfixes_run
from syncbox.safety import process_guard
from syncbox.safety.mutate import fingerprint
from syncbox.smartfixes import (
    collapse_whitespace,
    compose,
    decode_entities,
    extract_featured_artist,
    extract_remixer,
    fix_mojibake,
    plan,
    strip_trailing_url,
)


def make_row(
    content_id,
    title,
    artist="Artist",
    remixer=None,
    ownership="external",
):
    return {
        "content_id": content_id,
        "title": title,
        "artist": artist,
        "remixer": remixer,
        "ownership": ownership,
    }


def test_exact_xml_entities_only():
    assert decode_entities("Rock &amp; Roll &quot;Live&quot;") == 'Rock & Roll "Live"'
    assert decode_entities("Rock &amp;amp; Roll") == "Rock & Roll"
    assert decode_entities("AT&ampT &#38; &copy;") == "AT&ampT &#38; &copy;"


def test_unicode_whitespace_and_nfc_without_compatibility_folding():
    assert collapse_whitespace("\u00a0Cafe\u0301\u2009\u2009del\u202fMar ") == "Café del Mar"
    assert collapse_whitespace("\ufeffTitle") == "Title"
    assert collapse_whitespace("① ＦＵＬＬ ﬁ") == "① ＦＵＬＬ ﬁ"
    assert collapse_whitespace("A\u200dB") == "A\u200dB"


def test_trailing_url_requires_a_separator_or_wrapper_and_keeps_nonempty_values():
    assert strip_trailing_url("Track - www.pool.example/x") == "Track"
    assert strip_trailing_url("Track (https://pool.example/x)") == "Track"
    assert strip_trailing_url("Track [pool.example]") == "Track"
    assert strip_trailing_url("Track - www.a.example - www.b.example") == "Track"
    assert strip_trailing_url("Track (www.a.example) [www.b.example]") == "Track"
    assert strip_trailing_url("https://example.com") == "https://example.com"
    assert strip_trailing_url("Song about www.example.com") == "Song about www.example.com"
    assert strip_trailing_url("Track - example.com") == "Track - example.com"
    assert strip_trailing_url("Track -") == "Track -"
    assert strip_trailing_url("AC|DC |") == "AC|DC |"


def test_mojibake_repairs_latin1_cp1252_and_double_encoding_to_a_fixpoint():
    assert fix_mojibake("CafÃ© del Mar") == "Café del Mar"
    assert fix_mojibake("Itâ€™s") == "It’s"
    assert fix_mojibake("CafÃƒÂ©") == "Café"
    assert fix_mojibake("Rock â€“ Roll") == "Rock – Roll"


def test_mojibake_leaves_unprovable_or_already_clean_text_unchanged():
    for value in (
        "Ãngela",
        "AHÅ™, the new sofa from IKEA®",
        "Caf�",
        "ÐŸÑ€Ð¸Ð²ÐµÑ‚",
        "æ—¥æœ¬èªž",
        "Î‘Î¸Î®Î½Î±",
        "Plain ASCII",
    ):
        assert fix_mojibake(value) == value


def test_featured_artist_moves_only_one_explicit_terminal_credit():
    assert extract_featured_artist("Umbrella (FEAT. Jay‐Z)", "Rihanna") == (
        "Umbrella",
        "Rihanna feat. Jay‐Z",
    )
    assert extract_featured_artist("Song [ft. eMOTIVe]", "Main") == (
        "Song",
        "Main feat. eMOTIVe",
    )
    assert extract_featured_artist(
        "Song - (featuring Guest) (Known Remix)", "Main"
    ) == ("Song (Known Remix)", "Main featuring Guest")
    assert extract_featured_artist(
        "Song (www.pool.example) (feat. Guest)", "Main"
    ) == ("Song", "Main feat. Guest")


def test_featured_artist_counterexamples_are_noops():
    samples = (
        ("A feat. of Strength", "Main"),
        ("Song (feat. Guest) Live", "Main"),
        ("Song (feat. A) (feat. B)", "Main"),
        ("Song (feat. Guest (Live))", "Main"),
        ("Song [feat. Guest (Live)]", "Main"),
        ("Song (feat. Guest [Live])", "Main"),
        ("Song (Live (feat. Guest)", "Main"),
        ("Song (feat. Guest)", "Main feat. Other"),
        ("Song (feat. Guest)", "Main (feat. Existing)"),
        ("Song (with Guest)", "Main"),
        ("Song (feat. Guest)", None),
        ("Song (feat. Guest)", "A" * 250),
        ("- (feat. Guest)", "Main"),
        ("| (feat. Guest)", "Main"),
        ("Song (feat. Guest)", "Guest"),
    )
    for title, artist in samples:
        assert extract_featured_artist(title, artist) == (title, artist)


def test_remixer_is_fill_only_known_and_never_changes_the_title():
    known = ["Purple Disco Machine", "Culture Club"]
    title = "At Night (purple disco machine Remix)"
    assert extract_remixer(title, None, known) == "Purple Disco Machine"
    assert extract_remixer(title, "Existing Remixer", known) == "Existing Remixer"


def test_remixer_counterexamples_are_noops():
    assert extract_remixer("Song (Unknown Remix)", None, ["Known"]) is None
    assert extract_remixer("Song (Original Remix)", None, ["Original"]) is None
    assert extract_remixer("Song (Club Mix)", None, ["Club"]) is None
    assert extract_remixer("Song - Known Remix", None, ["Known"]) is None
    assert extract_remixer("Song [Known (Live) Remix]", None, ["Known"]) is None
    assert extract_remixer("Song (Known Remix) (Other Remix)", None, ["Known", "Other"]) is None
    assert extract_remixer("Song (KNOWN Remix)", None, ["Known", "KNOWN"]) is None


def test_no_generic_casing_or_compatibility_normalization():
    for value in ("DAKITI", "SNAP", "#SELFIE", "deadmau5", "CamelPhat", "t.A.T.u."):
        assert compose("title", value) == value


def test_plan_composes_final_values_in_canonical_order():
    rows = [
        make_row("20", "Clean", artist="Purple Disco Machine"),
        make_row(
            "10",
            "\u00a0Umbrella (FEAT. Jay‐Z) (Purple Disco Machine Remix) - www.pool.example",
            artist="Rihanna ",
            ownership="permanent_library",
        ),
    ]
    assert plan(rows) == [
        {
            "content_id": "10",
            "field": "title",
            "before": "\u00a0Umbrella (FEAT. Jay‐Z) (Purple Disco Machine Remix) - www.pool.example",
            "after": "Umbrella (Purple Disco Machine Remix)",
        },
        {
            "content_id": "10",
            "field": "artist",
            "before": "Rihanna ",
            "after": "Rihanna feat. Jay‐Z",
        },
        {
            "content_id": "10",
            "field": "remixer",
            "before": None,
            "after": "Purple Disco Machine",
        },
    ]


def test_plan_is_deterministic_and_ownership_neutral():
    dirty = [
        make_row("2", "B  title", ownership="app_managed"),
        make_row("1", "A  title", ownership="permanent_library"),
        make_row("3", "C  title", ownership="external"),
    ]
    expected = plan(dirty)
    assert [change["content_id"] for change in expected] == ["1", "2", "3"]
    assert plan(list(reversed(dirty))) == expected
    for row in dirty:
        row["ownership"] = "external"
    assert plan(dirty) == expected


def test_clean_data_none_fields_and_unknown_remixer_are_noops():
    assert plan([make_row("1", "Clean Title", artist="Clean Artist")]) == []
    assert plan([make_row("1", None, artist=None, remixer=None)]) == []
    assert plan([make_row("1", "Song (Unknown Remix)", artist="Main")]) == []


def test_composed_plan_is_a_fixpoint():
    rows = [
        make_row("2", "Clean", artist="Purple Disco Machine"),
        make_row(
            "1",
            "CafÃƒÂ©  (feat. Guest) (Purple Disco Machine Remix) - www.pool.example",
            artist=" Main\u00a0",
        ),
    ]
    first = plan(rows)
    by_id = {row["content_id"]: dict(row) for row in rows}
    for change in first:
        by_id[change["content_id"]][change["field"]] = change["after"]
    assert plan(list(by_id.values())) == []


def test_cross_track_credit_composition_is_a_fixpoint_in_one_plan():
    rows = [
        make_row("1", "Song (feat. Guest)", artist="Main"),
        make_row("2", "Other (Main feat. Guest Remix)", artist="Second"),
    ]
    first = plan(rows)
    assert ("2", "remixer", "Main feat. Guest") in {
        (change["content_id"], change["field"], change["after"])
        for change in first
    }

    by_id = {row["content_id"]: dict(row) for row in rows}
    for change in first:
        by_id[change["content_id"]][change["field"]] = change["after"]
    assert plan(list(by_id.values())) == []


class RunnerCache:
    def __init__(self, rows, current, log):
        self.rows = rows
        self._fingerprint = current
        self.log = log

    def get(self, _storage_root):
        return self.rows

    @property
    def current_fingerprint(self):
        return self._fingerprint

    def invalidate(self):
        self.log.append("invalidate")
        self._fingerprint = None


class RunnerHandle:
    def __init__(self, log):
        self.log = log

    def commit(self):
        self.log.append("commit")

    def rollback(self):
        self.log.append("rollback")

    def close(self):
        self.log.append("close")


def test_execute_requires_a_real_dry_run_fingerprint_before_mutation(tmp_path):
    cache = RunnerCache([make_row("1", "A  title")], (("db", "1"),), [])
    dry = {"payload": plan(cache.rows), "fingerprint": None}

    with pytest.raises(ValueError, match="fingerprint is required"):
        smartfixes_run.execute(
            tmp_path / "missing-master.db",
            tmp_path / "backups",
            cache,
            tmp_path / "storage",
            dry,
            open_db=lambda _path: RunnerHandle([]),
        )
    assert not (tmp_path / "backups").exists()


def test_execute_noop_still_requires_rekordbox_closed_without_a_backup(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "master.db"
    db_path.write_bytes(b"database")
    backups = tmp_path / "backups"
    cache = RunnerCache(
        [make_row("1", "Clean Title")], fingerprint(db_path), []
    )
    dry = smartfixes_run.dry_run(cache, tmp_path / "storage")
    assert dry["payload"] == []

    def blocked(_path):
        raise process_guard.MutationBlockedError()

    monkeypatch.setattr(process_guard, "assert_mutation_ready", blocked)
    with pytest.raises(process_guard.MutationBlockedError):
        smartfixes_run.execute(
            db_path,
            backups,
            cache,
            tmp_path / "storage",
            dry,
            open_db=lambda _path: pytest.fail("no-op must not open the database"),
        )
    assert not backups.exists()

    monkeypatch.setattr(process_guard, "assert_mutation_ready", lambda _path: None)
    result = smartfixes_run.execute(
        db_path,
        backups,
        cache,
        tmp_path / "storage",
        dry,
        open_db=lambda _path: pytest.fail("no-op must not open the database"),
    )
    assert result == {"fields_applied": 0, "tracks_touched": 0}
    assert not backups.exists()


def test_execute_backs_up_then_writes_exactly_and_invalidates(tmp_path, monkeypatch):
    db_path = tmp_path / "master.db"
    db_path.write_bytes(b"database")
    backups = tmp_path / "backups"
    log = []
    cache = RunnerCache(
        [make_row("2", "B  title"), make_row("1", "A  title")],
        fingerprint(db_path),
        log,
    )
    dry = smartfixes_run.dry_run(cache, tmp_path / "storage")

    def guard(path):
        assert path == db_path
        log.append("guard")

    def open_db(path):
        assert path == db_path
        snapshots = list(backups.iterdir())
        assert len(snapshots) == 1
        assert (snapshots[0] / "master.db").read_bytes() == b"database"
        log.append("open")
        return RunnerHandle(log)

    def write(_db, content_id, changes):
        log.append(("write", content_id, changes))

    monkeypatch.setattr(process_guard, "assert_mutation_ready", guard)
    monkeypatch.setattr(smartfixes_run, "set_content_fields", write)
    result = smartfixes_run.execute(
        db_path,
        backups,
        cache,
        tmp_path / "storage",
        dry,
        open_db=open_db,
    )

    assert result == {"fields_applied": 2, "tracks_touched": 2}
    assert log == [
        "guard",
        "open",
        ("write", "1", {"title": "A title"}),
        ("write", "2", {"title": "B title"}),
        "commit",
        "invalidate",
        "close",
    ]


def test_execute_rolls_back_all_writes_and_keeps_backup_on_failure(tmp_path, monkeypatch):
    db_path = tmp_path / "master.db"
    db_path.write_bytes(b"database")
    backups = tmp_path / "backups"
    log = []
    cache = RunnerCache(
        [make_row("1", "A  title"), make_row("2", "B  title")],
        fingerprint(db_path),
        log,
    )
    dry = smartfixes_run.dry_run(cache, tmp_path / "storage")

    monkeypatch.setattr(process_guard, "assert_mutation_ready", lambda _path: None)

    def write(_db, content_id, _changes):
        log.append(("write", content_id))
        if content_id == "2":
            raise RuntimeError("simulated second write failure")

    monkeypatch.setattr(smartfixes_run, "set_content_fields", write)
    with pytest.raises(RuntimeError, match="second write failure"):
        smartfixes_run.execute(
            db_path,
            backups,
            cache,
            tmp_path / "storage",
            dry,
            open_db=lambda _path: RunnerHandle(log),
        )

    assert log == [("write", "1"), ("write", "2"), "rollback", "close"]
    snapshots = list(backups.iterdir())
    assert len(snapshots) == 1
    assert (snapshots[0] / "master.db").read_bytes() == b"database"
    assert cache.current_fingerprint == dry["fingerprint"]
