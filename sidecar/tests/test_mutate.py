"""Tests for the single mutation unit-of-work (SPEC-UNIFIED 3.1/5.1,
SPEC-01 1.2, poc/09 verdict).

Unit tests use fake handles and dummy files; the final integration test
needs the real poc/testdata/master.db fixture and is skipped without it.
"""

import os
import shutil
import sys
import types
from pathlib import Path

import pytest

from syncbox.safety import mutate as mutate_mod
from syncbox.safety import statuses
from syncbox.safety.mutate import StaleSnapshotError, fingerprint, mutate

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTDATA = REPO_ROOT / "poc" / "testdata"
FIXTURE = TESTDATA / "master.db"


# --- helpers ---------------------------------------------------------------


def install_fake_guard(monkeypatch, log=None, exc=None):
    """Substitute syncbox.safety.process_guard (resolved via sys.modules)."""
    mod = types.ModuleType("syncbox.safety.process_guard")
    calls = []

    def assert_mutation_ready(db_path):
        calls.append(Path(db_path))
        if log is not None:
            log.append("guard")
        if exc is not None:
            raise exc

    mod.assert_mutation_ready = assert_mutation_ready
    mod.calls = calls
    monkeypatch.setitem(sys.modules, "syncbox.safety.process_guard", mod)
    return mod


class FakeHandle:
    """Records commit/rollback/close order; commit can be armed to fail."""

    def __init__(self, log, commit_exc=None):
        self.log = log
        self.commit_exc = commit_exc

    def commit(self):
        self.log.append("commit")
        if self.commit_exc is not None:
            raise self.commit_exc

    def rollback(self):
        self.log.append("rollback")

    def close(self):
        self.log.append("close")


