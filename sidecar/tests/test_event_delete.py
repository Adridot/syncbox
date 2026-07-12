"""Focused tests for exact event-delete plans and retained-track safety."""

import json
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from syncbox import appdb, event_delete
from syncbox.events_service import create_event
from syncbox.platform_os import PermanentDeleteConsentRequired
from syncbox.safety.mutate import StaleSnapshotError
from syncbox.safety.paths import canonical_key


class FakeCache:
    def __init__(self):
        self.invalidated = 0

    def invalidate(self):
        self.invalidated += 1


@pytest.fixture
def conn(tmp_path):
    connection = appdb.open_app_db(tmp_path / "app.db")
    yield connection
    connection.close()


def _plan(event, staging_file: Path | None = None) -> dict:
    artifacts = [str(staging_file)] if staging_file is not None else []
    cleanup_files = (
        [event_delete._file_state(staging_file, with_hash=True)]
        if staging_file is not None
        else []
    )
    return {
        "dry_run": True,
        "plan_version": 1,
        "event_id": event["id"],
        "event_name": event["name"],
        "fingerprint": [["1", "2"]],
        "tag_id": None,
        "event_mytag": None,
        "tracks": [],
        "playlists": [],
        "xml_artifacts": [],
        "staging_artifacts": artifacts,
        "expected_file_deletions": artifacts,
        "validation": {
            "db_fingerprint": [["1", "2"]],
            "sources": [],
            "destinations": [],
            "active_mytags": [],
            "support_files": [],
            "cleanup_files": cleanup_files,
        },
    }


def test_collision_policy_reuses_only_unreferenced_identical_file(tmp_path):
    source = tmp_path / "staging" / "Track.mp3"
    collection = tmp_path / "Collection"
    source.parent.mkdir()
    collection.mkdir()
    source.write_bytes(b"same")
    existing = collection / source.name
    existing.write_bytes(b"same")

    destination, reused, inspected, source_state = event_delete._migration_destination(
        source, "10", collection, [], tmp_path
    )
    assert destination == existing
    assert reused is True
    assert inspected[-1]["sha256"] == source_state["sha256"]

    destination, reused, _, _ = event_delete._migration_destination(
        source, "10", collection, [("99", str(existing))], tmp_path
    )
    assert destination == collection / "Track - 2.mp3"
    assert reused is False


def test_collision_policy_never_overwrites_different_content(tmp_path):
    source = tmp_path / "staging" / "Track.mp3"
    collection = tmp_path / "Collection"
    source.parent.mkdir()
    collection.mkdir()
    source.write_bytes(b"new")
    (collection / source.name).write_bytes(b"old")
    (collection / "Track - 2.mp3").write_bytes(b"also-old")

    destination, reused, inspected, _ = event_delete._migration_destination(
        source, "10", collection, [], tmp_path
    )
    assert destination == collection / "Track - 3.mp3"
    assert reused is False
    assert [state["path"] for state in inspected] == [
        str(collection / "Track.mp3"),
        str(collection / "Track - 2.mp3"),
        str(collection / "Track - 3.mp3"),
    ]


def test_collision_policy_reserves_destinations_between_tracks(tmp_path):
    source = tmp_path / "staging" / "Track.mp3"
    collection = tmp_path / "Collection"
    source.parent.mkdir()
    collection.mkdir()
    source.write_bytes(b"same")
    existing = collection / source.name
    existing.write_bytes(b"same")

    destination, reused, _, _ = event_delete._migration_destination(
        source,
        "11",
        collection,
        [],
        tmp_path,
        {canonical_key(existing, tmp_path)},
    )
    assert destination == collection / "Track - 2.mp3"
    assert reused is False


def test_anlz_paths_match_pyrekordbox_directory_enumeration(tmp_path):
    db_path = tmp_path / "master.db"
    analysis = tmp_path / "share" / "PIONEER" / "0001"
    analysis.mkdir(parents=True)
    actual_dat = analysis / "ANLZ9999.DAT"
    actual_ext = analysis / "ANLZ1234.EXT"
    actual_dat.write_bytes(b"dat")
    actual_ext.write_bytes(b"ext")

    paths = event_delete._anlz_paths(
        db_path, "PIONEER/0001/ANLZ0000.DAT"
    )
    assert paths == [actual_dat, actual_ext]


