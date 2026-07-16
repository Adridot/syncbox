"""Tests for timestamped backup / rotation / restore (SPEC-01 1.3, POC 09).

All tests run on dummy files in tmp dirs; none requires the real fixture.
"""

import sys
import sqlite3
import types
from pathlib import Path

import pytest

from syncbox.safety import backup


# --- helpers ---------------------------------------------------------------


def install_fake_guard(monkeypatch, exc=None):
    """Substitute syncbox.safety.process_guard with a recording fake.

    The guard module is delivered separately; backup.py resolves it at call
    time through sys.modules, which is exactly the seam patched here.
    """
    mod = types.ModuleType("syncbox.safety.process_guard")
    calls = []

    def assert_mutation_ready(db_path):
        calls.append(Path(db_path))
        if exc is not None:
            raise exc

    mod.assert_mutation_ready = assert_mutation_ready
    mod.calls = calls
    monkeypatch.setitem(sys.modules, "syncbox.safety.process_guard", mod)
    return mod


def freeze_timestamp(monkeypatch, *stamps):
    """Pin backup._timestamp: one fixed stamp, or a sequence consumed in order."""
    if len(stamps) == 1:
        monkeypatch.setattr(backup, "_timestamp", lambda: stamps[0])
    else:
        it = iter(stamps)
        monkeypatch.setattr(backup, "_timestamp", lambda: next(it))


def backup_names(backups_root):
    return sorted(p.name for p in backups_root.iterdir())


