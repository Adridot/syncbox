"""Timestamped Rekordbox database backups, rotation, and safe restore
(SPEC-01 1.3, SPEC-UNIFIED 3.1/5.1).

A backup precedes every mutation. Restore validates the backup name
against path traversal, requires Rekordbox closed, and snapshots the
current database first so the restore is itself reversible.
"""

import errno
import os
import re
import shutil
import tempfile
from datetime import datetime
from importlib import import_module
from pathlib import Path

_PREFIX = "rekordbox-db-"
_NAME = re.compile(r"^rekordbox-db-(\d{8}-\d{6})(?:-(\d+))?$")


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


def create_backup(db_path, backups_root, retention: int = 15) -> Path:
    """Copy master.db (+ -wal/-shm when present) into a timestamped folder.

    Same-second collisions get a ``-<n>`` suffix starting at 2 (poc/09
    measured that this really happens). Keeps the ``retention`` most
    recent backups (0 = unlimited); the backup just created is never
    rotated away.
    """
    db_path = Path(db_path)
    backups_root = Path(backups_root)
    if not db_path.is_file():
        raise FileNotFoundError(f"database not found: {db_path}")
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
        files = sorted(f for f in child.iterdir() if f.is_file())
        out.append(
            {
                "name": child.name,
                "files": [f.name for f in files],
                "size_bytes": sum(f.stat().st_size for f in files),
            }
        )
    return out


def _rotate(backups_root: Path, retention: int, just_created: Path) -> None:
    if retention <= 0:  # 0 = unlimited
        return
    candidates = _backup_dirs_oldest_first(backups_root)
    excess = len(candidates) - retention
    for stale in candidates:
        if excess <= 0:
            return
        if stale == just_created:
            continue
        shutil.rmtree(stale)
        excess -= 1


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


def restore_backup(name, backups_root, db_path) -> Path | None:
    """Restore the named backup over the live database.

    Returns the path of the pre-restore snapshot taken from the current
    database, which makes the restore itself reversible (SPEC-01 1.3:
    a restore leaves two backups behind) — or None when no live database
    exists (the disaster case restore exists for: nothing to snapshot,
    Rekordbox-closed still enforced).
    """
    backups_root = Path(backups_root)
    db_path = Path(db_path)

    source = _resolve_backup_dir(name, backups_root)
    backed_up_db = source / db_path.name
    if not backed_up_db.is_file():
        raise FileNotFoundError(f"backup {name!r} does not contain {db_path.name}")

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
        snapshot = create_backup(db_path, backups_root, retention=0)

    # Ordering is load-bearing (a crash at any point must leave the live DB
    # either old or new, never torn, and never paired with a foreign wal):
    # 1. clear live wal/shm — their content is preserved in the snapshot; a
    #    stale live wal must never be replayed over the restored db file;
    # 2. copy the backup db next to the live one, then atomically replace
    #    (os.replace is atomic on APFS/NTFS) — no torn master.db, ever;
    # 3. bring over the backup's own sidecars.
    for sidecar in _sidecars(db_path):
        sidecar.unlink(missing_ok=True)
    tmp = db_path.with_name(db_path.name + ".restore-tmp")
    try:
        shutil.copy2(backed_up_db, tmp)
        os.replace(tmp, db_path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    for backed_sidecar in _sidecars(backed_up_db):
        if backed_sidecar.is_file():
            shutil.copy2(backed_sidecar, db_path.with_name(backed_sidecar.name))
    return snapshot