def test_event_playlist_query_excludes_user_homonyms_outside_owned_folder():
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE djmdPlaylist (ID TEXT, Name TEXT, ParentID TEXT, "
        "Attribute INTEGER, rb_local_deleted INTEGER)"
    )
    db.executemany(
        "INSERT INTO djmdPlaylist VALUES (?, ?, ?, ?, 0)",
        [
            ("folder", "Event Imports", "root", 1),
            ("owned", "My Event", "folder", 4),
            ("user", "My Event", "root", 4),
            ("ordinary", "My Event", "folder", 0),
        ],
    )
    rows = db.execute(
        event_delete._PLAYLISTS_SQL,
        {
            "name": "My Event",
            "legacy": "My Event - Smart",
            "folder": "Event Imports",
        },
    ).fetchall()
    db.close()
    assert rows == [("owned", "My Event")]


def test_plan_rejects_staging_or_collection_symlink_escape(tmp_path):
    storage = tmp_path / "storage"
    events = storage / "_syncbox" / "events"
    events.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    staging_link = events / "event"
    staging_link.symlink_to(outside, target_is_directory=True)
    event = {
        "id": 1,
        "name": "Event",
        "default_tag": "Event",
        "staging_dir": str(staging_link),
    }
    with pytest.raises(event_delete.EventMigrationError, match="symbolic link"):
        event_delete.build_plan(
            lambda *args: [], event, storage, tmp_path / "master.db", [["1", "2"]]
        )

    staging_link.unlink()
    staging_link.mkdir()
    (storage / "rekordbox").mkdir()
    (storage / "rekordbox" / "Collection").symlink_to(
        outside, target_is_directory=True
    )
    with pytest.raises(event_delete.EventMigrationError, match="symbolic-link"):
        event_delete.build_plan(
            lambda *args: [], event, storage, tmp_path / "master.db", [["1", "2"]]
        )


def test_copy_publishes_verified_destination_and_keeps_source(tmp_path):
    source = tmp_path / "staging" / "Track.mp3"
    destination = tmp_path / "Collection" / source.name
    source.parent.mkdir()
    source.write_bytes(b"audio")
    expected = {"content_id": "10", **event_delete._file_state(source)}
    track = {
        "source_path": str(source),
        "destination_path": str(destination),
        "destination_reused": False,
    }

    published, created, digest = event_delete._copy_migration(track, expected)
    assert published == destination
    assert created is True
    assert destination.read_bytes() == source.read_bytes() == b"audio"
    assert event_delete._sha256(destination) == digest


def test_copy_removes_destination_when_post_publish_fsync_fails(
    tmp_path, monkeypatch
):
    source = tmp_path / "staging" / "Track.mp3"
    destination = tmp_path / "Collection" / source.name
    source.parent.mkdir()
    source.write_bytes(b"audio")
    expected = {"content_id": "10", **event_delete._file_state(source)}
    original_fsync = event_delete._fsync_directory
    calls = 0

    def fail_once(directory):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("fsync failed")
        return original_fsync(directory)

    monkeypatch.setattr(event_delete, "_fsync_directory", fail_once)
    with pytest.raises(OSError, match="fsync failed"):
        event_delete._copy_migration(
            {
                "source_path": str(source),
                "destination_path": str(destination),
                "destination_reused": False,
            },
            expected,
        )
    assert source.is_file()
    assert not destination.exists()


def test_hard_link_fallback_removes_destination_if_temp_unlink_fails(
    tmp_path, monkeypatch
):
    source = tmp_path / "temp"
    destination = tmp_path / "destination"
    source.write_bytes(b"audio")
    monkeypatch.setattr(event_delete.ctypes, "CDLL", lambda *args, **kwargs: SimpleNamespace())
    original_unlink = Path.unlink
    failed = False

    def fail_source_once(path, *args, **kwargs):
        nonlocal failed
        if path == source and not failed:
            failed = True
            raise OSError("temp unlink failed")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_source_once)
    with pytest.raises(OSError, match="temp unlink failed"):
        event_delete._rename_exclusive(source, destination)
    assert source.is_file()
    assert not destination.exists()