@pytest.fixture
def db(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    path = live / "master.db"
    path.write_bytes(b"main-v1")
    (live / "master.db-wal").write_bytes(b"wal-v1")
    (live / "master.db-shm").write_bytes(b"shm-v1")
    return path


@pytest.fixture
def backups_root(tmp_path):
    return tmp_path / "backups"


# --- create_backup ---------------------------------------------------------


class TestCreateBackup:
    def test_copies_db_wal_shm_into_timestamped_dir(
        self, db, backups_root, monkeypatch
    ):
        freeze_timestamp(monkeypatch, "20260702-120000")
        dest = backup.create_backup(db, backups_root)
        assert dest == backups_root / "rekordbox-db-20260702-120000"
        assert (dest / "master.db").read_bytes() == b"main-v1"
        assert (dest / "master.db-wal").read_bytes() == b"wal-v1"
        assert (dest / "master.db-shm").read_bytes() == b"shm-v1"

    def test_wal_and_shm_copied_only_when_present(self, db, backups_root):
        db.with_name("master.db-wal").unlink()
        db.with_name("master.db-shm").unlink()
        dest = backup.create_backup(db, backups_root)
        assert (dest / "master.db").read_bytes() == b"main-v1"
        assert not (dest / "master.db-wal").exists()
        assert not (dest / "master.db-shm").exists()

    def test_missing_db_raises_and_creates_nothing(self, tmp_path, backups_root):
        with pytest.raises(FileNotFoundError):
            backup.create_backup(tmp_path / "absent.db", backups_root)
        assert not backups_root.exists()

    def test_same_second_collision_gets_numeric_suffix(
        self, db, backups_root, monkeypatch
    ):
        # POC 09 measured this really happens within one wall-clock second.
        freeze_timestamp(monkeypatch, "20260702-120000")
        first = backup.create_backup(db, backups_root)
        second = backup.create_backup(db, backups_root)
        third = backup.create_backup(db, backups_root)
        assert first.name == "rekordbox-db-20260702-120000"
        assert second.name == "rekordbox-db-20260702-120000-2"
        assert third.name == "rekordbox-db-20260702-120000-3"
        for dest in (first, second, third):
            assert (dest / "master.db").read_bytes() == b"main-v1"

    def test_copies_rekordbox_support_files_with_relative_layout(
        self, db, backups_root
    ):
        anlz = db.parent / "share" / "PIONEER" / "ANLZ0000.DAT"
        anlz.parent.mkdir(parents=True)
        anlz.write_bytes(b"anlz-v1")
        destination = backup.create_backup(db, backups_root, extra_files=[anlz])
        backed = destination / "extra" / anlz.relative_to(db.parent)
        assert backed.read_bytes() == b"anlz-v1"
        listing = backup.list_backups(backups_root)[0]
        assert str(backed.relative_to(destination)) in listing["files"]

    def test_rejects_extra_files_outside_database_directory(
        self, db, backups_root, tmp_path
    ):
        outside = tmp_path / "outside.DAT"
        outside.write_bytes(b"unsafe")
        with pytest.raises(ValueError, match="database directory"):
            backup.create_backup(db, backups_root, extra_files=[outside])
        assert not backups_root.exists()

    def test_restore_extra_files_rejects_missing_required_support_file(
        self, db, backups_root
    ):
        destination = backup.create_backup(db, backups_root)
        required = db.parent / "share" / "PIONEER" / "ANLZ0000.DAT"
        with pytest.raises(FileNotFoundError, match="required support files"):
            backup.restore_extra_files(
                destination,
                db,
                required_files=[required],
            )

    def test_includes_a_verified_syncbox_database_snapshot(
        self, db, backups_root, tmp_path
    ):
        app_db = tmp_path / "syncbox.db"
        connection = sqlite3.connect(app_db)
        connection.execute("CREATE TABLE state (value TEXT)")
        connection.execute("INSERT INTO state VALUES ('before')")
        connection.commit()
        connection.close()

        destination = backup.create_backup(
            db,
            backups_root,
            app_db_path=app_db,
            reason="event_delete",
        )

        snapshot = destination / "syncbox" / "syncbox.db"
        assert snapshot.is_file()
        probe = sqlite3.connect(snapshot)
        try:
            assert probe.execute("SELECT value FROM state").fetchone()[0] == "before"
        finally:
            probe.close()
        listing = backup.list_backups(backups_root)[0]
        assert listing["verified"] is True
        assert listing["reason"] == "event_delete"


class TestRotation:
    def test_retention_zero_is_unlimited(self, db, backups_root, monkeypatch):
        stamps = [f"20260702-1200{i:02d}" for i in range(20)]
        freeze_timestamp(monkeypatch, *stamps)
        for _ in stamps:
            backup.create_backup(db, backups_root, retention=0)
        assert len(backup_names(backups_root)) == 20

    def test_exactly_n_backups_kept_untouched(self, db, backups_root, monkeypatch):
        freeze_timestamp(
            monkeypatch, "20260702-120000", "20260702-120001", "20260702-120002"
        )
        for _ in range(3):
            backup.create_backup(db, backups_root, retention=3)
        assert backup_names(backups_root) == [
            "rekordbox-db-20260702-120000",
            "rekordbox-db-20260702-120001",
            "rekordbox-db-20260702-120002",
        ]

    def test_n_plus_one_rotates_only_the_oldest(self, db, backups_root, monkeypatch):
        stamps = [f"20260702-12000{i}" for i in range(4)]
        freeze_timestamp(monkeypatch, *stamps)
        for _ in stamps:
            backup.create_backup(db, backups_root, retention=3)
        assert backup_names(backups_root) == [
            "rekordbox-db-20260702-120001",
            "rekordbox-db-20260702-120002",
            "rekordbox-db-20260702-120003",
        ]

    def test_just_created_backup_never_rotated_away(
        self, db, backups_root, monkeypatch
    ):
        freeze_timestamp(
            monkeypatch, "20260702-120000", "20260702-120001", "20260702-120002"
        )
        for _ in range(3):
            newest = backup.create_backup(db, backups_root, retention=1)
            assert backup_names(backups_root) == [newest.name]
        assert backup_names(backups_root) == ["rekordbox-db-20260702-120002"]

    def test_rotation_orders_collision_suffixes_numerically(
        self, db, backups_root, monkeypatch
    ):
        # "-10" must sort after "-9", not between the base name and "-2".
        freeze_timestamp(monkeypatch, "20260702-120000")
        for _ in range(11):
            backup.create_backup(db, backups_root, retention=0)
        backup.create_backup(db, backups_root, retention=3)
        assert backup_names(backups_root) == [
            "rekordbox-db-20260702-120000-10",
            "rekordbox-db-20260702-120000-11",
            "rekordbox-db-20260702-120000-12",
        ]

    def test_rotation_ignores_foreign_entries(self, db, backups_root, monkeypatch):
        backups_root.mkdir(parents=True)
        (backups_root / "notes.txt").write_text("keep me")
        (backups_root / "unrelated-dir").mkdir()
        freeze_timestamp(monkeypatch, "20260702-120000", "20260702-120001")
        backup.create_backup(db, backups_root, retention=1)
        backup.create_backup(db, backups_root, retention=1)
        assert backup_names(backups_root) == [
            "notes.txt",
            "rekordbox-db-20260702-120001",
            "unrelated-dir",
        ]

    def test_pending_event_backup_is_pinned_until_recovery_finishes(
        self, db, backups_root, monkeypatch
    ):
        freeze_timestamp(
            monkeypatch,
            "20260702-120000",
            "20260702-120001",
            "20260702-120002",
        )
        pending = backup.create_backup(db, backups_root, retention=1)
        marker = backup.pin_backup(pending)
        current = backup.create_backup(db, backups_root, retention=1)
        assert pending.is_dir() and current.is_dir() and marker.is_file()
        assert marker.name not in backup.list_backups(backups_root)[1]["files"]

        backup.unpin_backup(pending)
        newest = backup.create_backup(db, backups_root, retention=1)
        assert backup_names(backups_root) == [newest.name]

    def test_hourly_tier_preserves_history_beyond_the_recent_count(
        self, db, backups_root, monkeypatch
    ):
        freeze_timestamp(
            monkeypatch,
            "20260702-100000",
            "20260702-110000",
            "20260702-120000",
        )
        for _ in range(3):
            backup.create_backup(db, backups_root, retention=1)
        assert backup_names(backups_root) == [
            "rekordbox-db-20260702-100000",
            "rekordbox-db-20260702-110000",
            "rekordbox-db-20260702-120000",
        ]


# --- restore_backup --------------------------------------------------------


class TestRestoreValidation:
    @pytest.mark.parametrize(
        "name",
        ["", ".", "..", "a/b", "a" + chr(92) + "b", "../evil", "/etc", "nested/../x"],
    )
    def test_rejects_malformed_names_before_touching_anything(
        self, db, backups_root, monkeypatch, name
    ):
        guard = install_fake_guard(monkeypatch)
        existing = backup.create_backup(db, backups_root)
        with pytest.raises(ValueError):
            backup.restore_backup(name, backups_root, db)
        assert guard.calls == []  # rejected before the guard, before any snapshot
        assert backup_names(backups_root) == [existing.name]
        assert db.read_bytes() == b"main-v1"

    def test_rejects_symlink_escaping_backups_root(
        self, db, backups_root, tmp_path, monkeypatch
    ):
        guard = install_fake_guard(monkeypatch)
        backup.create_backup(db, backups_root)
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "master.db").write_bytes(b"attacker")
        (backups_root / "escape").symlink_to(outside)
        with pytest.raises(ValueError):
            backup.restore_backup("escape", backups_root, db)
        assert guard.calls == []
        assert db.read_bytes() == b"main-v1"

    def test_missing_backup_name_raises(self, db, backups_root, monkeypatch):
        install_fake_guard(monkeypatch)
        backup.create_backup(db, backups_root)
        with pytest.raises(FileNotFoundError):
            backup.restore_backup("rekordbox-db-19990101-000000", backups_root, db)

    def test_backup_dir_without_db_file_raises_before_snapshot(
        self, db, backups_root, monkeypatch
    ):
        guard = install_fake_guard(monkeypatch)
        backups_root.mkdir(parents=True)
        (backups_root / "rekordbox-db-20260101-000000").mkdir()
        with pytest.raises(FileNotFoundError):
            backup.restore_backup("rekordbox-db-20260101-000000", backups_root, db)
        assert guard.calls == []
        assert backup_names(backups_root) == ["rekordbox-db-20260101-000000"]

    def test_requires_rekordbox_closed(self, db, backups_root, monkeypatch):
        target = backup.create_backup(db, backups_root)
        install_fake_guard(monkeypatch, exc=RuntimeError("Rekordbox is running"))
        before = backup_names(backups_root)
        with pytest.raises(RuntimeError, match="running"):
            backup.restore_backup(target.name, backups_root, db)
        assert backup_names(backups_root) == before  # no pre-restore snapshot taken
        assert db.read_bytes() == b"main-v1"


