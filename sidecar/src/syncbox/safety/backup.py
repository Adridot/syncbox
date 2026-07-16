"""Timestamped Rekordbox database/support-file backups and safe restore
(SPEC-01 1.3, SPEC-UNIFIED 3.1/5.1).

A backup precedes every mutation. Restore validates the backup name
against path traversal, requires Rekordbox closed, and snapshots the
current database first so the restore is itself reversible.
"""

import errno
import fcntl
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime
from importlib import import_module
from pathlib import Path

_PREFIX = "rekordbox-db-"
_NAME = re.compile(r"^rekordbox-db-(\d{8}-\d{6})(?:-(\d+))?$")
_EXTRA_DIR = "extra"
_SYNCBOX_DIR = "syncbox"
_MANIFEST = "manifest.json"
_PENDING_EVENT_DELETE = ".pending-event-delete"
_RESTORE_JOURNAL = "restore-journal.json"
_TIER_LIMITS = (("hour", 48), ("day", 30), ("week", 12), ("month", 12))

log = logging.getLogger(__name__)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _sidecars(db_path: Path) -> tuple[Path, Path]:
    return (
        db_path.with_name(db_path.name + "-wal"),
        db_path.with_name(db_path.name + "-shm"),
    )


def _assert_mutation_ready(db_path: Path) -> None:
    # process_guard ships as its own safety module; resolving it at call time
    # keeps import order across safety modules flat and gives tests a seam
    # (sys.modules) to substitute the guard.
    import_module("syncbox.safety.process_guard").assert_mutation_ready(db_path)