@pytest.fixture
def db(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    path = live / "master.db"
    path.write_bytes(b"main-v1")
    return path


@pytest.fixture
def backups_root(tmp_path):
    return tmp_path / "backups"


def backup_dirs(backups_root):
    if not backups_root.exists():
        return []
    return sorted(backups_root.glob("rekordbox-db-*"))


# --- fingerprint (poc/09 normalized APFS wal rule) --------------------------


class TestFingerprint:
    def test_fingerprint_survives_a_json_round_trip_verbatim(self, db):
        # The fingerprint crosses the UI as JSON and st_mtime_ns (~19 digits)
        # exceeds JavaScript's 2^53 Number precision — as ints, JSON.parse
        # rounds them and every execute aborts stale (live bug 2026-07-07).
        # Every leaf must be a string that round-trips verbatim.
        import json

        fp = fingerprint(db)
        assert all(isinstance(leaf, str) for part in fp for leaf in part)
        assert tuple(tuple(part) for part in json.loads(json.dumps(fp))) == fp

    def test_wal_absent_equals_wal_empty(self, db):
        # poc/09: a bare mode=ro open recreates a 0-byte wal; the fingerprint
        # must not change for it, or every mutate spuriously aborts.
        before = fingerprint(db)
        db.with_name("master.db-wal").write_bytes(b"")
        assert fingerprint(db) == before

    def test_non_empty_wal_changes_fingerprint(self, db):
        before = fingerprint(db)
        db.with_name("master.db-wal").write_bytes(b"journal")
        assert fingerprint(db) != before

    def test_db_size_change_changes_fingerprint(self, db):
        before = fingerprint(db)
        db.write_bytes(b"main-v1-and-more")
        assert fingerprint(db) != before

    def test_db_mtime_change_alone_changes_fingerprint(self, db):
        before = fingerprint(db)
        stat = db.stat()
        os.utime(db, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        assert fingerprint(db) != before

    def test_wal_growth_changes_fingerprint(self, db):
        wal = db.with_name("master.db-wal")
        wal.write_bytes(b"journal")
        before = fingerprint(db)
        wal.write_bytes(b"journal-grown")
        assert fingerprint(db) != before

    def test_fingerprint_is_hashable_and_stable(self, db):
        assert fingerprint(db) == fingerprint(db)
        assert {fingerprint(db): "cache-entry"}  # usable as a cache key

    def test_missing_db_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            fingerprint(tmp_path / "absent.db")


# --- mutate unit-of-work -----------------------------------------------------


class TestMutateSequencing:
    def test_exact_order_guard_backup_open_body_commit_invalidate_close(
        self, db, backups_root, monkeypatch
    ):
        log = []
        install_fake_guard(monkeypatch, log=log)
        monkeypatch.setattr(
            mutate_mod,
            "create_backup",
            lambda path, root, retention=15: log.append("backup"),
        )
        handle = FakeHandle(log)

        def open_db(path):
            log.append("open")
            return handle

        with mutate(
            db,
            backups_root,
            open_db=open_db,
            invalidate_cache=lambda: log.append("invalidate"),
        ) as h:
            assert h is handle
            log.append("body")

        assert log == ["guard", "backup", "open", "body", "commit", "invalidate", "close"]

    def test_guard_receives_db_path_and_runs_before_backup(
        self, db, backups_root, monkeypatch
    ):
        guard = install_fake_guard(monkeypatch)
        with mutate(db, backups_root, open_db=lambda p: FakeHandle([])):
            pass
        assert guard.calls == [db]

    def test_backup_exists_before_open_db_is_called(self, db, backups_root, monkeypatch):
        install_fake_guard(monkeypatch)
        seen = {}

        def open_db(path):
            seen["backups_at_open"] = backup_dirs(backups_root)
            return FakeHandle([])

        with mutate(db, backups_root, open_db=open_db):
            pass
        assert len(seen["backups_at_open"]) == 1
        assert (seen["backups_at_open"][0] / "master.db").read_bytes() == b"main-v1"

    def test_retention_is_forwarded_to_create_backup(self, db, backups_root, monkeypatch):
        install_fake_guard(monkeypatch)
        received = {}

        def fake_create_backup(path, root, retention=15):
            received["retention"] = retention

        monkeypatch.setattr(mutate_mod, "create_backup", fake_create_backup)
        with mutate(db, backups_root, retention=7, open_db=lambda p: FakeHandle([])):
            pass
        assert received["retention"] == 7

    def test_extra_backup_files_and_observer_run_before_open(
        self, db, backups_root, monkeypatch
    ):
        install_fake_guard(monkeypatch)
        anlz = db.parent / "share" / "ANLZ0000.DAT"
        anlz.parent.mkdir()
        anlz.write_bytes(b"anlz")
        log = []
        made = backups_root / "rekordbox-db-20260711-120000"

        def fake_create(path, root, retention=15, *, extra_files=()):
            assert list(extra_files) == [anlz]
            log.append("backup")
            return made

        monkeypatch.setattr(mutate_mod, "create_backup", fake_create)

        def open_db(path):
            log.append("open")
            return FakeHandle(log)

        with mutate(
            db,
            backups_root,
            open_db=open_db,
            backup_files=[anlz],
            backup_observer=lambda path: log.append(f"observed:{path.name}"),
        ):
            log.append("body")
        assert log == [
            "backup",
            f"observed:{made.name}",
            "open",
            "body",
            "commit",
            "close",
        ]

    def test_invalidate_cache_is_optional(self, db, backups_root, monkeypatch):
        install_fake_guard(monkeypatch)
        log = []
        with mutate(db, backups_root, open_db=lambda p: FakeHandle(log)):
            pass
        assert log == ["commit", "close"]


class TestMutateFailurePaths:
    def test_exception_rolls_back_closes_and_reraises_backup_kept(
        self, db, backups_root, monkeypatch
    ):
        install_fake_guard(monkeypatch)
        log = []

        class Boom(Exception):
            pass

        with pytest.raises(Boom):
            with mutate(
                db,
                backups_root,
                open_db=lambda p: FakeHandle(log),
                invalidate_cache=lambda: log.append("invalidate"),
            ):
                raise Boom()

        assert log == ["rollback", "close"]  # no commit, no cache invalidation
        assert len(backup_dirs(backups_root)) == 1  # the backup is the safety net

    def test_commit_failure_rolls_back_and_closes(self, db, backups_root, monkeypatch):
        install_fake_guard(monkeypatch)
        log = []

        class CommitBoom(Exception):
            pass

        with pytest.raises(CommitBoom):
            with mutate(
                db,
                backups_root,
                open_db=lambda p: FakeHandle(log, commit_exc=CommitBoom()),
                invalidate_cache=lambda: log.append("invalidate"),
            ):
                pass

        assert log == ["commit", "rollback", "close"]
        assert "invalidate" not in log

    def test_rb_running_aborts_before_backup_and_open(self, db, backups_root, monkeypatch):
        install_fake_guard(monkeypatch, exc=RuntimeError("Rekordbox is running"))

        def open_db(path):  # pragma: no cover - must never run
            raise AssertionError("open_db called despite guard abort")

        with pytest.raises(RuntimeError, match="running"):
            with mutate(db, backups_root, open_db=open_db):
                pass
        assert backup_dirs(backups_root) == []

    def test_stale_snapshot_aborts_before_backup_and_open(
        self, db, backups_root, monkeypatch
    ):
        log = []
        install_fake_guard(monkeypatch, log=log)
        expected = fingerprint(db)
        db.write_bytes(b"changed-by-rekordbox-meanwhile")

        def open_db(path):  # pragma: no cover - must never run
            raise AssertionError("open_db called despite stale snapshot")

        with pytest.raises(StaleSnapshotError, match="dry-run"):
            with mutate(db, backups_root, expected_fingerprint=expected, open_db=open_db):
                pass
        assert log == ["guard"]  # guard ran first; nothing else did
        assert backup_dirs(backups_root) == []  # and NO backup was created

    def test_matching_fingerprint_proceeds(self, db, backups_root, monkeypatch):
        install_fake_guard(monkeypatch)
        log = []
        with mutate(
            db,
            backups_root,
            expected_fingerprint=fingerprint(db),
            open_db=lambda p: FakeHandle(log),
        ):
            log.append("body")
        assert log == ["body", "commit", "close"]


# --- integration: real master.db round-trip (mirrors poc/05 verification) ---


@pytest.mark.skipif(not FIXTURE.is_file(), reason="poc/testdata/master.db fixture absent")
def test_integration_soft_delete_round_trip_on_real_db(tmp_path, monkeypatch):
    install_fake_guard(monkeypatch)
    sqlcipher3 = pytest.importorskip("sqlcipher3")
    pyrekordbox_db6 = pytest.importorskip("pyrekordbox.db6")
    from pyrekordbox.db6.database import BLOB
    from pyrekordbox.db6.tables import DjmdContent
    from pyrekordbox.utils import deobfuscate

    key = deobfuscate(BLOB)
    live = tmp_path / "live"
    live.mkdir()
    for name in ("master.db", "master.db-wal", "master.db-shm", "masterPlaylists6.xml"):
        src = TESTDATA / name
        if src.is_file():  # never touch the originals: copy into tmp_path
            shutil.copy2(src, live / name)
    db = live / "master.db"
    backups_root = tmp_path / "backups"

    def open_db(path):
        return pyrekordbox_db6.Rekordbox6Database(
            path=path, db_dir=live, key=key, unlock=True
        )

    def on_disk_tuple(content_id):
        """Independent sqlcipher read, as in poc/05: never trust the ORM view."""
        con = sqlcipher3.connect(str(db))
        try:
            con.execute(f"PRAGMA key = '{key}'")
            return con.execute(
                "SELECT rb_local_deleted, rb_local_synced, rb_data_status,"
                " rb_local_data_status FROM djmdContent WHERE ID = ?",
                (content_id,),
            ).fetchone()
        finally:
            con.close()

    # Soft-delete one active content row inside the unit-of-work.
    with mutate(
        db, backups_root, expected_fingerprint=fingerprint(db), open_db=open_db
    ) as handle:
        row = (
            handle.query(DjmdContent)
            .filter(
                DjmdContent.rb_local_deleted == 0,
                DjmdContent.rb_data_status == statuses.RB_DATA_STATUS_ACTIVE,
            )
            .first()
        )
        assert row is not None
        assert not statuses.is_soft_deleted(row)
        target_id = row.ID
        for field, value in statuses.soft_delete_values().items():
            setattr(row, field, value)

    assert on_disk_tuple(target_id) == (1, 0, 258, 0)

    # Reactivate through a second, independent unit-of-work.
    with mutate(
        db, backups_root, expected_fingerprint=fingerprint(db), open_db=open_db
    ) as handle:
        row = handle.query(DjmdContent).filter(DjmdContent.ID == target_id).one()
        assert statuses.is_soft_deleted(row)
        for field, value in statuses.reactivate_values().items():
            setattr(row, field, value)

    on_disk = on_disk_tuple(target_id)
    assert on_disk[0] == 0  # rb_local_deleted cleared
    assert on_disk[2] == 256  # rb_data_status back to active
    assert len(backup_dirs(backups_root)) == 2  # one backup per mutation


# --- fix-round regression tests (adversarial review findings) ----------------


class FlakyHandle(FakeHandle):
    """FakeHandle whose rollback/close can be armed to fail (secondary errors)."""

    def __init__(self, log, rollback_exc=None, close_exc=None, commit_exc=None):
        super().__init__(log, commit_exc=commit_exc)
        self.rollback_exc = rollback_exc
        self.close_exc = close_exc

    def rollback(self):
        super().rollback()
        if self.rollback_exc is not None:
            raise self.rollback_exc

    def close(self):
        super().close()
        if self.close_exc is not None:
            raise self.close_exc


def test_invalidate_failure_never_takes_rollback_path(db, backups_root, monkeypatch):
    # After a durable commit nothing may be rolled back: an invalidate_cache
    # failure propagates as itself, and the log shows no rollback call.
    install_fake_guard(monkeypatch)
    log = []
    handle = FakeHandle(log)

    def bad_invalidate():
        log.append("invalidate")
        raise RuntimeError("cache backend gone")

    with pytest.raises(RuntimeError, match="cache backend gone"):
        with mutate(
            db, backups_root, open_db=lambda p: handle, invalidate_cache=bad_invalidate
        ):
            pass
    assert log == ["commit", "invalidate", "close"]


def test_close_failure_after_commit_is_suppressed(db, backups_root, monkeypatch):
    # A close failure must never make a durable commit look like a failure.
    install_fake_guard(monkeypatch)
    log = []
    handle = FlakyHandle(log, close_exc=RuntimeError("close failed"))
    with mutate(db, backups_root, open_db=lambda p: handle):
        pass
    assert log == ["commit", "close"]


def test_rollback_failure_preserves_original_error(db, backups_root, monkeypatch):
    install_fake_guard(monkeypatch)
    log = []
    handle = FlakyHandle(log, rollback_exc=RuntimeError("dead connection"))
    with pytest.raises(ValueError, match="body failed"):
        with mutate(db, backups_root, open_db=lambda p: handle):
            raise ValueError("body failed")
    assert log == ["rollback", "close"]


def test_close_failure_with_body_error_preserves_original(db, backups_root, monkeypatch):
    install_fake_guard(monkeypatch)
    log = []
    handle = FlakyHandle(log, close_exc=RuntimeError("close failed"))
    with pytest.raises(ValueError, match="body failed"):
        with mutate(db, backups_root, open_db=lambda p: handle):
            raise ValueError("body failed")
    assert log == ["rollback", "close"]