class TestRestoreBehavior:
    def test_snapshots_current_db_first_then_copies_back(
        self, db, backups_root, monkeypatch
    ):
        install_fake_guard(monkeypatch)
        freeze_timestamp(monkeypatch, "20260702-120000", "20260702-120100")
        target = backup.create_backup(db, backups_root)

        # The live database moves on after the backup was taken.
        db.write_bytes(b"main-v2")
        db.with_name("master.db-wal").write_bytes(b"wal-v2")
        db.with_name("master.db-shm").write_bytes(b"shm-v2")

        snapshot = backup.restore_backup(target.name, backups_root, db)

        # Pre-restore snapshot holds the v2 state: the restore is reversible.
        assert snapshot.name == "rekordbox-db-20260702-120100"
        assert (snapshot / "master.db").read_bytes() == b"main-v2"
        assert (snapshot / "master.db-wal").read_bytes() == b"wal-v2"

        # Live state is back to v1, wal included (the backup carried one).
        assert db.read_bytes() == b"main-v1"
        assert db.with_name("master.db-wal").read_bytes() == b"wal-v1"
        assert db.with_name("master.db-shm").read_bytes() == b"shm-v1"

    def test_clears_live_wal_shm_when_backup_has_none(
        self, db, backups_root, monkeypatch
    ):
        install_fake_guard(monkeypatch)
        db.with_name("master.db-wal").unlink()
        db.with_name("master.db-shm").unlink()
        target = backup.create_backup(db, backups_root)  # db only, no wal/shm

        db.write_bytes(b"main-v2")
        db.with_name("master.db-wal").write_bytes(b"stale-wal")
        db.with_name("master.db-shm").write_bytes(b"stale-shm")

        backup.restore_backup(target.name, backups_root, db)

        assert db.read_bytes() == b"main-v1"
        # A stale wal would replay foreign journal content over the restored db.
        assert not db.with_name("master.db-wal").exists()
        assert not db.with_name("master.db-shm").exists()

    def test_restore_snapshot_is_never_rotated_away(
        self, db, backups_root, monkeypatch
    ):
        # Even with many existing backups, restoring must not rotate: rotation
        # here could delete the very backup being restored.
        install_fake_guard(monkeypatch)
        stamps = [f"20260702-1200{i:02d}" for i in range(17)]
        freeze_timestamp(monkeypatch, *stamps)
        oldest = backup.create_backup(db, backups_root, retention=0)
        for _ in range(15):
            backup.create_backup(db, backups_root, retention=0)
        db.write_bytes(b"main-v2")
        snapshot = backup.restore_backup(oldest.name, backups_root, db)
        names = backup_names(backups_root)
        assert oldest.name in names
        assert snapshot.name in names
        assert len(names) == 17
        assert db.read_bytes() == b"main-v1"

    def test_restore_includes_anlz_and_snapshots_current_anlz(
        self, db, backups_root, monkeypatch
    ):
        install_fake_guard(monkeypatch)
        freeze_timestamp(monkeypatch, "20260702-120000", "20260702-120100")
        anlz = db.parent / "share" / "PIONEER" / "ANLZ0000.DAT"
        anlz.parent.mkdir(parents=True)
        anlz.write_bytes(b"anlz-v1")
        target = backup.create_backup(db, backups_root, extra_files=[anlz])

        db.write_bytes(b"main-v2")
        anlz.write_bytes(b"anlz-v2")
        snapshot = backup.restore_backup(target.name, backups_root, db)

        assert anlz.read_bytes() == b"anlz-v1"
        backed_current = snapshot / "extra" / anlz.relative_to(db.parent)
        assert backed_current.read_bytes() == b"anlz-v2"