def test_execution_rejects_any_plan_change_before_cleanup(conn, tmp_path, monkeypatch):
    event = create_event(conn, tmp_path / "storage", "Exact")
    staged = Path(event["staging_dir"]) / "track.mp3"
    staged.write_bytes(b"audio")
    fresh = _plan(event, staged)
    submitted = {**fresh, "event_name": "tampered"}
    monkeypatch.setattr(event_delete, "read_plan", lambda *args: fresh)

    with pytest.raises(StaleSnapshotError):
        event_delete.delete_event(
            conn,
            tmp_path / "master.db",
            tmp_path / "backups",
            FakeCache(),
            tmp_path / "storage",
            event,
            dry_run=False,
            plan=submitted,
        )
    assert staged.is_file()
    assert conn.execute("SELECT 1 FROM events WHERE id = ?", (event["id"],)).fetchone()


def test_preview_refuses_a_mytag_shared_by_two_app_events(conn, tmp_path):
    first = create_event(conn, tmp_path / "storage", "Shared Event")
    create_event(conn, tmp_path / "storage", "Shared Event")
    with pytest.raises(event_delete.EventMigrationError, match="shared"):
        event_delete.delete_event(
            conn,
            tmp_path / "master.db",
            tmp_path / "backups",
            FakeCache(),
            tmp_path / "storage",
            first,
            dry_run=True,
        )


def test_database_free_plan_cleans_only_displayed_files(conn, tmp_path, monkeypatch):
    event = create_event(conn, tmp_path / "storage", "Cleanup")
    staged = Path(event["staging_dir"]) / "track.mp3"
    staged.write_bytes(b"audio")
    plan = _plan(event, staged)
    monkeypatch.setattr(event_delete, "read_plan", lambda *args: plan)
    seen = []

    def remove(path, *, consent_to_permanent_delete=False):
        seen.append((str(path), consent_to_permanent_delete))
        Path(path).unlink()
        return "trashed"

    monkeypatch.setattr(event_delete, "delete_file", remove)
    result = event_delete.delete_event(
        conn,
        tmp_path / "master.db",
        tmp_path / "backups",
        FakeCache(),
        tmp_path / "storage",
        event,
        dry_run=False,
        plan=plan,
        consent_to_permanent_delete=True,
    )
    assert result["deleted_event"] is True
    assert seen == [(str(staged), True)]
    assert conn.execute("SELECT 1 FROM events WHERE id = ?", (event["id"],)).fetchone() is None


def test_postcommit_cleanup_retries_without_reapplying_database(
    conn, tmp_path, monkeypatch
):
    event = create_event(conn, tmp_path / "storage", "Retry")
    staged = Path(event["staging_dir"]) / "track.mp3"
    staged.write_bytes(b"audio")
    plan = _plan(event, staged)
    conn.execute(
        "UPDATE events SET delete_plan = ?, delete_committed = 1 WHERE id = ?",
        (json.dumps(plan), event["id"]),
    )
    event = dict(conn.execute("SELECT * FROM events WHERE id = ?", (event["id"],)).fetchone())
    monkeypatch.setattr(event_delete, "_db_plan_committed", lambda *args: True)

    def remove(path, *, consent_to_permanent_delete=False):
        if not consent_to_permanent_delete:
            raise PermanentDeleteConsentRequired(Path(path), OSError("no trash"))
        Path(path).unlink()
        return "deleted_permanently"

    monkeypatch.setattr(event_delete, "delete_file", remove)
    with pytest.raises(PermanentDeleteConsentRequired):
        event_delete.delete_event(
            conn,
            tmp_path / "master.db",
            tmp_path / "backups",
            FakeCache(),
            tmp_path / "storage",
            event,
            dry_run=False,
            plan=plan,
        )
    assert staged.is_file()
    event = dict(conn.execute("SELECT * FROM events WHERE id = ?", (event["id"],)).fetchone())
    result = event_delete.delete_event(
        conn,
        tmp_path / "master.db",
        tmp_path / "backups",
        FakeCache(),
        tmp_path / "storage",
        event,
        dry_run=False,
        plan=plan,
        consent_to_permanent_delete=True,
    )
    assert result["cleanup_only"] is True
    assert not staged.exists()


