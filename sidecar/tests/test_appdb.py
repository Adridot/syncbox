"""Tests for the app DB migration runner (SPEC-UNIFIED 6.8, research 08 s.2)."""

import sqlite3

import pytest

from syncbox import appdb


def test_fresh_db_migrates_to_current_version(tmp_path):
    conn = appdb.open_app_db(tmp_path / "app.db")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version >= 1
    # settings table exists and is STRICT (insert of wrong shape fails)
    conn.execute("INSERT INTO settings (key, value) VALUES ('k', 'v')")
    assert conn.execute("SELECT value FROM settings WHERE key='k'").fetchone()[0] == "v"


def test_migrate_is_idempotent(tmp_path):
    conn = appdb.open_app_db(tmp_path / "app.db")
    before = conn.execute("PRAGMA user_version").fetchone()[0]
    assert appdb.migrate(conn) == before
    assert conn.execute("PRAGMA user_version").fetchone()[0] == before


def test_failing_migration_rolls_back_atomically(tmp_path, monkeypatch):
    conn = appdb.open_app_db(tmp_path / "app.db")
    v1 = conn.execute("PRAGMA user_version").fetchone()[0]
    real = appdb._scripts()
    bad = real + [
        (
            v1 + 1,
            f"{v1 + 1:04d}_bad.sql",
            "CREATE TABLE half_done (x TEXT) STRICT;\nTHIS IS NOT SQL;\n",
        )
    ]
    monkeypatch.setattr(appdb, "_scripts", lambda: bad)
    with pytest.raises(sqlite3.OperationalError):
        appdb.migrate(conn)
    # version unchanged AND the partial table did not survive
    assert conn.execute("PRAGMA user_version").fetchone()[0] == v1
    tables = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "half_done" not in tables


def test_broken_numbering_is_rejected(monkeypatch, tmp_path):
    conn = appdb.connect(tmp_path / "app.db")
    fake = [
        (1, "0001_a.sql", "CREATE TABLE a (x TEXT) STRICT;"),
        (3, "0003_c.sql", "CREATE TABLE c (x TEXT) STRICT;"),
    ]

    def scripts_with_gap():
        for position, (version, name, _) in enumerate(fake, start=1):
            if version != position:
                raise RuntimeError(f"migration numbering broken at {name!r}")
        return fake

    monkeypatch.setattr(appdb, "_scripts", scripts_with_gap)
    with pytest.raises(RuntimeError, match="numbering broken"):
        appdb.migrate(conn)


def test_real_numbering_is_contiguous():
    scripts = appdb._scripts()
    assert scripts, "at least migration 0001 must exist"
    assert [v for v, _, _ in scripts] == list(range(1, len(scripts) + 1))


def test_statement_splitter_handles_strings_and_comments():
    sql = (
        "-- header comment\n"
        "CREATE TABLE t (x TEXT);\n"
        "INSERT INTO t VALUES ('semi;colon; inside');\n"
        "-- trailing comment\n"
    )
    stmts = list(appdb._statements(sql))
    assert len(stmts) == 2
    assert "semi;colon; inside" in stmts[1]


def test_statement_splitter_rejects_unterminated_tail():
    with pytest.raises(ValueError, match="unterminated"):
        list(appdb._statements("CREATE TABLE t (x TEXT)"))


def test_connect_is_manual_transaction_mode(tmp_path):
    conn = appdb.connect(tmp_path / "app.db")
    assert conn.isolation_level is None  # autocommit; BEGIN/COMMIT are ours
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


# --- all-data export / import (SPEC-UNIFIED 5.10) -----------------------------


def test_export_import_round_trip(tmp_path):
    db = tmp_path / "app.db"
    conn = appdb.open_app_db(db)
    conn.execute("INSERT INTO settings (key, value) VALUES ('language', '\"fr\"')")
    exported = appdb.export_data(conn, tmp_path / "export" / "syncbox-export.db")
    assert exported.is_file()

    # wipe the live db, then import the export back
    conn.close()
    db.unlink()
    fresh = appdb.open_app_db(db)
    fresh.close()
    safety = appdb.import_data(db, exported)
    assert safety is not None and safety.exists()  # pre-import backup taken
    conn2 = appdb.open_app_db(db)
    row = conn2.execute("SELECT value FROM settings WHERE key='language'").fetchone()
    assert row[0] == '"fr"'