# --- fix-round regression tests (adversarial review findings) ----------------


def test_retention_default_is_20_everywhere():
    # The recent tier keeps 20 snapshots before hourly/daily/weekly/monthly thinning.
    import inspect

    from syncbox.safety import mutate as mutate_mod

    assert inspect.signature(backup.create_backup).parameters["retention"].default == 20
    assert inspect.signature(mutate_mod.mutate).parameters["retention"].default == 20


def test_failed_copy_leaves_no_backup_dir(db, tmp_path, monkeypatch):
    # A copy dying half-way must never leave a truncated dir that passes for a
    # valid backup (it would poison rotation and be restorable over a live DB).
    import shutil as shutil_mod

    backups_root = tmp_path / "backups"
    real_copy2 = shutil_mod.copy2
    calls = []

    def failing_copy2(src, dst, **kw):
        calls.append(dst)
        if len(calls) == 2:  # the db copy succeeded; fail on the wal copy
            raise OSError(28, "No space left on device")
        return real_copy2(src, dst, **kw)

    monkeypatch.setattr(backup.shutil, "copy2", failing_copy2)
    with pytest.raises(OSError):
        backup.create_backup(db, backups_root)
    leftovers = [p.name for p in backups_root.iterdir()]
    assert not [n for n in leftovers if n.startswith(backup._PREFIX)]
    assert not [n for n in leftovers if n.startswith(".incoming-")]