def test_postcommit_cleanup_rejects_replaced_staging_file(
    conn, tmp_path, monkeypatch
):
    event = create_event(conn, tmp_path / "storage", "Replaced")
    staged = Path(event["staging_dir"]) / "track.mp3"
    staged.write_bytes(b"first")
    plan = _plan(event, staged)
    conn.execute(
        "UPDATE events SET delete_plan = ?, delete_committed = 1 WHERE id = ?",
        (json.dumps(plan), event["id"]),
    )
    staged.write_bytes(b"other")
    monkeypatch.setattr(event_delete, "_db_plan_committed", lambda *args: True)

    with pytest.raises(event_delete.EventCleanupError, match="changed"):
        event_delete.delete_event(
            conn,
            tmp_path / "master.db",
            tmp_path / "backups",
            FakeCache(),
            tmp_path / "storage",
            event,
            dry_run=False,
            plan=plan,
        )
    assert staged.read_bytes() == b"other"
    assert conn.execute("SELECT 1 FROM events WHERE id = ?", (event["id"],)).fetchone()


def test_cleanup_retry_requires_rekordbox_guard(conn, tmp_path, monkeypatch):
    event = create_event(conn, tmp_path / "storage", "Guarded retry")
    staged = Path(event["staging_dir"]) / "track.mp3"
    staged.write_bytes(b"audio")
    plan = _plan(event, staged)
    plan["tag_id"] = "42"
    conn.execute(
        "UPDATE events SET delete_plan = ?, delete_committed = 1 WHERE id = ?",
        (json.dumps(plan), event["id"]),
    )
    monkeypatch.setattr(event_delete, "_db_plan_committed", lambda *args: True)
    monkeypatch.setattr(
        event_delete,
        "assert_mutation_ready",
        lambda *args: (_ for _ in ()).throw(RuntimeError("Rekordbox is running")),
    )
    monkeypatch.setattr(
        event_delete,
        "delete_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("guard must run before cleanup")
        ),
    )

    with pytest.raises(RuntimeError, match="running"):
        event_delete.delete_event(
            conn,
            tmp_path / "master.db",
            tmp_path / "backups",
            FakeCache(),
            tmp_path / "storage",
            event,
            dry_run=False,
            plan=plan,
        )
    assert staged.is_file()
    assert conn.execute("SELECT 1 FROM events WHERE id = ?", (event["id"],)).fetchone()


def test_postcommit_cleanup_keeps_source_when_destination_is_lost(
    conn, tmp_path, monkeypatch
):
    event = create_event(conn, tmp_path / "storage", "Lost destination")
    source = Path(event["staging_dir"]) / "track.mp3"
    source.write_bytes(b"audio")
    destination = tmp_path / "storage" / "rekordbox" / "Collection" / source.name
    plan = _plan(event, source)
    plan["tracks"] = [
        {
            "content_id": "10",
            "source_path": str(source),
            "action": "migrate_to_collection",
            "destination_path": str(destination),
            "destination_reused": False,
        }
    ]
    plan["validation"]["sources"] = [
        {"content_id": "10", **event_delete._file_state(source, with_hash=True)}
    ]
    conn.execute(
        "UPDATE events SET delete_plan = ?, delete_committed = 1 WHERE id = ?",
        (json.dumps(plan), event["id"]),
    )
    monkeypatch.setattr(event_delete, "_db_plan_committed", lambda *args: True)
    monkeypatch.setattr(event_delete, "assert_mutation_ready", lambda *args: None)

    with pytest.raises(event_delete.EventCleanupError, match="destination"):
        event_delete.delete_event(
            conn,
            tmp_path / "master.db",
            tmp_path / "backups",
            FakeCache(),
            tmp_path / "storage",
            event,
            dry_run=False,
            plan=plan,
        )
    assert source.is_file()
    assert conn.execute("SELECT 1 FROM events WHERE id = ?", (event["id"],)).fetchone()