def _extra_sources(db_path: Path, extra_files) -> list[tuple[Path, Path]]:
    """Validate extra Rekordbox files and map them below the backup root."""
    root = db_path.parent.resolve(strict=True)
    mapped = []
    for value in dict.fromkeys(Path(path) for path in extra_files):
        if value.is_symlink() or not value.is_file():
            raise FileNotFoundError(f"backup extra file is missing or unsafe: {value}")
        source = value.resolve(strict=True)
        try:
            relative = source.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"backup extra file must live below the Rekordbox database directory: {value}"
            ) from exc
        if source == db_path.resolve(strict=True) or source in {
            path.resolve(strict=True) for path in _sidecars(db_path) if path.is_file()
        }:
            continue
        mapped.append((source, relative))
    return mapped


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _snapshot_sqlite(source: Path, destination: Path) -> None:
    source_connection = sqlite3.connect(
        f"{source.resolve().as_uri()}?mode=ro", uri=True
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
        result = destination_connection.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise ValueError(f"Syncbox snapshot failed integrity_check: {result}")
    finally:
        destination_connection.close()
        source_connection.close()


def _write_manifest(staging: Path, *, reason: str) -> None:
    files = sorted(
        path for path in staging.rglob("*") if path.is_file() and path.name != _MANIFEST
    )
    payload = {
        "schema": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "reason": reason,
        "files": {
            str(path.relative_to(staging)): {
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in files
        },
    }
    (staging / _MANIFEST).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _validate_manifest(backup_dir: Path) -> dict:
    manifest_path = backup_dir / _MANIFEST
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError(f"backup manifest is missing or unsafe: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"backup manifest is invalid: {manifest_path}") from exc
    if payload.get("schema") != 1 or not isinstance(payload.get("files"), dict):
        raise ValueError(f"backup manifest is unsupported: {manifest_path}")
    # The manifest must describe the EXACT file set. A file present on disk
    # but absent from the manifest would otherwise ride along unverified —
    # restore scans directories, so an undeclared extra/master.db would
    # overwrite the live database after the verified restore.
    actual = {
        str(path.relative_to(backup_dir))
        for path in backup_dir.rglob("*")
        if path.is_file()
        and path != manifest_path
        and path != backup_dir / _PENDING_EVENT_DELETE
    }
    undeclared = sorted(actual - set(payload["files"]))
    if undeclared:
        raise ValueError(
            "backup contains files missing from its manifest: "
            + ", ".join(undeclared)
        )
    for relative, expected in payload["files"].items():
        raw_path = backup_dir / relative
        if raw_path.is_symlink():
            raise ValueError(f"backup manifest file is unsafe: {relative}")
        path = raw_path.resolve(strict=False)
        try:
            path.relative_to(backup_dir.resolve(strict=True))
        except ValueError as exc:
            raise ValueError(
                f"backup manifest path escapes its root: {relative}"
            ) from exc
        if not path.is_file():
            raise ValueError(f"backup manifest file is missing or unsafe: {relative}")
        if path.stat().st_size != expected.get("size") or _sha256(path) != expected.get(
            "sha256"
        ):
            raise ValueError(f"backup file failed verification: {relative}")
    return payload


def create_backup(
    db_path,
    backups_root,
    retention: int = 20,
    *,
    extra_files=(),
    app_db_path=None,
    reason: str = "rekordbox_mutation",
) -> Path:
    """Copy master.db, SQLite sidecars, and selected Rekordbox support files.

    Same-second collisions get a ``-<n>`` suffix starting at 2 (POC 09
    measured that this really happens). Keeps the ``retention`` most
    recent backups (0 = unlimited); the backup just created is never
    rotated away.
    """
    db_path = Path(db_path)
    backups_root = Path(backups_root)
    if not db_path.is_file():
        raise FileNotFoundError(f"database not found: {db_path}")
    extras = _extra_sources(db_path, extra_files)
    backups_root.mkdir(parents=True, exist_ok=True)

    # Copy into a dot-prefixed staging dir first, then rename into the final
    # timestamped name. A copy that dies half-way (disk full, interrupt, crash)
    # must never leave a truncated dir that looks like a valid backup: the
    # staging name never matches _NAME, so rotation and restore cannot see it.
    staging = Path(tempfile.mkdtemp(prefix=".incoming-", dir=backups_root))
    try:
        shutil.copy2(db_path, staging / db_path.name)
        for sidecar in _sidecars(db_path):
            if sidecar.is_file():
                shutil.copy2(sidecar, staging / sidecar.name)
        for source, relative in extras:
            destination = staging / _EXTRA_DIR / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        if app_db_path is not None:
            app_db_path = Path(app_db_path)
            if not app_db_path.is_file():
                raise FileNotFoundError(f"Syncbox database not found: {app_db_path}")
            _snapshot_sqlite(app_db_path, staging / _SYNCBOX_DIR / app_db_path.name)
        copied_pairs = [(db_path, staging / db_path.name)]
        copied_pairs.extend(
            (sidecar, staging / sidecar.name)
            for sidecar in _sidecars(db_path)
            if sidecar.is_file()
        )
        copied_pairs.extend(
            (source, staging / _EXTRA_DIR / relative) for source, relative in extras
        )
        for source, copied in copied_pairs:
            if _sha256(source) != _sha256(copied):
                raise ValueError(f"backup copy verification failed: {source}")
        _write_manifest(staging, reason=reason)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    stamp = _timestamp()
    dest = backups_root / f"{_PREFIX}{stamp}"
    suffix = 1
    while True:
        try:
            staging.rename(dest)
            break
        except OSError as exc:
            # Same-second collision: the final name already exists (EEXIST, or
            # ENOTEMPTY when renaming onto a non-empty dir on POSIX).
            if exc.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                shutil.rmtree(staging, ignore_errors=True)
                raise
            suffix += 1
            dest = backups_root / f"{_PREFIX}{stamp}-{suffix}"

    _rotate(backups_root, retention, just_created=dest)
    return dest


def _backup_dirs_oldest_first(backups_root: Path) -> list[Path]:
    # Sort on (timestamp, numeric collision suffix), not the raw name:
    # lexicographically "-10" would sort before "-2". Entries that do not
    # match the backup naming scheme are never rotation candidates.
    keyed = []
    for child in backups_root.iterdir():
        match = _NAME.match(child.name)
        if match and child.is_dir():
            keyed.append((match.group(1), int(match.group(2) or 1), child))
    keyed.sort(key=lambda item: item[:2])
    return [child for _, _, child in keyed]


def list_backups(backups_root) -> list[dict]:
    """Doctor inventory (SPEC-UNIFIED 5.10/F9): newest-first backup folders.

    Only folders matching the timestamped naming scheme count - the same
    filter rotation and restore use, so the doctor can never show a backup
    that restore would refuse.
    """
    root = Path(backups_root)
    if not root.is_dir():
        return []
    out = []
    for child in reversed(_backup_dirs_oldest_first(root)):
        try:
            manifest = json.loads((child / _MANIFEST).read_text(encoding="utf-8"))
            if manifest.get("schema") != 1:
                manifest = {}
        except OSError, json.JSONDecodeError:
            manifest = {}
        files = sorted(
            f
            for f in child.rglob("*")
            if f.is_file() and f.name != _PENDING_EVENT_DELETE
        )
        out.append(
            {
                "name": child.name,
                "files": [str(f.relative_to(child)) for f in files],
                "size_bytes": sum(f.stat().st_size for f in files),
                "reason": manifest.get("reason"),
                "verified": bool(manifest),
                "coherent": any(
                    str(relative).startswith(f"{_SYNCBOX_DIR}/")
                    for relative in manifest.get("files", {})
                ),
                "pinned": (child / _PENDING_EVENT_DELETE).is_file(),
            }
        )
    return out


def _bucket_key(path: Path, tier: str):
    match = _NAME.match(path.name)
    stamp = datetime.strptime(match.group(1), "%Y%m%d-%H%M%S")
    if tier == "hour":
        return stamp.strftime("%Y%m%d-%H")
    if tier == "day":
        return stamp.date().isoformat()
    if tier == "week":
        year, week, _ = stamp.isocalendar()
        return year, week
    return stamp.strftime("%Y-%m")


def _rotate(backups_root: Path, retention: int, just_created: Path) -> None:
    if retention <= 0:
        return
    candidates = _backup_dirs_oldest_first(backups_root)
    keep = set(candidates[-retention:])
    keep.add(just_created)
    newest_first = list(reversed(candidates))
    for tier, limit in _TIER_LIMITS:
        seen = set()
        for candidate in newest_first:
            key = _bucket_key(candidate, tier)
            if key in seen:
                continue
            seen.add(key)
            keep.add(candidate)
            if len(seen) >= limit:
                break
    for stale in candidates:
        if stale in keep:
            continue
        if (stale / _PENDING_EVENT_DELETE).is_file():
            continue
        shutil.rmtree(stale)


def pin_backup(backup_dir) -> Path:
    """Exclude an event-deletion recovery backup from retention rotation."""
    backup_dir = Path(backup_dir)
    if backup_dir.is_symlink() or not backup_dir.is_dir():
        raise FileNotFoundError(f"backup directory is missing or unsafe: {backup_dir}")
    marker = backup_dir / _PENDING_EVENT_DELETE
    if marker.is_symlink() or (marker.exists() and not marker.is_file()):
        raise ValueError(f"pending backup marker is unsafe: {marker}")
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(marker, flags, 0o600)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory_fd = os.open(backup_dir, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return marker


def unpin_backup(backup_dir) -> None:
    """Return a completed or rolled-back event backup to normal rotation."""
    backup_dir = Path(backup_dir)
    marker = backup_dir / _PENDING_EVENT_DELETE
    try:
        marker.unlink()
    except FileNotFoundError:
        return
    directory_fd = os.open(backup_dir, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _resolve_backup_dir(name, backups_root: Path) -> Path:
    """Validate ``name`` and return the backup directory it designates.

    Path traversal is the attack here: the name must be a plain directory
    name resolving to a direct child of the backups root, nothing else.
    """
    if (
        not isinstance(name, str)
        or not name
        or name in (".", "..")
        or "/" in name
        or chr(92) in name  # backslash: Windows separator, rejected everywhere
    ):
        raise ValueError(f"invalid backup name: {name!r}")
    root = backups_root.resolve(strict=True)
    target = (root / name).resolve()
    # Strictly a direct child of the backups root; also rejects symlinks
    # inside the root that point anywhere else.
    if target.parent != root or target.name != name:
        raise ValueError(f"backup name escapes the backups root: {name!r}")
    if not target.is_dir():
        raise FileNotFoundError(f"no such backup: {name!r}")
    return target


def _backed_extra_targets(
    backup_dir: Path, db_path: Path, *, app_db_path=None
) -> list[tuple[Path, Path]]:
    root = backup_dir / _EXTRA_DIR
    if not root.exists():
        return []
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"invalid extra backup directory: {root}")
    live_root = db_path.parent.resolve(strict=False)
    # Support files may never masquerade as the databases themselves: those
    # are restored through their own verified, staged paths only.
    forbidden = {db_path.resolve(strict=False)}
    forbidden.update(path.resolve(strict=False) for path in _sidecars(db_path))
    if app_db_path is not None:
        app_db_path = Path(app_db_path)
        forbidden.add(app_db_path.resolve(strict=False))
        forbidden.update(path.resolve(strict=False) for path in _sidecars(app_db_path))
    targets = []
    for source in sorted(root.rglob("*")):
        if source.is_symlink():
            raise ValueError(f"backup contains an unsafe symlink: {source}")
        if not source.is_file():
            continue
        relative = source.relative_to(root)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(
                f"backup extra path escapes the database directory: {relative}"
            )
        target = (live_root / relative).resolve(strict=False)
        try:
            target.relative_to(live_root)
        except ValueError as exc:
            raise ValueError(
                f"backup extra path escapes the database directory: {relative}"
            ) from exc
        if target in forbidden:
            raise ValueError(
                f"backup extra path targets a protected database file: {relative}"
            )
        targets.append((source, target))
    return targets


def restore_extra_files(
    backup_dir, db_path, *, required_files=(), app_db_path=None
) -> list[Path]:
    """Atomically restore support files, validating required paths first."""
    db_path = Path(db_path)
    targets = _backed_extra_targets(
        Path(backup_dir), db_path, app_db_path=app_db_path
    )
    available = {target.resolve(strict=False) for _, target in targets}
    required = {Path(path).resolve(strict=False) for path in required_files}
    missing = sorted(str(path) for path in required - available)
    if missing:
        raise FileNotFoundError(
            "backup is missing required support files: " + ", ".join(missing)
        )
    restored = []
    for source, target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".syncbox-restore-", dir=target.parent)
        os.close(fd)
        temp = Path(temp_name)
        try:
            shutil.copy2(source, temp)
            with temp.open("rb") as stream:
                os.fsync(stream.fileno())
            os.replace(temp, target)
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        restored.append(target)
    return restored


def _fullsync_file(path: Path) -> None:
    """Flush file bytes to durable storage. On macOS fsync alone only
    reaches the drive cache; F_FULLFSYNC asks for real persistence
    (Apple fsync(2))."""
    fd = os.open(path, os.O_RDONLY)
    try:
        if hasattr(fcntl, "F_FULLFSYNC"):
            try:
                fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
                return
            except OSError:
                pass
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _stage_copy(source: Path, target: Path) -> dict:
    """Copy ``source`` next to ``target`` and fsync it, ready for os.replace."""
    staged = target.with_name(target.name + ".restore-tmp")
    try:
        shutil.copy2(source, staged)
        _fullsync_file(staged)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return {"staged": str(staged), "target": str(target), "sha256": _sha256(staged)}


def _stage_restore(
    source: Path, db_path: Path, app_db_path
) -> tuple[list[dict], list[str]]:
    """Stage EVERY file of the restore set before anything is published.

    Returns (replacements, removals): each replacement is a fsynced staged
    sibling of its target plus the expected hash; removals are live sidecar
    files the restored databases must not be paired with. Nothing visible
    is modified here; a failure unstages everything.
    """
    replacements: list[dict] = []
    removals: list[str] = []
    try:
        backed_up_db = source / db_path.name
        replacements.append(_stage_copy(backed_up_db, db_path))
        for live_sidecar, backed_sidecar in zip(
            _sidecars(db_path), _sidecars(backed_up_db)
        ):
            if backed_sidecar.is_file():
                replacements.append(_stage_copy(backed_sidecar, live_sidecar))
            else:
                removals.append(str(live_sidecar))
        for extra_source, target in _backed_extra_targets(
            source, db_path, app_db_path=app_db_path
        ):
            target.parent.mkdir(parents=True, exist_ok=True)
            replacements.append(_stage_copy(extra_source, target))
        if app_db_path is not None:
            backed_up_app = source / _SYNCBOX_DIR / app_db_path.name
            staged = app_db_path.with_name(app_db_path.name + ".restore-tmp")
            staged.unlink(missing_ok=True)
            try:
                # A fresh SQLite snapshot of the backed-up app DB: compact,
                # integrity-checked, and independent of any wal the backup
                # may carry.
                _snapshot_sqlite(backed_up_app, staged)
                _fullsync_file(staged)
            except BaseException:
                staged.unlink(missing_ok=True)
                raise
            removals.extend(str(path) for path in _sidecars(app_db_path))
            replacements.append(
                {
                    "staged": str(staged),
                    "target": str(app_db_path),
                    "sha256": _sha256(staged),
                }
            )
    except BaseException:
        for entry in replacements:
            Path(entry["staged"]).unlink(missing_ok=True)
        raise
    return replacements, removals


def _publish_restore(replacements: list[dict], removals: list[str]) -> None:
    """Apply a journaled restore plan. Idempotent: crash recovery re-runs it,
    accepting targets that already carry the journaled bytes."""
    directories = set()
    for target in removals:
        target = Path(target)
        target.unlink(missing_ok=True)
        directories.add(target.parent)
    for entry in replacements:
        staged = Path(entry["staged"])
        target = Path(entry["target"])
        if staged.exists():
            os.replace(staged, target)
        elif not (target.is_file() and _sha256(target) == entry["sha256"]):
            raise ValueError(f"restore publication lost its staged file: {target}")
        directories.add(target.parent)
    for directory in directories:
        _fsync_dir(directory)


def _can_complete(replacements: list[dict]) -> bool:
    for entry in replacements:
        staged = Path(entry["staged"])
        if staged.is_file() and _sha256(staged) == entry["sha256"]:
            continue
        target = Path(entry["target"])
        if target.is_file() and _sha256(target) == entry["sha256"]:
            continue
        return False
    return True


def _write_restore_journal(journal_dir: Path, payload: dict) -> None:
    journal_dir.mkdir(parents=True, exist_ok=True)
    journal = journal_dir / _RESTORE_JOURNAL
    tmp = journal.with_name(journal.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _fullsync_file(tmp)
    os.replace(tmp, journal)
    _fsync_dir(journal_dir)


def _clear_restore_journal(journal_dir: Path) -> None:
    (Path(journal_dir) / _RESTORE_JOURNAL).unlink(missing_ok=True)
    _fsync_dir(Path(journal_dir))


def _execute_journaled_restore(
    source: Path, db_path: Path, app_db_path, journal_dir: Path, *, snapshot
) -> None:
    """Stage, journal, then publish one restore as a single recoverable unit.

    The journal is durable BEFORE the first live file is replaced, so a
    crash at any point leaves either a completable staged set (rolled
    forward on recovery) or a pre-restore snapshot to roll back to. A
    synchronous publication error rolls back to the snapshot immediately
    by restoring it through this same journaled path.
    """
    replacements, removals = _stage_restore(source, db_path, app_db_path)
    _write_restore_journal(
        Path(journal_dir),
        {
            "schema": 1,
            "created_at": datetime.now().astimezone().isoformat(),
            "source": str(source),
            "snapshot": str(snapshot) if snapshot is not None else None,
            "db_path": str(db_path),
            "app_db_path": str(app_db_path) if app_db_path is not None else None,
            "replacements": replacements,
            "removals": removals,
        },
    )
    try:
        _publish_restore(replacements, removals)
    except BaseException:
        for entry in replacements:
            Path(entry["staged"]).unlink(missing_ok=True)
        if snapshot is not None:
            _execute_journaled_restore(
                Path(snapshot), db_path, app_db_path, journal_dir, snapshot=None
            )
        raise
    _clear_restore_journal(journal_dir)


def recover_restore(journal_dir) -> str | None:
    """Resolve an interrupted restore recorded in ``journal_dir``.

    Runs at composition-root startup (before the app DB is opened) and
    before any new restore. Rolls the interrupted restore forward when the
    journaled staged/target set is intact, otherwise rolls the whole
    Rekordbox + Syncbox pair back to the pre-restore snapshot. Returns
    'completed', 'rolled_back', or None when there is nothing to recover.
    """
    journal_dir = Path(journal_dir)
    journal = journal_dir / _RESTORE_JOURNAL
    if not journal.is_file():
        return None
    payload = json.loads(journal.read_text(encoding="utf-8"))
    replacements = payload.get("replacements") or []
    removals = payload.get("removals") or []
    if _can_complete(replacements):
        _publish_restore(replacements, removals)
        _clear_restore_journal(journal_dir)
        log.warning("completed an interrupted backup restore at recovery")
        return "completed"
    snapshot = payload.get("snapshot")
    if snapshot and Path(snapshot).is_dir():
        for entry in replacements:
            Path(entry["staged"]).unlink(missing_ok=True)
        app_db_path = (
            Path(payload["app_db_path"]) if payload.get("app_db_path") else None
        )
        _execute_journaled_restore(
            Path(snapshot),
            Path(payload["db_path"]),
            app_db_path,
            journal_dir,
            snapshot=None,
        )
        log.warning("rolled back an interrupted backup restore at recovery")
        return "rolled_back"
    raise ValueError(
        "an interrupted restore can neither be completed nor rolled back; "
        f"keep {journal} and the backups directory for manual recovery"
    )


def restore_backup(
    name, backups_root, db_path, *, app_db_path=None, journal_dir=None
) -> Path | None:
    """Restore the named backup over the live database.

    Returns the path of the pre-restore snapshot taken from the current
    database, which makes the restore itself reversible (SPEC-01 1.3:
    a restore leaves two backups behind) — or None when no live database
    exists (the disaster case restore exists for: nothing to snapshot,
    Rekordbox-closed still enforced).

    The replacement itself is journaled: every component (master.db, its
    wal/shm, support extras, and the Syncbox DB) is staged and fsynced
    before the first live file changes, so the Rekordbox + Syncbox pair is
    recovered as one unit after a crash (see :func:`recover_restore`).
    """
    backups_root = Path(backups_root)
    db_path = Path(db_path)
    app_db_path = Path(app_db_path) if app_db_path is not None else None
    journal_dir = (
        Path(journal_dir)
        if journal_dir is not None
        else (app_db_path.parent if app_db_path is not None else backups_root)
    )
    # An earlier interrupted restore must be resolved before a new one may
    # touch the same files.
    recover_restore(journal_dir)

    source = _resolve_backup_dir(name, backups_root)
    if (source / _MANIFEST).exists():
        _validate_manifest(source)
    backed_up_db = source / db_path.name
    if not backed_up_db.is_file():
        raise FileNotFoundError(f"backup {name!r} does not contain {db_path.name}")
    backed_up_app = (
        source / _SYNCBOX_DIR / app_db_path.name if app_db_path is not None else None
    )
    if backed_up_app is not None and not backed_up_app.is_file():
        raise ValueError(
            f"backup {name!r} does not contain a coherent Syncbox database"
        )

    snapshot = None
    try:
        _assert_mutation_ready(db_path)
    except FileNotFoundError:
        # Live DB gone (deleted/lost): restoring is the whole point, and the
        # guard checks Rekordbox-running BEFORE existence, so RB is closed.
        # The snapshot-first rule is vacuous with nothing to snapshot.
        pass
    else:
        # retention=0 here: rotating during a restore could delete the very
        # backup being restored.
        current_extras = [
            target
            for _, target in _backed_extra_targets(
                source, db_path, app_db_path=app_db_path
            )
            if target.is_file() and not target.is_symlink()
        ]
        snapshot = create_backup(
            db_path,
            backups_root,
            retention=0,
            extra_files=current_extras,
            app_db_path=app_db_path,
            reason="pre_restore",
        )

    _execute_journaled_restore(
        source, db_path, app_db_path, journal_dir, snapshot=snapshot
    )
    return snapshot