def test_restore_without_live_db(db, tmp_path, monkeypatch):
    # Disaster path: master.db deleted/lost. Restore must still work (that is
    # what it exists for); snapshot-first is vacuous with nothing to snapshot.
    backups_root = tmp_path / "backups"
    made = backup.create_backup(db, backups_root)
    db.unlink()
    db.with_name(db.name + "-wal").unlink()
    db.with_name(db.name + "-shm").unlink()
    install_fake_guard(monkeypatch, exc=FileNotFoundError("no live db"))
    snapshot = backup.restore_backup(made.name, backups_root, db)
    assert snapshot is None
    assert db.read_bytes() == b"main-v1"


def test_restore_replaces_rekordbox_and_syncbox_state_together(
    db, tmp_path, monkeypatch
):
    backups_root = tmp_path / "backups"
    app_db = tmp_path / "syncbox.db"
    connection = sqlite3.connect(app_db)
    connection.execute("CREATE TABLE state (value TEXT)")
    connection.execute("INSERT INTO state VALUES ('before')")
    connection.commit()
    connection.close()
    made = backup.create_backup(db, backups_root, app_db_path=app_db)

    db.write_bytes(b"main-v2")
    connection = sqlite3.connect(app_db)
    connection.execute("UPDATE state SET value = 'after'")
    connection.commit()
    connection.close()
    install_fake_guard(monkeypatch)

    backup.restore_backup(made.name, backups_root, db, app_db_path=app_db)

    assert db.read_bytes() == b"main-v1"
    connection = sqlite3.connect(app_db)
    try:
        assert connection.execute("SELECT value FROM state").fetchone()[0] == "before"
    finally:
        connection.close()


def test_coherent_restore_rejects_rekordbox_only_backup(db, tmp_path):
    backups_root = tmp_path / "backups"
    app_db = tmp_path / "syncbox.db"
    connection = sqlite3.connect(app_db)
    connection.execute("CREATE TABLE state (value TEXT)")
    connection.commit()
    connection.close()
    made = backup.create_backup(db, backups_root)

    with pytest.raises(ValueError, match="coherent Syncbox database"):
        backup.restore_backup(made.name, backups_root, db, app_db_path=app_db)


def test_restore_copy_failure_leaves_live_db_intact(db, tmp_path, monkeypatch):
    # os.replace is atomic: a failure while copying the backup must leave the
    # live master.db byte-identical (old), never torn, and no tmp junk behind.
    import shutil as shutil_mod

    backups_root = tmp_path / "backups"
    install_fake_guard(monkeypatch)
    made = backup.create_backup(db, backups_root)
    db.write_bytes(b"main-v2")
    real_copy2 = shutil_mod.copy2

    def failing_copy2(src, dst, **kw):
        if str(dst).endswith(".restore-tmp"):
            raise OSError(5, "I/O error")
        return real_copy2(src, dst, **kw)

    monkeypatch.setattr(backup.shutil, "copy2", failing_copy2)
    with pytest.raises(OSError):
        backup.restore_backup(made.name, backups_root, db)
    assert db.read_bytes() == b"main-v2"
    assert not list(db.parent.glob("*.restore-tmp"))
    # The pre-restore snapshot exists and captured the current db AND its wal
    # (the live wal is cleared before the copy; the snapshot preserves it).
    snapshots = [
        p
        for p in backups_root.iterdir()
        if p.name.startswith(backup._PREFIX) and p != made
    ]
    assert len(snapshots) == 1
    assert (snapshots[0] / "master.db").read_bytes() == b"main-v2"
    assert (snapshots[0] / "master.db-wal").read_bytes() == b"wal-v1"


