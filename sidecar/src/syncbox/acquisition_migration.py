"""Previewed migration of legacy job-owned acquisition files."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from syncbox import acquisition, event_delete
from syncbox.platform_os import delete_file
from syncbox.rb import open_readonly
from syncbox.rb_write import migrate_content_path, open_rekordbox
from syncbox.safety.mutate import StaleSnapshotError, fingerprint, mutate
from syncbox.safety.paths import (
    SYNC_DIR_NAME,
    paths_equal,
    resolve_stored_path,
    stored_form,
)

PLAN_VERSION = 2
ACTIVE_JOB_STATUSES = {"queued", "running"}


def _serial_fingerprint(db_path) -> list[list[str]]:
    return [list(part) for part in fingerprint(db_path)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _state(path: Path) -> dict:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"path": str(path), "exists": False}
    if path.is_symlink() or not path.is_file():
        return {"path": str(path), "exists": True, "kind": "unsafe"}
    return {
        "path": str(path),
        "exists": True,
        "kind": "file",
        "size": str(info.st_size),
        "mtime_ns": str(info.st_mtime_ns),
        "sha256": _sha256(path),
    }


def _matches_state(expected: dict) -> bool:
    return _state(Path(expected["path"])) == expected


def _directory_state(path: Path) -> dict:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"path": str(path), "exists": False}
    if path.is_symlink() or not path.is_dir():
        return {"path": str(path), "exists": True, "kind": "unsafe"}
    return {
        "path": str(path),
        "exists": True,
        "kind": "directory",
        "device": str(info.st_dev),
        "inode": str(info.st_ino),
        "mtime_ns": str(info.st_mtime_ns),
    }


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
    except ValueError:
        return False
    return True


def _destination(
    source: Path, destination_dir: Path, content_id, active_paths, storage_root
):
    source_digest = _sha256(source)
    for suffix in range(1, 10_001):
        candidate = (
            destination_dir / source.name
            if suffix == 1
            else destination_dir / f"{source.stem} - {suffix}{source.suffix}"
        )
        state = _state(candidate)
        if not state["exists"]:
            return candidate, False, state
        if (
            state.get("kind") == "file"
            and state.get("sha256") == source_digest
            and not event_delete._referenced_by_other_content(
                candidate, str(content_id or ""), active_paths, storage_root
            )
        ):
            return candidate, True, state
    raise ValueError(f"could not allocate a destination for {source.name!r}")


def _owner(conn, job, storage_root):
    if job["scope"] == "event":
        row = conn.execute(
            "SELECT t.id, t.content_id, t.staging_file_path, e.id AS event_id, "
            "e.slug, e.staging_dir "
            "FROM event_tracks t JOIN events e ON e.id = t.event_id "
            "WHERE t.id = ?",
            (job["event_track_id"] or job["ref"],),
        ).fetchone()
        if row is None:
            return None
        staging = row["staging_dir"] or str(
            Path(storage_root) / SYNC_DIR_NAME / "events" / row["slug"]
        )
        return {
            "destination_dir": Path(staging) / "audio",
            "content_id": row["content_id"],
            "track_id": row["id"],
            "staging_file_path": row["staging_file_path"],
            "event_id": row["event_id"],
            "staging_dir": staging,
            "slug": row["slug"],
        }
    if job["scope"] == "library":
        row = conn.execute(
            "SELECT id, content_id, staging_file_path FROM library_tracks WHERE id = ?",
            (job["library_track_id"] or job["ref"],),
        ).fetchone()
        if row is None:
            return None
        return {
            "destination_dir": Path(storage_root) / "rekordbox" / "Collection",
            "content_id": row["content_id"],
            "track_id": row["id"],
            "staging_file_path": row["staging_file_path"],
        }
    return {
        "destination_dir": Path(storage_root) / "rekordbox" / "Collection",
        "content_id": job["ref"],
        "track_id": None,
    }


def _safe_owner_destination(job, owner, storage_root) -> Path | None:
    try:
        if job["scope"] == "event":
            destination = acquisition.event_audio_destination(
                storage_root, owner["staging_dir"], event_slug=owner["slug"]
            )
        else:
            destination = acquisition.collection_destination(storage_root)
    except ValueError:
        return None
    if destination != Path(owner["destination_dir"]).resolve(strict=False):
        return None
    return destination


def _ignored(job, path: Path, reason: str) -> dict:
    return {
        "job_id": job["id"] if job is not None else None,
        "title": job["title"] if job is not None else path.name,
        "artist": job["artist"] if job is not None else None,
        "source_path": str(path),
        "reason": reason,
    }


def _cleanup_directory(
    job,
    path: Path,
    state: dict,
    destination: Path,
    digest: str,
    owner,
    source_state: dict | None = None,
) -> dict:
    entry = {
        "job_id": job["id"],
        "scope": job["scope"],
        "title": job["title"],
        "artist": job["artist"],
        "directory_path": str(path),
        "directory_state": state,
        "destination_path": str(destination),
        "destination_sha256": digest,
        "content_id": str(owner["content_id"]) if owner["content_id"] else None,
    }
    if source_state is not None:
        entry["source_state"] = source_state
    return entry


def _owner_references_destination(
    ro, job, owner, destination: Path, storage_root
) -> bool:
    if job["scope"] in ("event", "library"):
        staging = owner.get("staging_file_path")
        if not staging or not paths_equal(staging, destination, storage_root):
            return False
    content_id = owner["content_id"]
    if not content_id:
        return True
    content = ro.execute(
        "SELECT FolderPath, rb_local_deleted FROM djmdContent WHERE ID = ?",
        (str(content_id),),
    ).fetchone()
    return bool(
        content is not None
        and not int(content[1] or 0)
        and paths_equal(
            resolve_stored_path(content[0], storage_root), destination, storage_root
        )
    )


def build_plan(conn, storage_root, db_path) -> dict:
    # Refuses symlinked ancestors: with acquisition -> /victim, every job
    # source below it would really live outside managed storage and the
    # cleanup pass would delete external files.
    legacy_root = acquisition.acquisition_root(storage_root)
    before = _serial_fingerprint(db_path)
    ro = open_readonly(db_path)
    try:
        active_paths = list(
            ro.execute(
                "SELECT ID, FolderPath FROM djmdContent "
                "WHERE rb_local_deleted = 0 AND FolderPath IS NOT NULL ORDER BY ID"
            )
        )
        jobs = conn.execute("SELECT * FROM acquisition_jobs ORDER BY id").fetchall()
        items = []
        cleanup_directories = []
        ignored = []
        known_job_directories = set()
        for job in jobs:
            job_root = legacy_root / f"job-{job['id']}"
            known_job_directories.add(job_root)
            directory_state = _directory_state(job_root)
            if directory_state.get("kind") == "unsafe":
                ignored.append(_ignored(job, job_root, "unsafe_directory"))
                continue
            if job["status"] in ACTIVE_JOB_STATUSES:
                if directory_state["exists"]:
                    ignored.append(_ignored(job, job_root, "active_job"))
                continue
            raw_source = job["legacy_output_path"] or job["output_path"]
            if not raw_source:
                if directory_state["exists"]:
                    ignored.append(_ignored(job, job_root, "missing_destination"))
                continue
            raw_source_path = Path(raw_source)
            source = raw_source_path.resolve(strict=False)
            if job["legacy_output_path"] is None and not _inside(source, legacy_root):
                if not directory_state["exists"]:
                    continue
                owner = _owner(conn, job, storage_root)
                owner_destination = (
                    _safe_owner_destination(job, owner, storage_root)
                    if owner is not None
                    else None
                )
                destination_state = _state(source)
                if owner is None:
                    ignored.append(_ignored(job, job_root, "missing_owner"))
                elif (
                    raw_source_path.is_symlink()
                    or owner_destination is None
                    or source.parent != owner_destination
                ):
                    ignored.append(_ignored(job, job_root, "unsafe_destination"))
                elif destination_state.get("kind") != "file":
                    ignored.append(_ignored(job, job_root, "missing_destination"))
                elif not _owner_references_destination(
                    ro, job, owner, source, storage_root
                ):
                    ignored.append(_ignored(job, job_root, "unverified_destination"))
                else:
                    cleanup_directories.append(
                        _cleanup_directory(
                            job,
                            job_root,
                            directory_state,
                            source,
                            destination_state["sha256"],
                            owner,
                        )
                    )
                continue
            if raw_source_path.is_symlink() or not _inside(source, job_root):
                ignored.append(
                    {
                        "job_id": job["id"],
                        "title": job["title"],
                        "artist": job["artist"],
                        "source_path": str(raw_source_path),
                        "reason": "unsafe_source",
                    }
                )
                continue
            source_state = _state(source)
            owner = _owner(conn, job, storage_root)
            if source_state.get("kind") != "file" or owner is None:
                reason = (
                    "missing_source"
                    if not source_state["exists"]
                    else "unsafe_source"
                    if source_state.get("kind") != "file"
                    else "missing_owner"
                )
                ignored.append(
                    {
                        "job_id": job["id"],
                        "title": job["title"],
                        "artist": job["artist"],
                        "source_path": str(source),
                        "reason": reason,
                    }
                )
                continue

            owner_destination = _safe_owner_destination(job, owner, storage_root)
            if owner_destination is None:
                ignored.append(
                    {
                        "job_id": job["id"],
                        "title": job["title"],
                        "artist": job["artist"],
                        "source_path": str(source),
                        "reason": "unsafe_destination",
                    }
                )
                continue

            content_id = owner["content_id"]
            if job["legacy_output_path"]:
                raw_destination = Path(job["output_path"])
                destination = raw_destination.resolve(strict=False)
                destination_reused = True
                destination_state = _state(destination)
                if (
                    raw_destination.is_symlink()
                    or destination.parent != owner_destination
                    or destination_state.get("kind") != "file"
                    or destination_state.get("sha256") != source_state["sha256"]
                ):
                    ignored.append(
                        {
                            "job_id": job["id"],
                            "title": job["title"],
                            "artist": job["artist"],
                            "source_path": str(source),
                            "reason": "missing_destination",
                        }
                    )
                    continue
            else:
                try:
                    destination, destination_reused, destination_state = _destination(
                        source,
                        owner_destination,
                        content_id,
                        active_paths,
                        storage_root,
                    )
                except ValueError:
                    ignored.append(
                        {
                            "job_id": job["id"],
                            "title": job["title"],
                            "artist": job["artist"],
                            "source_path": str(source),
                            "reason": "destination_collision",
                        }
                    )
                    continue

            update_rekordbox = False
            anlz_paths = []
            if content_id:
                content = ro.execute(
                    "SELECT FolderPath, AnalysisDataPath, rb_local_deleted "
                    "FROM djmdContent WHERE ID = ?",
                    (str(content_id),),
                ).fetchone()
                if content is None or int(content[2] or 0):
                    ignored.append(
                        {
                            "job_id": job["id"],
                            "title": job["title"],
                            "artist": job["artist"],
                            "source_path": str(source),
                            "reason": "missing_rekordbox_content",
                        }
                    )
                    continue
                current = resolve_stored_path(content[0], storage_root)
                if paths_equal(current, source, storage_root):
                    update_rekordbox = True
                    try:
                        anlz_paths = [
                            str(path)
                            for path in event_delete._anlz_paths(
                                Path(db_path), content[1]
                            )
                        ]
                    except ValueError:
                        ignored.append(
                            {
                                "job_id": job["id"],
                                "title": job["title"],
                                "artist": job["artist"],
                                "source_path": str(source),
                                "reason": "unsafe_analysis",
                            }
                        )
                        continue
                elif not paths_equal(current, destination, storage_root):
                    ignored.append(
                        {
                            "job_id": job["id"],
                            "title": job["title"],
                            "artist": job["artist"],
                            "source_path": str(source),
                            "reason": "rekordbox_path_changed",
                        }
                    )
                    continue

            items.append(
                {
                    "job_id": job["id"],
                    "scope": job["scope"],
                    "ref": job["ref"],
                    "title": job["title"],
                    "artist": job["artist"],
                    "source_path": str(source),
                    "source_state": source_state,
                    "destination_path": str(destination),
                    "destination_state": destination_state,
                    "destination_reused": destination_reused,
                    "content_id": str(content_id) if content_id else None,
                    "update_rekordbox": update_rekordbox,
                    "anlz_paths": anlz_paths,
                    "event_id": owner.get("event_id"),
                    "staging_dir": owner.get("staging_dir"),
                }
            )
            cleanup_directories.append(
                _cleanup_directory(
                    job,
                    job_root,
                    directory_state,
                    destination,
                    source_state["sha256"],
                    owner,
                    source_state,
                )
            )
    finally:
        ro.close()
    after = _serial_fingerprint(db_path)
    if before != after:
        raise StaleSnapshotError(
            "master.db changed while the storage migration was planned"
        )

    if legacy_root.is_dir():
        for path in legacy_root.glob("job-*"):
            if path not in known_job_directories:
                ignored.append(
                    _ignored(
                        None,
                        path,
                        (
                            "unsafe_directory"
                            if path.is_symlink()
                            else "unowned_directory"
                        ),
                    )
                )
    return {
        "dry_run": True,
        "plan_version": PLAN_VERSION,
        "fingerprint": before,
        "items": items,
        "cleanup_directories": cleanup_directories,
        "ignored": ignored,
    }


def _copy_item(item: dict) -> bool:
    source = Path(item["source_path"])
    destination = Path(item["destination_path"])
    if not _matches_state(item["source_state"]):
        raise StaleSnapshotError(f"migration source changed: {source}")
    if item["destination_reused"]:
        if _sha256(destination) != item["source_state"]["sha256"]:
            raise StaleSnapshotError(f"migration destination changed: {destination}")
        return False
    if destination.exists():
        raise StaleSnapshotError(f"migration destination now exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=".syncbox-migrate-", dir=destination.parent
    )
    os.close(descriptor)
    temp = Path(temp_name)
    try:
        shutil.copy2(source, temp)
        if _sha256(temp) != item["source_state"]["sha256"]:
            raise ValueError(f"migration copy verification failed: {source}")
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)
    return True


def _assert_cleanup_safe(conn, cleanup: dict, storage_root, db_path) -> bool:
    """Revalidate the complete job directory and its published owner."""
    raw_directory = Path(cleanup["directory_path"])
    try:
        expected_directory = acquisition.validated_job_workspace(
            storage_root, cleanup["job_id"]
        )
    except ValueError as exc:
        raise StaleSnapshotError(str(exc)) from exc
    if (
        raw_directory != expected_directory
        or raw_directory.is_symlink()
        or raw_directory.resolve(strict=False) != expected_directory
    ):
        raise StaleSnapshotError(
            f"migration directory escaped its workspace: {raw_directory}"
        )
    current_directory_state = _directory_state(raw_directory)
    if current_directory_state["exists"] and (
        current_directory_state != cleanup["directory_state"]
    ):
        raise StaleSnapshotError(f"migration directory changed: {raw_directory}")
    if (
        current_directory_state["exists"]
        and cleanup.get("source_state")
        and not _matches_state(cleanup["source_state"])
    ):
        raise StaleSnapshotError(
            f"migration source changed: {cleanup['source_state']['path']}"
        )
    raw_destination = Path(cleanup["destination_path"])
    if (
        raw_destination.is_symlink()
        or not raw_destination.is_file()
        or _sha256(raw_destination) != cleanup["destination_sha256"]
    ):
        raise StaleSnapshotError(
            f"migration destination changed: {raw_destination}"
        )
    job = conn.execute(
        "SELECT * FROM acquisition_jobs WHERE id = ?", (cleanup["job_id"],)
    ).fetchone()
    if job is None:
        raise StaleSnapshotError(
            f"migration job {cleanup['job_id']} no longer exists"
        )
    if job["status"] in ACTIVE_JOB_STATUSES:
        raise StaleSnapshotError(
            f"migration job {cleanup['job_id']} became active; keeping its directory"
        )
    if not job["output_path"] or not paths_equal(
        job["output_path"], raw_destination, storage_root
    ):
        raise StaleSnapshotError(
            f"migration destination for job {cleanup['job_id']} changed"
        )
    owner = _owner(conn, job, storage_root)
    if owner is None:
        raise StaleSnapshotError(
            f"migration owner for job {cleanup['job_id']} no longer exists"
        )
    owner_destination = _safe_owner_destination(job, owner, storage_root)
    if (
        owner_destination is None
        or raw_destination.resolve(strict=False).parent != owner_destination
    ):
        raise StaleSnapshotError(
            f"migration destination no longer belongs to its owner: {raw_destination}"
        )
    if job["scope"] in ("event", "library") and (
        not owner.get("staging_file_path")
        or not paths_equal(
            owner["staging_file_path"], raw_destination, storage_root
        )
    ):
        raise StaleSnapshotError(
            f"migration owner for job {cleanup['job_id']} no longer references "
            "the published destination"
        )
    if cleanup["content_id"]:
        ro = open_readonly(db_path)
        try:
            content = ro.execute(
                "SELECT FolderPath, rb_local_deleted FROM djmdContent WHERE ID = ?",
                (str(cleanup["content_id"]),),
            ).fetchone()
        finally:
            ro.close()
        if content is None or int(content[1] or 0):
            raise StaleSnapshotError(
                f"Rekordbox content {cleanup['content_id']} disappeared; "
                "keeping the migration directory"
            )
        current = resolve_stored_path(content[0], storage_root)
        if not paths_equal(current, raw_destination, storage_root):
            raise StaleSnapshotError(
                f"Rekordbox path for {cleanup['content_id']} does not reference "
                "the migrated destination; keeping the migration directory"
            )
    return current_directory_state["exists"]


def _resume_state(conn, item: dict) -> str | None:
    row = conn.execute(
        "SELECT output_path, legacy_output_path FROM acquisition_jobs WHERE id = ?",
        (item["job_id"],),
    ).fetchone()
    if row is None:
        return None
    destination = Path(item["destination_path"])
    if (
        row["output_path"] == item["destination_path"]
        and destination.is_file()
        and not destination.is_symlink()
        and _sha256(destination) == item["source_state"]["sha256"]
    ):
        if row["legacy_output_path"] == item["source_path"]:
            return "cleanup_pending"
        if row["legacy_output_path"] is None:
            return "complete"
    return None


def execute(
    conn,
    db_path,
    backups_root,
    cache,
    storage_root,
    plan,
    *,
    app_db_path=None,
    retention: int = 20,
    consent_to_permanent_delete: bool = False,
) -> dict:
    if not isinstance(plan, dict) or plan.get("plan_version") != PLAN_VERSION:
        raise ValueError("a valid storage migration preview is required")
    resume = [_resume_state(conn, item) for item in plan["items"]]
    migrated_files = sum(
        state not in ("cleanup_pending", "complete") for state in resume
    )
    if not all(state in ("cleanup_pending", "complete") for state in resume):
        fresh = build_plan(conn, storage_root, db_path)
        if fresh != plan:
            raise StaleSnapshotError("storage migration preview is stale")

        created = []
        try:
            for item in plan["items"]:
                if _copy_item(item):
                    created.append(
                        (
                            Path(item["destination_path"]),
                            item["source_state"]["sha256"],
                        )
                    )
            backup_files = [
                Path(path) for item in plan["items"] for path in item["anlz_paths"]
            ]
            with mutate(
                db_path,
                backups_root,
                retention=retention,
                expected_fingerprint=tuple(tuple(part) for part in plan["fingerprint"]),
                open_db=open_rekordbox,
                invalidate_cache=cache.invalidate,
                backup_files=backup_files,
                app_db_path=app_db_path,
                backup_reason="acquisition_storage_migration",
            ) as db:
                for item in plan["items"]:
                    if item["update_rekordbox"]:
                        migrate_content_path(
                            db,
                            item["content_id"],
                            stored_form(item["destination_path"], storage_root),
                            update_anlz=bool(item["anlz_paths"]),
                            anlz_paths=item["anlz_paths"],
                        )
        except BaseException:
            # Rollback removes ONLY the exact bytes this run created: a
            # destination that changed since the copy is somebody's file now.
            for path, digest in created:
                try:
                    if (
                        not path.is_symlink()
                        and path.is_file()
                        and _sha256(path) == digest
                    ):
                        path.unlink()
                except OSError:
                    pass
            raise

        conn.execute("BEGIN")
        try:
            for item in plan["items"]:
                conn.execute(
                    "UPDATE acquisition_jobs SET legacy_output_path = ?, output_path = ?, "
                    "stored_path = CASE WHEN stored_path = ? THEN ? ELSE stored_path END, "
                    "updated_at = datetime('now') WHERE id = ?",
                    (
                        item["source_path"],
                        item["destination_path"],
                        item["source_path"],
                        item["destination_path"],
                        item["job_id"],
                    ),
                )
                if item["scope"] in ("event", "library"):
                    table = {"event": "event_tracks", "library": "library_tracks"}[
                        item["scope"]
                    ]
                    conn.execute(
                        f"UPDATE {table} SET staging_file_path = ?, "
                        "updated_at = datetime('now') WHERE id = ?",
                        (item["destination_path"], item["ref"]),
                    )
                if item["event_id"] and item["staging_dir"]:
                    conn.execute(
                        "UPDATE events SET staging_dir = ? WHERE id = ?",
                        (item["staging_dir"], item["event_id"]),
                    )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

    removed_sources = []
    cleaned_directories = []
    for cleanup in plan["cleanup_directories"]:
        source_state = cleanup.get("source_state")
        source_existed = bool(
            source_state and Path(source_state["path"]).exists()
        )
        directory = Path(cleanup["directory_path"])
        if _assert_cleanup_safe(conn, cleanup, storage_root, db_path):
            delete_file(
                directory,
                consent_to_permanent_delete=consent_to_permanent_delete,
            )
            if directory.exists():
                raise OSError(f"migration directory was not removed: {directory}")
        conn.execute(
            "UPDATE acquisition_jobs SET legacy_output_path = NULL, "
            "updated_at = datetime('now') WHERE id = ?",
            (cleanup["job_id"],),
        )
        cleaned_directories.append(str(directory))
        if source_existed:
            removed_sources.append(source_state["path"])
    return {
        **plan,
        "dry_run": False,
        "migrated": migrated_files,
        "migrated_files": migrated_files,
        "cleaned_directories": len(cleaned_directories),
        "cleaned_directory_paths": cleaned_directories,
        "removed_sources": removed_sources,
    }
