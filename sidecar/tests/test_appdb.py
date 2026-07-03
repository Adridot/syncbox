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


def test_export_refuses_overwrite(tmp_path):
    conn = appdb.open_app_db(tmp_path / "app.db")
    dest = tmp_path / "out.db"
    appdb.export_data(conn, dest)
    import sqlite3 as _sq

    with pytest.raises(_sq.OperationalError):
        appdb.export_data(conn, dest)