def test_restore_failure_removes_staged_syncbox_database(db, tmp_path, monkeypatch):
    # Staging failure (here: while snapshotting the app DB into its staged
    # sibling) must unstage everything and leave every live file untouched.
    backups_root = tmp_path / "backups"
    app_db = tmp_path / "syncbox.db"
    connection = sqlite3.connect(app_db)
    connection.execute("CREATE TABLE state (value TEXT)")
    connection.commit()
    connection.close()
    made = backup.create_backup(db, backups_root, app_db_path=app_db)
    install_fake_guard(monkeypatch)
    db.write_bytes(b"main-v2")
    live_app_bytes = app_db.read_bytes()

    real_snapshot_sqlite = backup._snapshot_sqlite

    def failing_snapshot(source, destination):
        if str(destination).endswith(".restore-tmp"):
            raise OSError("restore failed")
        return real_snapshot_sqlite(source, destination)

    monkeypatch.setattr(backup, "_snapshot_sqlite", failing_snapshot)
    with pytest.raises(OSError, match="restore failed"):
        backup.restore_backup(made.name, backups_root, db, app_db_path=app_db)

    assert not app_db.with_name(app_db.name + ".restore-tmp").exists()
    assert not list(db.parent.glob("*.restore-tmp"))
    # Nothing was published and no journal is pending: live pair untouched.
    assert db.read_bytes() == b"main-v2"
    assert app_db.read_bytes() == live_app_bytes
    assert not (tmp_path / backup._RESTORE_JOURNAL).exists()


# --- PR #31 review regression tests ------------------------------------------


def _make_app_db(path, value="before"):
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE state (value TEXT)")
    connection.execute("INSERT INTO state VALUES (?)", (value,))
    connection.commit()
    connection.close()


def _app_value(path):
    connection = sqlite3.connect(path)
    try:
        return connection.execute("SELECT value FROM state").fetchone()[0]
    finally:
        connection.close()


def _set_app_value(path, value):
    connection = sqlite3.connect(path)
    connection.execute("UPDATE state SET value = ?", (value,))
    connection.commit()
    connection.close()


def test_unmanifested_extra_master_db_is_rejected(db, tmp_path, monkeypatch):
    """Review P1: a file absent from the manifest fails the whole restore —
    an undeclared extra/master.db would otherwise overwrite the verified
    database after restoration."""
    backups_root = tmp_path / "backups"
    app_db = tmp_path / "syncbox.db"
    _make_app_db(app_db)
    made = backup.create_backup(db, backups_root, app_db_path=app_db)
    install_fake_guard(monkeypatch)
    db.write_bytes(b"main-v2")

    smuggled = made / "extra" / "master.db"
    smuggled.parent.mkdir(exist_ok=True)
    smuggled.write_bytes(b"attacker bytes")

    with pytest.raises(ValueError, match="missing from its manifest"):
        backup.restore_backup(made.name, backups_root, db, app_db_path=app_db)

    assert db.read_bytes() == b"main-v2"
    assert _app_value(app_db) == "before"


def test_declared_extra_may_never_target_the_databases(db, tmp_path):
    """Review P1: even a manifest-declared extra must not resolve onto
    master.db, its wal/shm, or the Syncbox DB."""
    backup_dir = tmp_path / "crafted"
    (backup_dir / "extra").mkdir(parents=True)
    (backup_dir / "extra" / "master.db").write_bytes(b"attacker bytes")
    app_db = tmp_path / "syncbox.db"

    with pytest.raises(ValueError, match="protected database file"):
        backup._backed_extra_targets(backup_dir, db, app_db_path=app_db)


