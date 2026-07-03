"""The single Rekordbox mutation path (SPEC-UNIFIED 3.1/5.1, SPEC-01 1.2,
poc/09 verdict).

Every write to master.db goes through :func:`mutate` - no escape hatch:
guard (Rekordbox closed, optional snapshot freshness) -> timestamped
backup -> open -> yield -> commit + snapshot-cache invalidation; on
exception rollback and re-raise; always close.
"""

from contextlib import contextmanager
from importlib import import_module
from pathlib import Path

from syncbox.safety.backup import create_backup


class StaleSnapshotError(RuntimeError):
    """master.db changed after the dry-run snapshot was taken.

    Nothing was written and no backup was created; the caller must run a
    fresh dry-run and retry (SPEC-UNIFIED 5.11 freshness guard).
    """


def _assert_mutation_ready(db_path: Path) -> None:
    # process_guard ships as its own safety module; resolving it at call time
    # keeps import order across safety modules flat and gives tests a seam
    # (sys.modules) to substitute the guard.
    import_module("syncbox.safety.process_guard").assert_mutation_ready(db_path)


def fingerprint(db_path) -> tuple:
    """Freshness fingerprint of master.db(+wal): hashable, cache-key safe."""
    db_path = Path(db_path)
    stat = db_path.stat()
    parts = ((stat.st_mtime_ns, stat.st_size),)
    # ponytail: the wal component is included ONLY when the wal exists AND is
    # non-empty - "wal absent" == "wal empty". Measured in poc/09 (APFS +
    # sqlcipher): closing the last rw connection checkpoints and DELETES
    # master.db-wal, and a bare mode=ro open RECREATES a 0-byte wal, so a
    # literal "(mtime,size) of master.db(+wal)" fingerprint changes after
    # every read and would spuriously abort every mutate. An empty wal
    # carries no journal content; any real external write still flips the
    # master.db part (post-checkpoint) or grows the wal. Ceiling:
    # (mtime_ns, size) cannot see a same-size rewrite landing in the same
    # nanosecond; upgrade path is hashing file contents if that is ever
    # observed in practice.
    wal = db_path.with_name(db_path.name + "-wal")
    try:
        wal_stat = wal.stat()
    except FileNotFoundError:
        wal_stat = None
    if wal_stat is not None and wal_stat.st_size > 0:
        parts += ((wal_stat.st_mtime_ns, wal_stat.st_size),)
    return parts


@contextmanager
def mutate(
    db_path,
    backups_root,
    *,
    retention: int = 15,
    expected_fingerprint=None,
    open_db,
    invalidate_cache=None,
):
    """Unit-of-work for one master.db mutation. The order is load-bearing:

    (a) assert Rekordbox closed and, when ``expected_fingerprint`` is given,
        that the database still matches the dry-run snapshot - both BEFORE
        any backup;
    (b) timestamped backup (rotation per ``retention``);
    (c) ``handle = open_db(db_path)``;
    (d) yield the handle to the mutation body;
    (e) commit, then ``invalidate_cache()`` when provided;
    on exception BEFORE the commit: rollback and re-raise; after a durable
    commit nothing is ever rolled back; finally: close (a close failure
    never masks the primary error nor a successful commit).

    ``open_db`` is injected (production passes the pyrekordbox opener) so
    the unit-of-work stays testable and remains the ONE mutation path.
    """
    db_path = Path(db_path)
    _assert_mutation_ready(db_path)
    if expected_fingerprint is not None and fingerprint(db_path) != expected_fingerprint:
        raise StaleSnapshotError(
            f"{db_path} changed since the dry-run snapshot; nothing was "
            "written and no backup was created. Run a fresh dry-run and retry."
        )
    # Accepted residual window: a non-Rekordbox external writer (e.g. a cloud
    # sync client resolving a conflict) can land between this check and
    # open_db. The check's placement (at entry, before backup/open) is what
    # SPEC-UNIFIED 5.11 and poc/09 specify; re-checking after open risks
    # spurious aborts from SQLite's own wal recovery at open. The backup
    # taken below still covers whatever state gets mutated.
    create_backup(db_path, backups_root, retention=retention)
    handle = open_db(db_path)
    committed = False
    failing = False
    try:
        yield handle
        handle.commit()
        committed = True
        # After a durable commit there is nothing to roll back: an exception
        # from here on (invalidate_cache, a late KeyboardInterrupt) must
        # propagate WITHOUT taking the rollback path — the caller must never
        # be told "rolled back" when the commit stuck.
        if invalidate_cache is not None:
            invalidate_cache()
    except BaseException:
        failing = True
        if not committed:
            try:
                handle.rollback()
            except Exception:
                # Secondary failure (e.g. dead connection) while the original
                # error is propagating; nothing was committed, the original
                # error is the one the caller needs.
                pass
        raise
    finally:
        try:
            handle.close()
        except Exception:
            if failing or committed:
                # Never let a close failure mask the real error, or make a
                # durable commit look like a failed mutation.
                # ponytail: swallowed silently for now — route to the app
                # logger when M2 wires logging up.
                pass
            else:
                raise