def test_precommit_crash_state_is_recovered_before_exact_retry(
    conn, tmp_path, monkeypatch
):
    event = create_event(conn, tmp_path / "storage", "Crash recovery")
    source = Path(event["staging_dir"]) / "track.mp3"
    source.write_bytes(b"audio")
    destination = tmp_path / "storage" / "rekordbox" / "Collection" / source.name
    destination.parent.mkdir(parents=True)
    shutil.copy2(source, destination)
    plan = _plan(event, source)
    plan["tracks"] = [
        {
            "content_id": "10",
            "source_path": str(source),
            "action": "migrate_to_collection",
            "destination_path": str(destination),
            "destination_reused": False,
        }
    ]
    plan["validation"]["sources"] = [
        {"content_id": "10", **event_delete._file_state(source, with_hash=True)}
    ]
    conn.execute(
        "UPDATE events SET delete_plan = ?, delete_committed = 0 WHERE id = ?",
        (json.dumps(plan), event["id"]),
    )
    monkeypatch.setattr(event_delete, "_db_plan_committed", lambda *args: False)
    monkeypatch.setattr(event_delete, "read_plan", lambda *args: plan)
    monkeypatch.setattr(event_delete, "assert_mutation_ready", lambda *args: None)
    monkeypatch.setattr(event_delete, "fingerprint", lambda *args: (("1", "2"),))

    def remove(path, *, consent_to_permanent_delete=False):
        Path(path).unlink()
        return "trashed"

    monkeypatch.setattr(event_delete, "delete_file", remove)
    assert event_delete.delete_event(
        conn,
        tmp_path / "master.db",
        tmp_path / "backups",
        FakeCache(),
        tmp_path / "storage",
        event,
        dry_run=True,
    ) == plan
    result = event_delete.delete_event(
        conn,
        tmp_path / "master.db",
        tmp_path / "backups",
        FakeCache(),
        tmp_path / "storage",
        event,
        dry_run=False,
        plan=plan,
    )
    assert result["cleanup_only"] is False
    assert destination.read_bytes() == b"audio"
    assert not source.exists()
    assert conn.execute("SELECT 1 FROM events WHERE id = ?", (event["id"],)).fetchone() is None


def test_precommit_support_recovery_requires_a_mutating_phase_receipt(
    conn, tmp_path, monkeypatch
):
    db_path = tmp_path / "live" / "master.db"
    db_path.parent.mkdir()
    db_path.write_bytes(b"db")
    event = create_event(conn, tmp_path / "storage", "Support receipt")
    support = db_path.parent / "share" / "PIONEER" / "ANLZ0000.DAT"
    support.parent.mkdir(parents=True)
    support.write_bytes(b"original")
    plan = _plan(event)
    plan["validation"]["support_files"] = [
        {"role": "anlz", "content_id": "10", **event_delete._file_state(support, with_hash=True)}
    ]
    backup_dir = tmp_path / "backups" / "rekordbox-db-20260711-120000"
    backed = backup_dir / "extra" / support.relative_to(db_path.parent)
    backed.parent.mkdir(parents=True)
    shutil.copy2(support, backed)
    support.write_bytes(b"ambiguous")
    monkeypatch.setattr(event_delete, "assert_mutation_ready", lambda *args: None)
    interrupted = {
        **event,
        "delete_backup": str(backup_dir),
        "delete_phase": "backup_ready",
    }

    with pytest.raises(event_delete.EventMigrationError, match="ambiguous"):
        event_delete._recover_precommit(interrupted, plan, db_path)
    assert support.read_bytes() == b"ambiguous"

    interrupted["delete_phase"] = "mutating"
    event_delete._recover_precommit(interrupted, plan, db_path)
    assert support.read_bytes() == b"original"