def test_restore_error_between_master_and_syncbox_rolls_back_the_pair(
    db, tmp_path, monkeypatch
):
    """Review P1: a synchronous failure after master.db was replaced but
    before syncbox.db rolls the WHOLE pair back to the pre-restore state."""
    backups_root = tmp_path / "backups"
    app_db = tmp_path / "syncbox.db"
    _make_app_db(app_db)
    made = backup.create_backup(db, backups_root, app_db_path=app_db)
    install_fake_guard(monkeypatch)

    db.write_bytes(b"main-v2")
    _set_app_value(app_db, "after")

    real_replace = backup.os.replace
    failures = []

    def failing_replace(src, dst):
        if str(dst) == str(app_db) and not failures:
            failures.append(dst)
            raise OSError(5, "I/O error")
        return real_replace(src, dst)

    monkeypatch.setattr(backup.os, "replace", failing_replace)
    with pytest.raises(OSError):
        backup.restore_backup(made.name, backups_root, db, app_db_path=app_db)

    # Rolled back as one unit: Rekordbox AND Syncbox are at the pre-restore
    # epoch, nothing is staged, no journal is pending.
    assert db.read_bytes() == b"main-v2"
    assert _app_value(app_db) == "after"
    assert not list(db.parent.glob("*.restore-tmp"))
    assert not list(tmp_path.glob("*.restore-tmp"))
    assert not (tmp_path / backup._RESTORE_JOURNAL).exists()


def test_crash_between_master_and_syncbox_replacements_rolls_forward(
    db, tmp_path, monkeypatch
):
    """Review P1: with the journal durable and the staged set intact, a crash
    between the two database replacements completes the pair at recovery."""
    backups_root = tmp_path / "backups"
    app_db = tmp_path / "syncbox.db"
    _make_app_db(app_db)
    made = backup.create_backup(db, backups_root, app_db_path=app_db)
    install_fake_guard(monkeypatch)

    db.write_bytes(b"main-v2")
    _set_app_value(app_db, "after")

    # Reproduce the exact crash window: stage + journal, replace ONLY
    # master.db, then die before syncbox.db is published.
    replacements, removals = backup._stage_restore(made, db, app_db)
    backup._write_restore_journal(
        tmp_path,
        {
            "schema": 1,
            "created_at": "2026-07-16T00:00:00",
            "source": str(made),
            "snapshot": None,
            "db_path": str(db),
            "app_db_path": str(app_db),
            "replacements": replacements,
            "removals": removals,
        },
    )
    backup.os.replace(db.with_name(db.name + ".restore-tmp"), db)

    assert backup.recover_restore(tmp_path) == "completed"

    assert db.read_bytes() == b"main-v1"
    assert _app_value(app_db) == "before"
    assert not (tmp_path / backup._RESTORE_JOURNAL).exists()
    assert not list(db.parent.glob("*.restore-tmp"))
    assert not list(tmp_path.glob("*.restore-tmp"))


def test_unrecoverable_staged_set_rolls_back_to_the_snapshot(
    db, tmp_path, monkeypatch
):
    """Review P1: when the staged set was lost mid-publish, recovery restores
    the pre-restore snapshot — the pair never stays mixed across epochs."""
    backups_root = tmp_path / "backups"
    app_db = tmp_path / "syncbox.db"
    _make_app_db(app_db)
    made = backup.create_backup(db, backups_root, app_db_path=app_db)
    install_fake_guard(monkeypatch)
    freeze_timestamp(monkeypatch, "20260716-120000")

    db.write_bytes(b"main-v2")
    _set_app_value(app_db, "after")
    snapshot = backup.create_backup(
        db, backups_root, retention=0, app_db_path=app_db, reason="pre_restore"
    )

    replacements, removals = backup._stage_restore(made, db, app_db)
    backup._write_restore_journal(
        tmp_path,
        {
            "schema": 1,
            "created_at": "2026-07-16T00:00:00",
            "source": str(made),
            "snapshot": str(snapshot),
            "db_path": str(db),
            "app_db_path": str(app_db),
            "replacements": replacements,
            "removals": removals,
        },
    )
    # Crash story: master.db was already replaced by the OLD backup bytes,
    # then the remaining staged files were lost (disk cleanup, corruption).
    backup.os.replace(db.with_name(db.name + ".restore-tmp"), db)
    app_staged = app_db.with_name(app_db.name + ".restore-tmp")
    app_staged.unlink()
    # Make roll-forward impossible for the app DB (staged gone, target old).
    assert backup.recover_restore(tmp_path) == "rolled_back"

    assert db.read_bytes() == b"main-v2"
    assert _app_value(app_db) == "after"
    assert not (tmp_path / backup._RESTORE_JOURNAL).exists()
