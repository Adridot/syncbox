"""Source reconciliation (reconcile-deezer-event-tracks-by-isrc): the plan per
design decision 3 and the trash-first execution with its consent contract.

master.db is a plain SQLite file carrying the columns the planner reads, so
a Rekordbox write made through the faked rb_write helpers is seen by the
next preview exactly like a real commit would be.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from syncbox import appdb, event_source_reconcile as reconcile
from syncbox.events_service import add_track, create_event, list_event_tracks
from syncbox.platform_os import PermanentDeleteConsentRequired
from syncbox.safety.mutate import StaleSnapshotError, fingerprint


class Cache:
    def invalidate(self):
        pass


@pytest.fixture
def env(tmp_path, monkeypatch):
    conn = appdb.open_app_db(tmp_path / "app.db")
    storage = tmp_path / "storage"
    event = create_event(conn, storage, "Gig")
    master = tmp_path / "master.db"
    rb = sqlite3.connect(master)
    rb.executescript(
        "CREATE TABLE djmdContent (ID TEXT, Title TEXT, Length INTEGER, ISRC TEXT,"
        " FolderPath TEXT, rb_local_deleted INTEGER DEFAULT 0);"
        "CREATE TABLE djmdMyTag (ID TEXT, Name TEXT, ParentID TEXT, rb_local_deleted INTEGER DEFAULT 0);"
        "CREATE TABLE djmdSongMyTag (ContentID TEXT, MyTagID TEXT, rb_local_deleted INTEGER DEFAULT 0);"
        "CREATE TABLE djmdSongPlaylist (ContentID TEXT, rb_local_deleted INTEGER DEFAULT 0);"
        "INSERT INTO djmdMyTag VALUES ('cat', 'Situation', 'root', 0), ('T1', 'Gig', 'cat', 0),"
        " ('T9', 'Peak', 'cat', 0);"
    )
    rb.commit()
    rb.close()
    monkeypatch.setattr(reconcile, "open_readonly", lambda path: sqlite3.connect(path))
    trash = {"works": True, "calls": []}

    def fake_delete(path, *, consent_to_permanent_delete=False):
        trash["calls"].append((str(path), consent_to_permanent_delete))
        if not trash["works"] and not consent_to_permanent_delete:
            raise PermanentDeleteConsentRequired(Path(path), OSError("no trash"))
        Path(path).unlink()
        return "trashed"

    @contextmanager
    def fake_mutate(db_path, backups_root, *, expected_fingerprint, invalidate_cache, **kwargs):
        assert expected_fingerprint == fingerprint(db_path)
        db = sqlite3.connect(db_path)
        yield db
        db.commit()
        db.close()
        invalidate_cache()

    monkeypatch.setattr(reconcile, "delete_file", fake_delete)
    monkeypatch.setattr(reconcile, "mutate", fake_mutate)
    monkeypatch.setattr(reconcile, "tag_content", lambda db, c, t: db.execute(
        "INSERT INTO djmdSongMyTag VALUES (?, ?, 0)", (c, t)))
    monkeypatch.setattr(reconcile, "untag_content", lambda db, c, t: db.execute(
        "UPDATE djmdSongMyTag SET rb_local_deleted = 1 WHERE ContentID = ? AND MyTagID = ?", (c, t)))
    monkeypatch.setattr(reconcile, "soft_delete_content", lambda db, c: db.execute(
        "UPDATE djmdContent SET rb_local_deleted = 1 WHERE ID = ?", (c,)))

    class Env:
        pass

    e = Env()
    e.conn, e.storage, e.event, e.master, e.trash, e.tmp = conn, storage, event, master, trash, tmp_path
    e.audio = Path(event["staging_dir"]) / "audio"

    def rb_sql(sql, *params):
        db = sqlite3.connect(master)
        db.execute(sql, params)
        db.commit()
        db.close()

    def content(content_id, isrc, path, title="Song", length=200):
        rb_sql("INSERT INTO djmdContent VALUES (?, ?, ?, ?, ?, 0)", content_id, title, length, isrc, str(path))

    def row(item_id, status, isrc, filename=None, content_id=None, path=None):
        track = add_track(conn, event, resolved_source={
            "provider": "deezer", "item_id": item_id, "url": f"https://www.deezer.com/track/{item_id}",
            "title": "Song", "artist": "Artist", "duration_ms": 200_000, "isrc": isrc,
        })
        if filename:
            path = e.audio / filename
            path.write_bytes(b"download " + filename.encode())
        conn.execute("UPDATE event_tracks SET status = ?, staging_file_path = ?, content_id = ? WHERE id = ?",
                     (status, str(path) if path else None, content_id, track["id"]))
        return track["id"]

    e.rb_sql, e.content, e.row = rb_sql, content, row
    e.plan = lambda: reconcile.build_plan(conn, storage, master)
    e.run = lambda plan, **kw: reconcile.execute(conn, master, tmp_path / "b", Cache(), storage, plan, **kw)
    e.track = lambda track_id: next(t for t in list_event_tracks(conn, event["id"]) if t["id"] == track_id)
    yield e
    conn.close()


def _replace_case(env):
    """An applied download (D2, tagged by the event) duplicating original O2."""
    env.content("O2", "FR0000000002", env.storage / "music" / "two.mp3")
    track = env.row("2", "applied", "FR0000000002", "b.mp3", content_id="D2")
    env.content("D2", "FR0000000002", env.audio / "b.mp3")
    env.rb_sql("INSERT INTO djmdSongMyTag VALUES ('D2', 'T1', 0)")
    return track


def test_plan_classifies_every_design_case_and_reports_coverage(env):
    env.content("O1", "FR0000000001", env.storage / "music" / "one.mp3")
    ready_hit = env.row("1", "ready", "fr0000000001 ", "a.mp3")
    applied_hit = _replace_case(env)
    env.content("O3a", "FR0000000003", env.storage / "music" / "three.mp3")
    env.content("O3b", "FR0000000003", env.storage / "music" / "three (2).mp3")
    ambiguous = env.row("3", "ready", "FR0000000003", "c.mp3")
    no_candidate = env.row("4", "ready", "FR0000000004", "d.mp3")
    outside = env.tmp / "outside.mp3"
    outside.write_bytes(b"not ours")
    outside_staging = env.row("5", "ready", "FR0000000001", path=outside)
    env.content("O6", "FR0000000006", env.storage / "music" / "six.mp3")
    tagged_elsewhere = env.row("6", "applied", "FR0000000006", "f.mp3", content_id="D6")
    env.content("D6", "FR0000000006", env.audio / "f.mp3")
    env.rb_sql("INSERT INTO djmdSongMyTag VALUES ('D6', 'T1', 0), ('D6', 'T9', 0)")
    no_isrc = env.row("7", "ready", None, "g.mp3")
    # Coverage-only material: a Deezer download Rekordbox holds without ISRC,
    # and one dashed ISRC.
    env.content("H", "", env.audio / "h.mp3")
    env.conn.execute("INSERT INTO acquisition_jobs (provider, scope, ref, status, phase, published_path)"
                     " VALUES ('deezer', 'event', '1', 'downloaded', 'published', ?)", (str(env.audio / "h.mp3"),))
    env.content("X", "FR-000-0000099", env.storage / "music" / "x.mp3")

    plan = env.plan()

    items = {item["track_id"]: item for item in plan["items"]}
    assert set(items) == {ready_hit, applied_hit}
    assert (items[ready_hit]["action"], items[ready_hit]["content_id"]) == ("rematch", "O1")
    assert items[ready_hit]["file"]["sha256"]
    assert (items[applied_hit]["action"], items[applied_hit]["content_id"],
            items[applied_hit]["duplicate_content_id"], items[applied_hit]["tag_id"]) == ("replace", "O2", "D2", "T1")
    reasons = {entry["track_id"]: entry["reason"] for entry in plan["skipped"]}
    assert reasons == {
        ambiguous: "ambiguous",
        no_candidate: "no_candidate",
        outside_staging: "unsafe_file",
        tagged_elsewhere: "duplicate_in_use",
        no_isrc: "missing_isrc",
    }
    coverage = plan["isrc_coverage"]
    assert (coverage["rows_with_isrc"], coverage["rows_without_isrc"], coverage["rows_with_candidate"]) == (6, 1, 5)
    assert [entry["content_id"] for entry in coverage["downloads_without_isrc"]] == ["H"]
    assert coverage["non_alphanumeric_isrcs"] == 1
    assert plan["fingerprint"] == [list(part) for part in fingerprint(env.master)]


def test_plan_skips_a_guard_rejected_candidate_and_a_file_held_elsewhere(env):
    env.content("O1", "FR0000000001", env.storage / "music" / "one.mp3", title="Other Thing", length=500)
    guarded = env.row("1", "ready", "FR0000000001", "a.mp3")
    env.content("O2", "FR0000000002", env.storage / "music" / "two.mp3")
    shared = env.row("2", "ready", "FR0000000002", "b.mp3")
    holder = env.row("3", "missing", None)
    env.conn.execute("UPDATE event_tracks SET staging_file_path = ? WHERE id = ?", (str(env.audio / "b.mp3"), holder))

    reasons = {entry["track_id"]: entry["reason"] for entry in env.plan()["skipped"]}

    assert reasons == {guarded: "guard_rejected", shared: "file_in_use"}


def test_execute_rematches_and_replaces_then_trashes(env):
    env.content("O1", "FR0000000001", env.storage / "music" / "one.mp3")
    ready = env.row("1", "ready", "FR0000000001", "a.mp3")
    applied = _replace_case(env)

    result = env.run(env.plan())

    assert result["dry_run"] is False and result["cleanup_pending"] == [] and not result["consent_required"]
    assert sorted(result["trashed_files"]) == [str(env.audio / "a.mp3"), str(env.audio / "b.mp3")]
    assert not (env.audio / "a.mp3").exists() and not (env.audio / "b.mp3").exists()
    row = env.track(ready)
    assert (row["status"], row["content_id"], row["confidence"], row["staging_file_path"]) == ("matched", "O1", 100, None)
    row = env.track(applied)
    assert (row["status"], row["content_id"], row["staging_file_path"]) == ("applied", "O2", None)
    db = sqlite3.connect(env.master)
    assert db.execute("SELECT rb_local_deleted FROM djmdContent WHERE ID = 'D2'").fetchone() == (1,)
    assert db.execute("SELECT ContentID FROM djmdSongMyTag WHERE MyTagID = 'T1' AND rb_local_deleted = 0").fetchall() == [("O2",)]
    db.close()
    assert env.plan()["items"] == []


def test_execute_refuses_a_stale_plan(env):
    env.content("O1", "FR0000000001", env.storage / "music" / "one.mp3")
    ready = env.row("1", "ready", "FR0000000001", "a.mp3")
    plan = env.plan()
    (env.audio / "a.mp3").write_bytes(b"retagged since the preview")

    with pytest.raises(StaleSnapshotError):
        env.run(plan)

    assert env.track(ready)["status"] == "ready" and env.trash["calls"] == []
    plan = env.plan()
    env.content("O1b", "FR0000000001", env.storage / "music" / "one (2).mp3")
    with pytest.raises(StaleSnapshotError):
        env.run(plan)


def test_refused_trash_before_any_change_leaves_row_and_file_for_the_consent_retry(env):
    env.content("O1", "FR0000000001", env.storage / "music" / "one.mp3")
    ready = env.row("1", "ready", "FR0000000001", "a.mp3")
    env.trash["works"] = False
    plan = env.plan()

    with pytest.raises(PermanentDeleteConsentRequired):
        env.run(plan)
    assert env.track(ready)["status"] == "ready" and (env.audio / "a.mp3").exists()

    env.run(plan, consent_to_permanent_delete=True)
    assert env.track(ready)["status"] == "matched" and not (env.audio / "a.mp3").exists()


def test_refused_trash_after_the_commit_is_cleanup_pending_then_retried_with_consent(env):
    applied = _replace_case(env)
    env.trash["works"] = False

    result = env.run(env.plan())

    assert result["consent_required"] is True
    assert result["cleanup_pending"] == [
        {"track_id": applied, "path": str(env.audio / "b.mp3"), "reason": "permanent_delete_consent"}
    ]
    row = env.track(applied)  # repaired, and the kept file stays referenced
    assert (row["content_id"], row["staging_file_path"]) == ("O2", str(env.audio / "b.mp3"))
    assert (env.audio / "b.mp3").exists()

    plan = env.plan()
    assert [(item["action"], item["content_id"]) for item in plan["items"]] == [("cleanup", "O2")]
    with pytest.raises(PermanentDeleteConsentRequired):
        env.run(plan)
    env.run(plan, consent_to_permanent_delete=True)
    assert env.track(applied)["staging_file_path"] is None and not (env.audio / "b.mp3").exists()
    assert env.plan()["items"] == []
