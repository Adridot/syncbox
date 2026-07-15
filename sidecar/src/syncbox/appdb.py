"""Application database: plain SQLite + native PRAGMA user_version migrations
(SPEC-UNIFIED 6.8, research 08 section 2).

The app DB is cleartext SQLite (never master.db - no SQLCipher, no Rekordbox
guard in this layer). Migrations are forward-only ordered SQL scripts under
syncbox/migrations/; the seed is migration 0001, played exactly once (kills
the re-seed-at-boot bug class B4). The timestamped Rekordbox backup system is
unrelated; the safety net for this DB is the export/import VACUUM INTO path.
"""

import os
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime
from importlib import resources
from pathlib import Path

_SCRIPT_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


def connect(db_path) -> sqlite3.Connection:
    """Open the app DB in autocommit mode - transactions are driven manually.

    isolation_level=None is load-bearing: migrations issue explicit
    BEGIN/COMMIT, and cpython#112441 makes the implicit-transaction modes
    (legacy isolation levels, autocommit=False) fight explicit transaction
    control. Never combine this connection with executescript().
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: the HTTP layer (api.py) runs every handler in
    # a worker thread, all serialized behind one lock (api.Deps.lock), so the
    # connection is never used concurrently - only handed between threads,
    # which the default same-thread check would wrongly reject.
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _scripts() -> list[tuple[int, str, str]]:
    """Ordered migration scripts [(version, name, sql)], numbering validated."""
    pkg = resources.files("syncbox.migrations")
    found = []
    for entry in pkg.iterdir():
        match = _SCRIPT_NAME.match(entry.name)
        if match:
            found.append((int(match.group(1)), entry.name, entry.read_text()))
    found.sort()
    for position, (version, name, _) in enumerate(found, start=1):
        if version != position:
            raise RuntimeError(
                f"migration numbering broken at {name!r}: expected {position:04d}"
            )
    return found


def _statements(sql: str):
    """Split a script into executable statements via sqlite3.complete_statement.

    Correct for strings/comments without a SQL parser dependency; each
    statement in a migration must end with ';'. A trailing comment-only tail
    is ignored.
    """
    buf = ""
    for line in sql.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            stmt = buf.strip()
            if stmt:
                yield stmt
            buf = ""
    tail = buf.strip()
    if tail and not all(
        part.lstrip().startswith("--") for part in tail.splitlines() if part.strip()
    ):
        raise ValueError(f"migration ends with an unterminated statement: {tail[:80]!r}")


def migrate(conn: sqlite3.Connection) -> int:
    """Apply every migration above PRAGMA user_version; return the new version.

    Each script runs in ONE explicit transaction (BEGIN ... PRAGMA
    user_version = n ... COMMIT, rollback on failure), so a migration is
    all-or-nothing and the version bump commits atomically with its DDL.
    """
    scripts = _scripts()
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    latest = scripts[-1][0] if scripts else 0
    if current > latest:
        raise RuntimeError(
            f"database schema version {current} is newer than supported {latest}"
        )
    version = current
    for version_n, _name, sql in scripts[current:]:
        conn.execute("BEGIN")
        try:
            for stmt in _statements(sql):
                conn.execute(stmt)
            # PRAGMA takes no bound parameter; version_n comes from the
            # validated 4-digit filename, never user input.
            conn.execute(f"PRAGMA user_version = {int(version_n)}")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        version = version_n
    return version


def open_app_db(db_path) -> sqlite3.Connection:
    """Connect and migrate - the single entry point the service uses."""
    conn = connect(db_path)
    migrate(conn)
    return conn


def export_data(conn: sqlite3.Connection, dest) -> Path:
    """All-data export: VACUUM INTO writes ONE coherent snapshot file
    (SPEC-UNIFIED 5.10). Fails if dest already exists (VACUUM INTO refuses
    to overwrite - by design, no silent clobber)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    conn.execute("VACUUM INTO ?", (str(dest),))
    return dest


def import_data(db_path, source) -> Path | None:
    """Atomically import a validated DB after taking a durable safety backup.

    Returns the safety backup path. The incoming file is validated (it must
    open and pass integrity_check) before anything is touched. The source is
    copied and revalidated in the destination directory, then ``os.replace``
    publishes it atomically. Caller must reopen connections afterwards.
    """
    db_path = Path(db_path)
    source = Path(source).resolve(strict=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists() and source.samefile(db_path):
        raise ValueError("import source is the live Syncbox database")

    _validate_import_source(source)
    fd, staged_name = tempfile.mkstemp(
        prefix=f".{db_path.name}.import-", suffix=".tmp", dir=db_path.parent
    )
    os.close(fd)
    staged = Path(staged_name)
    try:
        shutil.copy2(source, staged)
        try:
            _prepare_import(staged)
        except sqlite3.DatabaseError as exc:
            raise ValueError("not a valid Syncbox data export") from exc
        _fsync_file(staged)

        backup = None
        if db_path.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup = db_path.with_name(f"{db_path.name}.pre-import-{stamp}")
            shutil.copy2(db_path, backup)
            _fsync_file(backup)

        os.replace(staged, db_path)
        _fsync_directory(db_path.parent)
        return backup
    finally:
        staged.unlink(missing_ok=True)


def _validate_import_source(path: Path) -> None:
    try:
        probe = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            _check_integrity(probe)
            current = probe.execute("PRAGMA user_version").fetchone()[0]
            latest = _scripts()[-1][0]
            if current > latest:
                raise ValueError(
                    f"import schema version {current} is newer than supported {latest}"
                )
            is_syncbox = probe.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'"
            ).fetchone()
            if not is_syncbox:
                raise ValueError("not a Syncbox data export")
        finally:
            probe.close()
    except sqlite3.DatabaseError as exc:
        raise ValueError("not a valid SQLite data export") from exc


def _prepare_import(path: Path) -> None:
    probe = connect(path)
    canonical = connect(":memory:")
    try:
        migrate(probe)
        migrate(canonical)
        _check_integrity(probe)
        if probe.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("import file failed foreign_key_check")
        if _schema(probe) != _schema(canonical):
            raise ValueError("import file does not have the canonical Syncbox schema")
    finally:
        probe.close()
        canonical.close()


def _check_integrity(conn: sqlite3.Connection) -> None:
    result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise ValueError(f"import file failed integrity_check: {result}")


def _schema(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
    ).fetchall()


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
