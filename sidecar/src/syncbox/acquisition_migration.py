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
            "SELECT t.id, t.content_id, e.id AS event_id, e.slug, e.staging_dir "
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
            "event_id": row["event_id"],
            "staging_dir": staging,
            "slug": row["slug"],
        }
    if job["scope"] == "library":
        row = conn.execute(
            "SELECT id, content_id FROM library_tracks WHERE id = ?",
            (job["library_track_id"] or job["ref"],),
        ).fetchone()
        if row is None:
            return None
        return {
            "destination_dir": Path(storage_root) / "rekordbox" / "Collection",
            "content_id": row["content_id"],
            "track_id": row["id"],
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
        jobs = conn.execute(
            "SELECT * FROM acquisition_jobs "
            "WHERE output_path IS NOT NULL OR legacy_output_path IS NOT NULL ORDER BY id"
        ).fetchall()
        items = []
        ignored = []
        planned_sources = set()
        for job in jobs:
            raw_source = job["legacy_output_path"] or job["output_path"]
            raw_source_path = Path(raw_source)
            source = raw_source_path.resolve(strict=False)
            job_root = legacy_root / f"job-{job['id']}"
            if job["legacy_output_path"] is None and not _inside(source, legacy_root):
                # Owner-published output (event/audio or Collection): not a
                # legacy candidate — silently out of scope, never a warning.
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
            planned_sources.add(source)
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
    finally:
        ro.close()
    after = _serial_fingerprint(db_path)
    if before != after:
        raise StaleSnapshotError(
            "master.db changed while the storage migration was planned"
        )

    if legacy_root.is_dir():
        for path in legacy_root.glob("job-*/*"):
            if path.is_file() and path.resolve(strict=False) not in planned_sources:
                ignored.append(
                    {
                        "job_id": None,
                        "title": path.name,
                        "artist": None,
                        "source_path": str(path),
                        "reason": "orphan_file",
                    }
                )
    return {
        "dry_run": True,
        "plan_version": 1,
        "fingerprint": before,
        "items": items,
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


def _assert_cleanup_safe(conn, item: dict, storage_root, db_path) -> None:
    """Revalidate EVERYTHING this item relies on immediately before deleting
    its legacy source — a resumed plan (e.g. after a permanent-delete 428)
    may be arbitrarily old, so nothing validated at planning time is
    trusted here. Any mismatch keeps the source and surfaces a conflict.
    """
    legacy_root = acquisition.acquisition_root(storage_root)
    raw_source = Path(item["source_path"])
    source = raw_source.resolve(strict=False)
    if raw_source.is_symlink() or not _inside(source, legacy_root / f"job-{item['job_id']}"):
        raise StaleSnapshotError(f"migration source escaped its workspace: {source}")
    if not _matches_state(item["source_state"]):
        raise StaleSnapshotError(f"migration source changed: {source}")
    raw_destination = Path(item["destination_path"])
    if (
        raw_destination.is_symlink()
        or not raw_destination.is_file()
        or _sha256(raw_destination) != item["source_state"]["sha256"]
    ):
        raise StaleSnapshotError(
            f"migration destination changed: {raw_destination}"
        )
    job = conn.execute(
        "SELECT * FROM acquisition_jobs WHERE id = ?", (item["job_id"],)
    ).fetchone()
    if job is None:
        raise StaleSnapshotError(f"migration job {item['job_id']} no longer exists")
    owner = _owner(conn, job, storage_root)
    if owner is None:
        raise StaleSnapshotError(
            f"migration owner for job {item['job_id']} no longer exists"
        )
    owner_destination = _safe_owner_destination(job, owner, storage_root)
    if (
        owner_destination is None
        or raw_destination.resolve(strict=False).parent != owner_destination
    ):
        raise StaleSnapshotError(
            f"migration destination no longer belongs to its owner: {raw_destination}"
        )
    if item["content_id"]:
        ro = open_readonly(db_path)
        try:
            content = ro.execute(
                "SELECT FolderPath, rb_local_deleted FROM djmdContent WHERE ID = ?",
                (str(item["content_id"]),),
            ).fetchone()
        finally:
            ro.close()
        if content is None or int(content[1] or 0):
            raise StaleSnapshotError(
                f"Rekordbox content {item['content_id']} disappeared; "
                "keeping the migration source"
            )
        current = resolve_stored_path(content[0], storage_root)
        if not paths_equal(current, raw_destination, storage_root):
            raise StaleSnapshotError(
                f"Rekordbox path for {item['content_id']} does not reference "
                "the migrated destination; keeping the migration source"
            )


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
    if not isinstance(plan, dict) or plan.get("plan_version") != 1:
        raise ValueError("a valid storage migration preview is required")
    resume = [_resume_state(conn, item) for item in plan["items"]]
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

    removed = []
    for item in plan["items"]:
        state = _resume_state(conn, item)
        if state == "complete":
            continue
        source = Path(item["source_path"])
        if source.exists():
            _assert_cleanup_safe(conn, item, storage_root, db_path)
            delete_file(source, consent_to_permanent_delete=consent_to_permanent_delete)
            removed.append(str(source))
        conn.execute(
            "UPDATE acquisition_jobs SET legacy_output_path = NULL, "
            "updated_at = datetime('now') WHERE id = ?",
            (item["job_id"],),
        )
        job_dir = source.parent
        try:
            job_dir.rmdir()
        except OSError:
            pass
    return {
        **plan,
        "dry_run": False,
        "migrated": len(plan["items"]),
        "removed_sources": removed,
    }