def test_stale_resume_does_not_restore_support_files(conn, tmp_path, monkeypatch):
    db_path = tmp_path / "live" / "master.db"
    db_path.parent.mkdir()
    db_path.write_bytes(b"db")
    event = create_event(conn, tmp_path / "storage", "Stale support")
    support = db_path.parent / "share" / "PIONEER" / "ANLZ0000.DAT"
    support.parent.mkdir(parents=True)
    support.write_bytes(b"original")
    plan = _plan(event)
    plan["validation"]["support_files"] = [
        {"role": "anlz", "content_id": "10", **event_delete._file_state(support, with_hash=True)}
    ]
    backup_dir = tmp_path / "backups" / "rekordbox-db-20260711-120000"
    backed = backup_dir / "extra" / support.relative_to(db_path.parent)
    backed.parent.mkdir(parents=True)
    shutil.copy2(support, backed)
    support.write_bytes(b"interrupted-write")
    conn.execute(
        "UPDATE events SET delete_plan = ?, delete_backup = ?, "
        "delete_phase = 'mutating' WHERE id = ?",
        (json.dumps(plan), str(backup_dir), event["id"]),
    )
    monkeypatch.setattr(event_delete, "_db_plan_committed", lambda *args: False)
    monkeypatch.setattr(event_delete, "assert_mutation_ready", lambda *args: None)
    monkeypatch.setattr(event_delete, "fingerprint", lambda *args: (("changed", "db"),))

    with pytest.raises(StaleSnapshotError, match="changed"):
        event_delete.delete_event(
            conn,
            db_path,
            tmp_path / "backups",
            FakeCache(),
            tmp_path / "storage",
            event,
            dry_run=False,
            plan=plan,
        )
    assert support.read_bytes() == b"interrupted-write"


def test_resume_revalidates_cleanup_files_before_rekordbox_mutation(
    conn, tmp_path, monkeypatch
):
    event = create_event(conn, tmp_path / "storage", "Resume source")
    staged = Path(event["staging_dir"]) / "track.mp3"
    staged.write_bytes(b"original")
    plan = _plan(event, staged)
    plan["tag_id"] = "42"
    conn.execute(
        "UPDATE events SET delete_plan = ?, delete_phase = 'planned' WHERE id = ?",
        (json.dumps(plan), event["id"]),
    )
    staged.write_bytes(b"replacement")
    monkeypatch.setattr(event_delete, "_db_plan_committed", lambda *args: False)
    monkeypatch.setattr(event_delete, "assert_mutation_ready", lambda *args: None)
    monkeypatch.setattr(event_delete, "fingerprint", lambda *args: (("1", "2"),))
    monkeypatch.setattr(
        event_delete,
        "mutate",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("stale cleanup file must abort before mutate")
        ),
    )

    with pytest.raises(StaleSnapshotError, match="file state changed"):
        event_delete.delete_event(
            conn,
            tmp_path / "master.db",
            tmp_path / "backups",
            FakeCache(),
            tmp_path / "storage",
            event,
            dry_run=False,
            plan=plan,
        )
    assert staged.read_bytes() == b"replacement"


def test_precommit_revalidates_cleanup_files_after_migration_copy(tmp_path):
    staged = tmp_path / "track.mp3"
    staged.write_bytes(b"original")
    plan = {
        "tracks": [],
        "validation": {
            "sources": [],
            "support_files": [],
            "cleanup_files": [event_delete._file_state(staged, with_hash=True)],
        },
    }
    staged.write_bytes(b"replacement")
    with pytest.raises(StaleSnapshotError, match="file state changed"):
        event_delete._verify_precommit_files(plan)


def test_app_state_failure_after_rekordbox_commit_never_rolls_back_files(
    conn, tmp_path, monkeypatch
):
    event = create_event(conn, tmp_path / "storage", "Journal failure")
    staged = Path(event["staging_dir"]) / "track.mp3"
    staged.write_bytes(b"audio")
    plan = _plan(event, staged)
    plan["tag_id"] = "42"
    plan["event_mytag"] = {"tag_id": "42", "name": event["default_tag"]}
    monkeypatch.setattr(event_delete, "read_plan", lambda *args: plan)
    monkeypatch.setattr(event_delete, "_db_plan_committed", lambda *args: True)
    monkeypatch.setattr(event_delete, "_execute_rekordbox_plan", lambda *args: None)
    monkeypatch.setattr(event_delete, "assert_mutation_ready", lambda *args: None)

    @contextmanager
    def committed_mutate(*args, **kwargs):
        yield object()

    monkeypatch.setattr(event_delete, "mutate", committed_mutate)

    class FailCommitStateOnce:
        def __init__(self, connection):
            self.connection = connection
            self.failed = False

        def execute(self, sql, params=()):
            if sql.startswith("UPDATE events SET delete_committed = 1") and not self.failed:
                self.failed = True
                raise sqlite3.OperationalError("app DB write failed")
            return self.connection.execute(sql, params)

    cache = FakeCache()
    with pytest.raises(event_delete.EventCleanupError, match="could not record"):
        event_delete.delete_event(
            FailCommitStateOnce(conn),
            tmp_path / "master.db",
            tmp_path / "backups",
            cache,
            tmp_path / "storage",
            event,
            dry_run=False,
            plan=plan,
        )
    assert staged.is_file()
    stored_event = dict(
        conn.execute("SELECT * FROM events WHERE id = ?", (event["id"],)).fetchone()
    )
    assert stored_event["delete_plan"] is not None
    assert stored_event["delete_committed"] == 0
    assert cache.invalidated == 1

    def remove(path, *, consent_to_permanent_delete=False):
        Path(path).unlink()
        return "trashed"

    monkeypatch.setattr(event_delete, "delete_file", remove)
    result = event_delete.delete_event(
        conn,
        tmp_path / "master.db",
        tmp_path / "backups",
        cache,
        tmp_path / "storage",
        stored_event,
        dry_run=False,
        plan=plan,
    )
    assert result["cleanup_only"] is True
    assert not staged.exists()