def test_import_rejects_corrupt_file(tmp_path):
    db = tmp_path / "app.db"
    appdb.open_app_db(db).close()
    bogus = tmp_path / "bogus.db"
    bogus.write_bytes(b"this is not a sqlite database at all")
    import sqlite3 as _sq

    with pytest.raises((ValueError, _sq.DatabaseError)):
        appdb.import_data(db, bogus)
    # live db untouched
    conn = appdb.open_app_db(db)
    assert conn.execute("PRAGMA user_version").fetchone()[0] >= 1


def test_import_rejects_future_and_incomplete_syncbox_schema(tmp_path):
    db = tmp_path / "app.db"
    appdb.open_app_db(db).close()
    current = appdb._scripts()[-1][0]

    future = tmp_path / "future.db"
    with sqlite3.connect(future) as conn:
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(f"PRAGMA user_version = {current + 1}")
    with pytest.raises(ValueError, match="newer than supported"):
        appdb.import_data(db, future)

    incomplete = tmp_path / "incomplete.db"
    with sqlite3.connect(incomplete) as conn:
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(f"PRAGMA user_version = {current}")
    with pytest.raises(ValueError, match="canonical Syncbox schema"):
        appdb.import_data(db, incomplete)

    assert appdb.open_app_db(db).execute("PRAGMA user_version").fetchone()[0] == current


def test_import_handles_uri_characters_in_path(tmp_path):
    db = tmp_path / "app.db"
    conn = appdb.open_app_db(db)
    source = appdb.export_data(conn, tmp_path / "syncbox export ? #.db")
    conn.close()
    appdb.import_data(db, source)
    assert appdb.open_app_db(db).execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_import_rejects_the_live_database_as_its_own_source(tmp_path):
    db = tmp_path / "app.db"
    appdb.open_app_db(db).close()
    with pytest.raises(ValueError, match="live Syncbox database"):
        appdb.import_data(db, db)


def test_import_copy_failure_leaves_live_database_untouched(tmp_path, monkeypatch):
    db = tmp_path / "app.db"
    conn = appdb.open_app_db(db)
    conn.execute("INSERT INTO settings (key, value) VALUES ('language', '\"en\"')")
    source = appdb.export_data(conn, tmp_path / "source.db")
    conn.close()
    before = db.read_bytes()

    monkeypatch.setattr(
        appdb.shutil, "copy2", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("copy failed"))
    )
    with pytest.raises(OSError, match="copy failed"):
        appdb.import_data(db, source)

    assert db.read_bytes() == before
    assert not list(tmp_path.glob(".app.db.import-*.tmp"))


def test_import_replace_failure_keeps_original_and_safety_backup(tmp_path, monkeypatch):
    db = tmp_path / "app.db"
    conn = appdb.open_app_db(db)
    conn.execute("INSERT INTO settings (key, value) VALUES ('language', '\"en\"')")
    source = appdb.export_data(conn, tmp_path / "source.db")
    conn.close()
    before = db.read_bytes()

    monkeypatch.setattr(
        appdb.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("replace failed"))
    )
    with pytest.raises(OSError, match="replace failed"):
        appdb.import_data(db, source)

    assert db.read_bytes() == before
    backups = list(tmp_path.glob("app.db.pre-import-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == before
    assert not list(tmp_path.glob(".app.db.import-*.tmp"))


def test_export_refuses_overwrite(tmp_path):
    conn = appdb.open_app_db(tmp_path / "app.db")
    dest = tmp_path / "out.db"
    appdb.export_data(conn, dest)
    import sqlite3 as _sq

    with pytest.raises(_sq.OperationalError):
        appdb.export_data(conn, dest)