def test_mutation_failure_restores_anlz_removes_destination_and_keeps_event(
    conn, tmp_path, monkeypatch
):
    db_path = tmp_path / "live" / "master.db"
    db_path.parent.mkdir()
    db_path.write_bytes(b"db")
    event = create_event(conn, tmp_path / "storage", "Rollback")
    source = Path(event["staging_dir"]) / "retained.mp3"
    source.write_bytes(b"audio")
    destination = tmp_path / "storage" / "rekordbox" / "Collection" / source.name
    anlz = db_path.parent / "share" / "PIONEER" / "ANLZ0000.DAT"
    anlz.parent.mkdir(parents=True)
    anlz.write_bytes(b"original-anlz")
    plan = _plan(event, source)
    plan["tag_id"] = "42"
    plan["event_mytag"] = {"tag_id": "42", "name": event["default_tag"]}
    plan["tracks"] = [
        {
            "content_id": "10",
            "title": "Retained",
            "artist": "Artist",
            "source_path": str(source),
            "ownership": "app_managed",
            "retaining_mytags": ["Energy"],
            "action": "migrate_to_collection",
            "destination_path": str(destination),
            "destination_reused": False,
            "anlz_update_required": True,
        }
    ]
    plan["validation"]["sources"] = [
        {"content_id": "10", **event_delete._file_state(source)}
    ]
    plan["validation"]["active_mytags"] = [
        {"content_id": "10", "tag_ids": ["88"], "tag_names": ["Energy"]}
    ]
    plan["validation"]["support_files"] = [
        {"role": "anlz", "content_id": "10", **event_delete._file_state(anlz, with_hash=True)}
    ]
    monkeypatch.setattr(event_delete, "read_plan", lambda *args: plan)
    backup_dir = tmp_path / "backups" / "rekordbox-db-20260711-120000"
    backed_anlz = backup_dir / "extra" / anlz.relative_to(db_path.parent)
    backed_anlz.parent.mkdir(parents=True)
    shutil.copy2(anlz, backed_anlz)

    @contextmanager
    def failing_mutate(*args, backup_observer=None, **kwargs):
        backup_observer(backup_dir)
        yield object()

    def fail_write(*args):
        anlz.write_bytes(b"corrupt-anlz")
        raise RuntimeError("database commit failed")

    monkeypatch.setattr(event_delete, "mutate", failing_mutate)
    monkeypatch.setattr(event_delete, "_execute_rekordbox_plan", fail_write)
    monkeypatch.setattr(event_delete, "_db_plan_committed", lambda *args: False)
    monkeypatch.setattr(event_delete, "assert_mutation_ready", lambda *args: None)
    with pytest.raises(RuntimeError, match="commit failed"):
        event_delete.delete_event(
            conn,
            db_path,
            tmp_path / "backups",
            FakeCache(),
            tmp_path / "storage",
            event,
            dry_run=False,
            plan=plan,
        )
    assert anlz.read_bytes() == b"original-anlz"
    assert source.is_file()
    assert not destination.exists()
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event["id"],)).fetchone()
    assert row is not None and row["delete_plan"] is None
