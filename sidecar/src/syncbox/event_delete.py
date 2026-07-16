"""Exact event-deletion planning and retained-track migration for macOS v1."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path

from pyrekordbox.anlz import get_anlz_paths

from syncbox.platform_os import delete_file
from syncbox.rb import open_readonly
from syncbox.rb_write import (
    migrate_content_path,
    open_rekordbox,
    soft_delete_content,
    soft_delete_mytag,
    soft_delete_playlist,
    untag_content,
)
from syncbox.safety.backup import pin_backup, restore_extra_files, unpin_backup
from syncbox.safety.mutate import StaleSnapshotError, fingerprint, mutate
from syncbox.safety.paths import (
    canonical_key,
    classify_ownership,
    paths_equal,
    resolve_stored_path,
    stored_form,
)
from syncbox.safety.process_guard import assert_mutation_ready

DELETE_PLAN_VERSION = 1
SITUATION_CATEGORY = "Situation"
EVENT_FOLDER_NAME = "Event Imports"
XML_NAME = "masterPlaylists6.xml"


class EventMigrationError(ValueError):
    """A retained track could not be secured, so deletion was aborted."""


class EventCleanupError(ValueError):
    """The Rekordbox commit succeeded but app-managed cleanup is incomplete."""


_TAG_SQL = """
SELECT t.ID FROM djmdMyTag t JOIN djmdMyTag c ON c.ID = t.ParentID
WHERE t.Name = :tag AND c.Name = :category AND c.ParentID = 'root'
  AND t.rb_local_deleted = 0
"""
_TAGGED_SQL = """
SELECT c.ID, c.Title, a.Name, c.FolderPath, c.AnalysisDataPath
FROM djmdSongMyTag l
JOIN djmdContent c ON c.ID = l.ContentID
LEFT JOIN djmdArtist a ON a.ID = c.ArtistID
WHERE l.MyTagID = :tag_id AND l.rb_local_deleted = 0 AND c.rb_local_deleted = 0
ORDER BY c.ID
"""
_OTHER_TAGS_SQL = """
SELECT t.ID, t.Name FROM djmdSongMyTag l
JOIN djmdMyTag t ON t.ID = l.MyTagID
WHERE l.ContentID = :content_id AND l.MyTagID != :tag_id
  AND l.rb_local_deleted = 0 AND t.rb_local_deleted = 0
ORDER BY t.Name, t.ID
"""
_PLAYLISTS_SQL = """
SELECT p.ID, p.Name FROM djmdPlaylist p
JOIN djmdPlaylist f ON f.ID = p.ParentID
WHERE p.Name IN (:name, :legacy) AND p.Attribute = 4
  AND p.rb_local_deleted = 0 AND f.Name = :folder
  AND f.Attribute = 1 AND f.ParentID = 'root' AND f.rb_local_deleted = 0
ORDER BY p.ID
"""
_ACTIVE_PATHS_SQL = """
SELECT ID, FolderPath FROM djmdContent
WHERE rb_local_deleted = 0 AND FolderPath IS NOT NULL
ORDER BY ID
"""

_FILE_STATE_KEYS = ("path", "exists", "kind", "size", "mtime_ns", "sha256")


def _serial_fingerprint(db_path) -> list[list[str]]:
    return [list(part) for part in fingerprint(db_path)]


def _sha256(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def _file_state(path, *, with_hash: bool = False) -> dict:
    path = Path(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"path": str(path), "exists": False}
    if stat.S_ISLNK(info.st_mode):
        kind = "symlink"
    elif stat.S_ISREG(info.st_mode):
        kind = "file"
    else:
        kind = "other"
    state = {
        "path": str(path),
        "exists": True,
        "kind": kind,
        "size": str(info.st_size),
        "mtime_ns": str(info.st_mtime_ns),
    }
    if with_hash and kind == "file":
        state["sha256"] = _sha256(path)
    return state


def _expected_file_state(state: dict) -> dict:
    return {key: state[key] for key in _FILE_STATE_KEYS if key in state}


def _assert_state(expected: dict, *, with_hash: bool = False) -> None:
    path = expected.get("path")
    current = (
        _file_state(path, with_hash=with_hash or "sha256" in expected)
        if path is not None
        else {"path": None, "exists": False}
    )
    expected_file = _expected_file_state(expected)
    comparable = {key: current.get(key) for key in expected_file}
    if comparable != expected_file:
        raise StaleSnapshotError(
            f"file state changed after the event deletion preview: {path}"
        )


def _staging_files(staging_dir, cap: int = 10_000) -> list[Path]:
    root = Path(staging_dir)
    if root.is_symlink():
        raise EventMigrationError(f"event staging directory is a symbolic link: {root}")
    if not root.is_dir():
        return []
    files = []
    for count, path in enumerate(root.rglob("*"), start=1):
        if count > cap:
            raise EventMigrationError(
                f"event staging contains more than {cap} entries; deletion was not planned"
            )
        if path.is_symlink():
            raise EventMigrationError(
                f"event staging contains a symbolic link that will not be deleted: {path}"
            )
        if path.is_file():
            files.append(path)
    return sorted(files)


def _inside_staging(path: Path | None, staging: Path | None) -> bool:
    if path is None or staging is None:
        return False
    path = path.resolve(strict=False)
    staging = staging.resolve(strict=False)
    try:
        path.relative_to(staging)
    except ValueError:
        return False
    return path != staging


def _anlz_paths(db_path: Path, analysis_data_path) -> list[Path]:
    if not analysis_data_path:
        return []
    relative = str(analysis_data_path).replace("\\", "/").strip("/")
    parts = [part for part in relative.split("/") if part]
    if not parts or any(part in (".", "..") for part in parts):
        raise EventMigrationError(
            f"invalid AnalysisDataPath for retained track: {analysis_data_path!r}"
        )
    share = (db_path.parent / "share").resolve(strict=False)
    dat = share.joinpath(*parts).resolve(strict=False)
    try:
        dat.relative_to(share)
    except ValueError as exc:
        raise EventMigrationError(
            f"AnalysisDataPath escapes the Rekordbox share directory: {analysis_data_path!r}"
        ) from exc
    directory = dat.parent
    if not directory.exists():
        return []
    if directory.is_symlink() or not directory.is_dir():
        raise EventMigrationError(f"ANLZ directory is unsafe: {directory}")
    paths = []
    for candidate in get_anlz_paths(directory).values():
        if candidate is None:
            continue
        candidate = Path(candidate)
        state = _file_state(candidate)
        if state.get("kind") != "file":
            raise EventMigrationError(f"ANLZ path is not a regular file: {candidate}")
        resolved = candidate.resolve(strict=True)
        if resolved.parent != directory.resolve(strict=True):
            raise EventMigrationError(
                f"ANLZ path escapes its analysis directory: {candidate}"
            )
        paths.append(resolved)
    return paths


def _referenced_by_other_content(
    candidate: Path, content_id: str, active_paths, storage_root
) -> bool:
    return any(
        str(other_id) != content_id
        and folder_path
        and paths_equal(folder_path, candidate, storage_root)
        for other_id, folder_path in active_paths
    )


def _migration_destination(
    source: Path,
    content_id: str,
    collection: Path,
    active_paths,
    storage_root,
    reserved=(),
) -> tuple[Path, bool, list[dict], dict]:
    source_state = _file_state(source)
    source_digest = None
    inspected = []
    for suffix in range(1, 10_001):
        candidate = (
            collection / source.name
            if suffix == 1
            else collection / f"{source.stem} - {suffix}{source.suffix}"
        )
        state = _file_state(candidate)
        if canonical_key(candidate, storage_root) in reserved:
            inspected.append({**state, "reserved": True})
            continue
        if not state["exists"]:
            inspected.append(state)
            return candidate, False, inspected, source_state
        if state.get("kind") == "file" and source_state.get("kind") == "file":
            if state["size"] == source_state["size"]:
                if source_digest is None:
                    source_digest = _sha256(source)
                    source_state["sha256"] = source_digest
                state["sha256"] = _sha256(candidate)
                if state[
                    "sha256"
                ] == source_digest and not _referenced_by_other_content(
                    candidate, content_id, active_paths, storage_root
                ):
                    inspected.append(state)
                    return candidate, True, inspected, source_state
        inspected.append(state)
    raise EventMigrationError(
        f"could not allocate a collision-free Collection filename for {source.name!r}"
    )


def build_plan(query, event, storage_root, db_path, db_fingerprint) -> dict:
    """Build the deterministic payload that the confirmation must echo."""
    db_path = Path(db_path)
    root = Path(storage_root).expanduser().resolve(strict=False)
    staging = None
    if event.get("staging_dir"):
        raw_staging = Path(event["staging_dir"]).expanduser()
        if raw_staging.is_symlink():
            raise EventMigrationError(
                f"event staging directory is a symbolic link: {raw_staging}"
            )
        staging = raw_staging.resolve(strict=False)
        expected_parent = (root / "_syncbox" / "events").resolve(strict=False)
        try:
            staging.relative_to(expected_parent)
        except ValueError as exc:
            raise EventMigrationError(
                f"event staging directory escapes app-managed storage: {staging}"
            ) from exc
        if staging == expected_parent:
            raise EventMigrationError(
                "event staging directory cannot be the events root"
            )
    collection_raw = root / "rekordbox" / "Collection"
    collection = collection_raw.resolve(strict=False)
    if collection != collection_raw:
        raise EventMigrationError(
            f"Rekordbox Collection must not use a symbolic-link path: {collection_raw}"
        )
    tag_rows = query(
        _TAG_SQL, {"tag": event["default_tag"], "category": SITUATION_CATEGORY}
    )
    tag_id = str(tag_rows[0][0]) if tag_rows else None
    active_paths = query(_ACTIVE_PATHS_SQL, {}) if tag_id is not None else []
    tracks = []
    source_states = []
    destination_states = []
    active_mytags = []
    anlz_states = []
    reserved_destinations = set()
    if tag_id is not None:
        for content_id, title, artist, folder_path, analysis_path in query(
            _TAGGED_SQL, {"tag_id": tag_id}
        ):
            content_id = str(content_id)
            other_tags = query(
                _OTHER_TAGS_SQL, {"content_id": content_id, "tag_id": tag_id}
            )
            retaining_ids = [str(row[0]) for row in other_tags]
            retaining_names = [row[1] for row in other_tags]
            source = (
                resolve_stored_path(folder_path, storage_root) if folder_path else None
            )
            ownership = (
                classify_ownership(folder_path, storage_root)
                if folder_path
                else "external"
            )
            in_event_staging = _inside_staging(source, staging)
            if ownership == "permanent_library":
                action = "already_permanent"
            elif in_event_staging and retaining_ids:
                action = "migrate_to_collection"
            elif in_event_staging:
                action = "delete_with_event"
            else:
                action = "keep_in_place"

            destination = None
            destination_reused = False
            source_state = (
                _file_state(source)
                if source is not None
                else {"path": None, "exists": False}
            )
            affected_anlz = []
            if action == "migrate_to_collection":
                destination, destination_reused, inspected, source_state = (
                    _migration_destination(
                        source,
                        content_id,
                        collection,
                        active_paths,
                        storage_root,
                        reserved_destinations,
                    )
                )
                reserved_destinations.add(canonical_key(destination, storage_root))
                if source_state.get("kind") == "file" and "sha256" not in source_state:
                    source_state["sha256"] = _sha256(source)
                destination_states.extend(inspected)
                affected_anlz = _anlz_paths(db_path, analysis_path)
                anlz_states.extend(
                    {
                        "content_id": content_id,
                        **_file_state(path, with_hash=True),
                    }
                    for path in affected_anlz
                )
            source_states.append({"content_id": content_id, **source_state})
            active_mytags.append(
                {
                    "content_id": content_id,
                    "tag_ids": retaining_ids,
                    "tag_names": retaining_names,
                }
            )
            tracks.append(
                {
                    "content_id": content_id,
                    "title": title,
                    "artist": artist,
                    "source_path": str(source) if source is not None else None,
                    "ownership": ownership,
                    "retaining_mytags": retaining_names,
                    "action": action,
                    "destination_path": str(destination) if destination else None,
                    "destination_reused": destination_reused,
                    "anlz_update_required": bool(affected_anlz),
                }
            )

    playlists = [
        {"playlist_id": str(playlist_id), "name": name}
        for playlist_id, name in query(
            _PLAYLISTS_SQL,
            {
                "name": event["name"],
                "legacy": f"{event['name']} - Smart",
                "folder": EVENT_FOLDER_NAME,
            },
        )
    ]
    staging_files = _staging_files(staging) if staging is not None else []
    cleanup_states = [_file_state(path, with_hash=True) for path in staging_files]
    xml_path = db_path.with_name(XML_NAME)
    needs_rekordbox_mutation = tag_id is not None or bool(playlists)
    xml_artifacts = (
        [str(xml_path)] if needs_rekordbox_mutation and xml_path.is_file() else []
    )
    support_states = (
        [{"role": "playlist_xml", **_file_state(xml_path, with_hash=True)}]
        if needs_rekordbox_mutation and xml_path.is_file()
        else []
    )
    support_states.extend({"role": "anlz", **state} for state in anlz_states)
    return {
        "dry_run": True,
        "plan_version": DELETE_PLAN_VERSION,
        "event_id": int(event["id"]),
        "event_name": event["name"],
        "fingerprint": db_fingerprint,
        "tag_id": tag_id,
        "event_mytag": (
            {"tag_id": tag_id, "name": event["default_tag"]} if tag_id else None
        ),
        "tracks": tracks,
        "playlists": playlists,
        "xml_artifacts": xml_artifacts,
        "staging_artifacts": [str(path) for path in staging_files],
        "expected_file_deletions": [str(path) for path in staging_files],
        "validation": {
            "db_fingerprint": db_fingerprint,
            "sources": source_states,
            "destinations": destination_states,
            "active_mytags": active_mytags,
            "support_files": support_states,
            "cleanup_files": cleanup_states,
        },
    }


def read_plan(db_path, event, storage_root) -> dict:
    before = _serial_fingerprint(db_path)
    ro = open_readonly(db_path)
    try:

        def query(sql, params):
            return ro.execute(sql, params).fetchall()

        plan = build_plan(query, event, storage_root, db_path, before)
    finally:
        ro.close()
    after = _serial_fingerprint(db_path)
    if before != after:
        raise StaleSnapshotError(
            "master.db changed while the event deletion preview was being built; "
            "run the preview again"
        )
    return plan


def _fingerprint_tuple(value) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list):
        raise ValueError("event deletion plan carries no valid database fingerprint")
    return tuple(tuple(str(leaf) for leaf in part) for part in value)


def _state_by_content(plan, key: str) -> dict[str, dict]:
    return {
        str(state["content_id"]): state for state in plan["validation"].get(key, [])
    }


def _rename_exclusive(source: Path, destination: Path) -> None:
    """Atomically publish a same-directory temp file without replacement."""
    renamex = getattr(ctypes.CDLL(None, use_errno=True), "renamex_np", None)
    if renamex is not None:
        renamex.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex.restype = ctypes.c_int
        if renamex(os.fsencode(source), os.fsencode(destination), 0x00000004) == 0:
            return
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise FileExistsError(error, os.strerror(error), destination)
        if error not in (errno.ENOTSUP, errno.EINVAL, errno.ENOSYS):
            raise OSError(error, os.strerror(error), destination)
    linked = False
    try:
        os.link(source, destination, follow_symlinks=False)
        linked = True
    except FileExistsError:
        raise
    except OSError as exc:
        raise EventMigrationError(
            "the destination volume cannot atomically publish a file without "
            f"overwriting an existing path: {destination}"
        ) from exc
    try:
        source.unlink()
    except BaseException as error:
        if linked:
            try:
                destination.unlink()
                _fsync_directory(destination.parent)
            except BaseException as cleanup_error:
                raise EventMigrationError(
                    "hard-link publication failed and its destination could not "
                    f"be removed safely: {cleanup_error}"
                ) from error
        raise


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _copy_migration(
    track: dict, expected_source: dict, *, resume_existing: bool = False
) -> tuple[Path, bool, str]:
    source = Path(track["source_path"])
    destination = Path(track["destination_path"])
    _assert_state(expected_source)
    if expected_source.get("kind") != "file":
        raise EventMigrationError(
            f"retained track source is missing or not a regular file: {source}"
        )
    source_digest = _sha256(source)
    if resume_existing:
        destination_state = _file_state(destination, with_hash=True)
        if destination_state["exists"] and (
            destination_state.get("kind") != "file"
            or destination_state.get("sha256") != source_digest
        ):
            raise EventMigrationError(
                f"stored migration destination differs from its source: {destination}"
            )
        if destination_state["exists"]:
            return destination, False, source_digest
    if track.get("destination_reused"):
        destination_state = _file_state(destination, with_hash=True)
        if (
            destination_state.get("kind") != "file"
            or destination_state.get("sha256") != source_digest
        ):
            raise StaleSnapshotError(
                f"reused migration destination changed after preview: {destination}"
            )
        return destination, False, source_digest

    if destination.parent.resolve(strict=False) != destination.parent:
        raise EventMigrationError(
            f"migration destination parent changed to a symbolic-link path: {destination.parent}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".syncbox-migrate-", dir=destination.parent)
    temp = Path(temp_name)
    copied_digest = hashlib.sha256()
    published = False
    try:
        with source.open("rb") as input_stream, os.fdopen(fd, "wb") as output_stream:
            for block in iter(lambda: input_stream.read(1024 * 1024), b""):
                output_stream.write(block)
                copied_digest.update(block)
            os.fchmod(output_stream.fileno(), stat.S_IMODE(source.stat().st_mode))
            output_stream.flush()
            os.fsync(output_stream.fileno())
        if temp.stat().st_size != source.stat().st_size:
            raise EventMigrationError(
                f"migration copy size verification failed: {source}"
            )
        if copied_digest.hexdigest() != source_digest or _sha256(temp) != source_digest:
            raise EventMigrationError(
                f"migration copy checksum verification failed: {source}"
            )
        _assert_state(expected_source)
        _rename_exclusive(temp, destination)
        published = True
        _fsync_directory(destination.parent)
        if _sha256(destination) != source_digest:
            raise EventMigrationError(
                f"published migration checksum verification failed: {destination}"
            )
        return destination, True, source_digest
    except BaseException as error:
        temp.unlink(missing_ok=True)
        if published:
            try:
                _remove_published([(destination, source_digest)])
            except BaseException as cleanup_error:
                raise EventMigrationError(
                    "migration publication failed and its destination could not "
                    f"be removed safely: {cleanup_error}"
                ) from error
        raise


def _remove_published(paths: list[tuple[Path, str]]) -> None:
    for path, expected_digest in reversed(paths):
        state = _file_state(path, with_hash=True)
        if not state["exists"]:
            continue
        if state.get("kind") != "file" or state.get("sha256") != expected_digest:
            raise EventMigrationError(
                f"published migration destination changed and was not removed: {path}"
            )
        path.unlink()
        _fsync_directory(path.parent)


def _verify_precommit_files(plan: dict) -> list[Path]:
    sources = _state_by_content(plan, "sources")
    backup_files = []
    for state in plan["validation"].get("sources", []):
        _assert_state(state, with_hash="sha256" in state)
    for state in plan["validation"].get("cleanup_files", []):
        _assert_state(state, with_hash=True)
    for track in plan["tracks"]:
        if track["action"] != "migrate_to_collection":
            continue
        expected = sources[track["content_id"]]
        _assert_state(expected)
        source = Path(track["source_path"])
        destination = Path(track["destination_path"])
        if not destination.is_file() or _sha256(source) != _sha256(destination):
            raise EventMigrationError(
                f"migration destination no longer matches its source: {destination}"
            )
    for state in plan["validation"].get("support_files", []):
        _assert_state(state, with_hash=True)
        if state.get("exists"):
            backup_files.append(Path(state["path"]))
    return backup_files


def _verify_migration_destinations(plan: dict) -> None:
    sources = _state_by_content(plan, "sources")
    for track in plan["tracks"]:
        if track["action"] != "migrate_to_collection":
            continue
        source = sources[track["content_id"]]
        digest = source.get("sha256")
        destination = Path(track["destination_path"])
        state = _file_state(destination, with_hash=True)
        if not digest or state.get("kind") != "file" or state.get("sha256") != digest:
            raise EventCleanupError(
                "retained-track destination is missing or changed; staging was "
                f"kept for recovery: {destination}"
            )


def _verify_live_plan(db, plan: dict, storage_root) -> None:
    from sqlalchemy import text

    tag_id = plan["tag_id"]
    expected_tags = _state_by_content(plan, "active_mytags")
    for track in plan["tracks"]:
        row = db.session.execute(
            text("SELECT FolderPath, rb_local_deleted FROM djmdContent WHERE ID = :id"),
            {"id": track["content_id"]},
        ).one_or_none()
        if row is None or int(row[1] or 0):
            raise StaleSnapshotError(
                f"content {track['content_id']} changed after the event deletion preview"
            )
        if track["source_path"] and not paths_equal(
            row[0], track["source_path"], storage_root
        ):
            raise StaleSnapshotError(
                f"content path changed after preview: {track['content_id']}"
            )
        link = db.session.execute(
            text(
                "SELECT rb_local_deleted FROM djmdSongMyTag "
                "WHERE ContentID = :content_id AND MyTagID = :tag_id"
            ),
            {"content_id": track["content_id"], "tag_id": tag_id},
        ).one_or_none()
        if link is None or int(link[0] or 0):
            raise StaleSnapshotError(
                f"event MyTag link changed after preview: {track['content_id']}"
            )
        rows = db.session.execute(
            text(
                "SELECT l.MyTagID FROM djmdSongMyTag l "
                "JOIN djmdMyTag t ON t.ID = l.MyTagID "
                "WHERE l.ContentID = :content_id AND l.MyTagID != :tag_id "
                "AND l.rb_local_deleted = 0 AND t.rb_local_deleted = 0 "
                "ORDER BY l.MyTagID"
            ),
            {"content_id": track["content_id"], "tag_id": tag_id},
        ).all()
        current = sorted(str(row[0]) for row in rows)
        if current != sorted(expected_tags[track["content_id"]]["tag_ids"]):
            raise StaleSnapshotError(
                f"active MyTags changed after preview: {track['content_id']}"
            )


def _execute_rekordbox_plan(db, plan: dict, storage_root) -> None:
    _verify_live_plan(db, plan, storage_root)
    tag_id = plan["tag_id"]
    anlz_paths = {}
    for state in plan["validation"].get("support_files", []):
        if state.get("role") == "anlz":
            anlz_paths.setdefault(str(state["content_id"]), []).append(state["path"])
    if tag_id is not None:
        for track in plan["tracks"]:
            if track["action"] == "migrate_to_collection":
                migrate_content_path(
                    db,
                    track["content_id"],
                    stored_form(track["destination_path"], storage_root),
                    update_anlz=track["anlz_update_required"],
                    anlz_paths=anlz_paths.get(track["content_id"], ()),
                )
            untag_content(db, track["content_id"], tag_id)
            if track["action"] == "delete_with_event":
                soft_delete_content(db, track["content_id"])
        soft_delete_mytag(db, tag_id)
    for playlist in plan["playlists"]:
        soft_delete_playlist(db, playlist["playlist_id"])


def _db_plan_committed(db_path, plan: dict, storage_root) -> bool:
    ro = open_readonly(db_path)
    try:
        tag_id = plan["tag_id"]
        if tag_id is not None:
            row = ro.execute(
                "SELECT rb_local_deleted FROM djmdMyTag WHERE ID = ?", (tag_id,)
            ).fetchone()
            if row is not None and not int(row[0] or 0):
                return False
        for playlist in plan["playlists"]:
            row = ro.execute(
                "SELECT rb_local_deleted FROM djmdPlaylist WHERE ID = ?",
                (playlist["playlist_id"],),
            ).fetchone()
            if row is not None and not int(row[0] or 0):
                return False
        for track in plan["tracks"]:
            row = ro.execute(
                "SELECT FolderPath, rb_local_deleted FROM djmdContent WHERE ID = ?",
                (track["content_id"],),
            ).fetchone()
            if row is None:
                return False
            if track["action"] == "delete_with_event":
                if not int(row[1] or 0):
                    return False
            else:
                if int(row[1] or 0):
                    return False
                expected_path = (
                    track["destination_path"]
                    if track["action"] == "migrate_to_collection"
                    else track["source_path"]
                )
                if expected_path and not paths_equal(
                    row[0], expected_path, storage_root
                ):
                    return False
        return True
    finally:
        ro.close()


def _atomic_restore(source: Path, destination: Path) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=".syncbox-restore-", dir=destination.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        shutil.copy2(source, temp)
        with temp.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temp, destination)
        _fsync_directory(destination.parent)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def _restore_plan_support(plan: dict, db_path: Path, backup_path) -> None:
    states = [
        state
        for state in plan["validation"].get("support_files", [])
        if state.get("exists")
    ]
    if not states:
        return
    if not backup_path:
        raise EventMigrationError(
            "event deletion support files need restoration but no backup is recorded"
        )
    required = [Path(state["path"]) for state in states]
    restore_extra_files(
        backup_path,
        db_path,
        required_files=required,
    )
    for state in states:
        _assert_state(state, with_hash=True)


def _restore_playlist_xml(plan: dict, db_path: Path, backup_path) -> None:
    state = next(
        (
            item
            for item in plan["validation"].get("support_files", [])
            if item.get("role") == "playlist_xml"
        ),
        None,
    )
    if state is None:
        return
    current = _file_state(state["path"], with_hash=True)
    expected = _expected_file_state(state)
    if {key: current.get(key) for key in expected} == expected:
        return
    if not backup_path:
        raise EventCleanupError(
            "playlist XML needs restoration but no backup is recorded"
        )
    try:
        relative = (
            Path(state["path"])
            .resolve(strict=False)
            .relative_to(db_path.parent.resolve(strict=False))
        )
    except ValueError as exc:
        raise EventCleanupError(
            "playlist XML path escapes the database directory"
        ) from exc
    source = Path(backup_path) / "extra" / relative
    if source.is_symlink() or not source.is_file():
        raise EventCleanupError(f"playlist XML backup is missing: {source}")
    _atomic_restore(source, Path(state["path"]))


def _cleanup_planned_files(event, plan: dict, *, consent: bool) -> list[str]:
    staging = (
        Path(event["staging_dir"]).resolve(strict=False)
        if event.get("staging_dir")
        else None
    )
    cleanup_states = {
        state["path"]: state for state in plan["validation"].get("cleanup_files", [])
    }
    ready = []
    for value in plan["expected_file_deletions"]:
        path = Path(value)
        if staging is None or not _inside_staging(path, staging):
            raise EventCleanupError(
                f"planned cleanup path escapes event staging: {path}"
            )
        expected = cleanup_states.get(str(path))
        if expected is None:
            raise EventCleanupError(f"planned cleanup has no file state: {path}")
        current = _file_state(path, with_hash=True)
        if not current["exists"]:
            continue
        expected_state = _expected_file_state(expected)
        if {key: current.get(key) for key in expected_state} != expected_state:
            raise EventCleanupError(
                f"planned cleanup file changed and was kept for recovery: {path}"
            )
        ready.append(path)
    removed = []
    for path in ready:
        delete_file(path, consent_to_permanent_delete=consent)
        removed.append(str(path))
    if staging is not None and staging.is_dir():
        for folder in sorted(
            (path for path in staging.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            try:
                folder.rmdir()
            except OSError:
                pass
        try:
            staging.rmdir()
        except OSError:
            remaining = [str(path) for path in _staging_files(staging)]
            raise EventCleanupError(
                "event deletion committed, but staging cleanup is incomplete: "
                + ", ".join(remaining or [str(staging)])
            )
    return removed


def _plan_requires_rekordbox_guard(plan: dict) -> bool:
    return bool(
        plan.get("tag_id")
        or plan.get("playlists")
        or plan.get("validation", {}).get("support_files")
        or any(
            track.get("action") == "migrate_to_collection"
            for track in plan.get("tracks", [])
        )
    )


def _assert_guarded_cleanup(db_path: Path, plan: dict) -> None:
    if _plan_requires_rekordbox_guard(plan):
        assert_mutation_ready(db_path)


def _support_files_match(plan: dict) -> bool:
    for state in plan["validation"].get("support_files", []):
        current = _file_state(state["path"], with_hash=True)
        expected = _expected_file_state(state)
        if {key: current.get(key) for key in expected} != expected:
            return False
    return True


def _verify_resume_files(plan: dict) -> None:
    for state in plan["validation"].get("sources", []):
        _assert_state(state, with_hash="sha256" in state)
    for state in plan["validation"].get("cleanup_files", []):
        _assert_state(state, with_hash=True)


def _recover_precommit(event: dict, plan: dict, db_path: Path) -> None:
    """Validate an interrupted plan without deleting ambiguous files."""
    _assert_guarded_cleanup(db_path, plan)
    phase = event.get("delete_phase")
    if phase == "mutating":
        _restore_plan_support(plan, db_path, event.get("delete_backup"))
    elif not _support_files_match(plan):
        raise EventMigrationError(
            "interrupted event deletion has ambiguous support-file changes; "
            "the event and every audio file were kept"
        )
    sources = _state_by_content(plan, "sources")
    for track in plan["tracks"]:
        if track["action"] != "migrate_to_collection":
            continue
        digest = sources[track["content_id"]].get("sha256")
        if not digest:
            raise EventMigrationError(
                f"stored migration plan has no source digest: {track['content_id']}"
            )
        destination = Path(track["destination_path"])
        destination_state = _file_state(destination, with_hash=True)
        if destination_state["exists"] and (
            destination_state.get("kind") != "file"
            or destination_state.get("sha256") != digest
        ):
            raise EventMigrationError(
                "interrupted migration destination is ambiguous and was kept: "
                f"{destination}"
            )


def _assert_event_tag_exclusive(conn, event: dict) -> None:
    other = conn.execute(
        "SELECT id, name FROM events WHERE default_tag = ? AND id != ? LIMIT 1",
        (event["default_tag"], event["id"]),
    ).fetchone()
    if other is not None:
        raise EventMigrationError(
            f"event MyTag {event['default_tag']!r} is shared with another Syncbox "
            "event; deletion was refused"
        )


def _release_backup(backup_path) -> None:
    if not backup_path:
        return
    try:
        unpin_backup(backup_path)
    except OSError:
        # A stale pin only retains an extra backup. It must not turn a durable
        # event deletion or rollback into an apparent data failure.
        pass


def _clear_delete_state(conn, event_id: int) -> None:
    conn.execute(
        "UPDATE events SET delete_plan = NULL, delete_backup = NULL, "
        "delete_committed = 0, delete_phase = NULL WHERE id = ?",
        (event_id,),
    )


def delete_event(
    conn,
    db_path,
    backups_root,
    cache,
    storage_root,
    event,
    *,
    dry_run: bool = True,
    plan=None,
    consent_to_permanent_delete: bool = False,
    retention: int = 20,
    app_db_path=None,
) -> dict:
    """Preview or execute one exact, recoverable event deletion plan."""
    event = _get_event(conn, event["id"])
    if event is None:
        raise KeyError("event no longer exists")
    db_path = Path(db_path)
    backups_root = Path(backups_root)

    if dry_run:
        stored = json.loads(event["delete_plan"]) if event.get("delete_plan") else None
        if stored:
            return stored
        _assert_event_tag_exclusive(conn, event)
        preview = read_plan(db_path, event, storage_root)
        preview["unresolved"] = _active_acquisition_issues(conn, event["id"])
        return preview

    if not isinstance(plan, dict):
        raise ValueError("event deletion execution requires the exact preview plan")
    if plan.get("plan_version") != DELETE_PLAN_VERSION:
        raise ValueError("unsupported event deletion plan version")
    if int(plan.get("event_id", -1)) != int(event["id"]):
        raise ValueError("event deletion plan targets a different event")
    if plan.get("unresolved"):
        raise ValueError("event deletion has unresolved cases")

    stored = json.loads(event["delete_plan"]) if event.get("delete_plan") else None
    if stored is not None and stored != plan:
        raise StaleSnapshotError(
            "another event deletion plan is already in progress; reopen the preview"
        )
    committed = bool(event.get("delete_committed"))
    resuming = False
    if stored is not None and not committed:
        committed = _db_plan_committed(db_path, stored, storage_root)
        if committed:
            try:
                conn.execute(
                    "UPDATE events SET delete_committed = 1, "
                    "delete_phase = 'committed' WHERE id = ?",
                    (event["id"],),
                )
            except BaseException as error:
                raise EventCleanupError(
                    "Rekordbox deletion committed, but Syncbox could not record "
                    "the cleanup state; retry with the same preview"
                ) from error
        else:
            _assert_event_tag_exclusive(conn, event)
            if fingerprint(db_path) != _fingerprint_tuple(plan["fingerprint"]):
                raise StaleSnapshotError(
                    "master.db changed after the interrupted event deletion; "
                    "sources and destinations were kept"
                )
            _verify_resume_files(plan)
            _recover_precommit(event, stored, db_path)
            resuming = True
    if committed:
        if not _db_plan_committed(db_path, plan, storage_root):
            raise EventCleanupError(
                "stored event deletion state does not match Rekordbox; cleanup was not run"
            )
        _assert_guarded_cleanup(db_path, plan)
        _verify_migration_destinations(plan)
        _restore_playlist_xml(plan, db_path, event.get("delete_backup"))
        removed = _cleanup_planned_files(
            event, plan, consent=consent_to_permanent_delete
        )
        conn.execute("DELETE FROM events WHERE id = ?", (event["id"],))
        _release_backup(event.get("delete_backup"))
        return {
            **plan,
            "dry_run": False,
            "deleted_event": True,
            "removed_files": removed,
            "cleanup_only": True,
        }

    if not resuming:
        _assert_event_tag_exclusive(conn, event)
        fresh = read_plan(db_path, event, storage_root)
        fresh["unresolved"] = _active_acquisition_issues(conn, event["id"])
        if fresh != plan:
            _clear_delete_state(conn, event["id"])
            raise StaleSnapshotError(
                "the event deletion preview is stale; reopen it before deleting"
            )
        conn.execute(
            "UPDATE events SET delete_plan = ?, delete_backup = NULL, "
            "delete_committed = 0, delete_phase = 'planned' WHERE id = ?",
            (json.dumps(plan, sort_keys=True, separators=(",", ":")), event["id"]),
        )

    sources = _state_by_content(plan, "sources")
    created_destinations = []
    backup_paths = []
    previous_backup = (
        Path(event["delete_backup"]) if event.get("delete_backup") else None
    )
    mutation_attempted = False
    try:
        for track in plan["tracks"]:
            if track["action"] != "migrate_to_collection":
                continue
            try:
                destination, created, digest = _copy_migration(
                    track,
                    sources[track["content_id"]],
                    resume_existing=resuming,
                )
            except BaseException as exc:
                raise EventMigrationError(
                    f"retained content {track['content_id']} migration failed: {exc}"
                ) from exc
            if created:
                created_destinations.append((destination, digest))
        conn.execute(
            "UPDATE events SET delete_phase = 'destinations_ready' WHERE id = ?",
            (event["id"],),
        )
        backup_files = _verify_precommit_files(plan)
        needs_mutation = plan["tag_id"] is not None or bool(plan["playlists"])
        if needs_mutation:

            def remember_backup(path):
                pin_backup(path)
                backup_paths.append(Path(path))
                conn.execute(
                    "UPDATE events SET delete_backup = ?, "
                    "delete_phase = 'backup_ready' WHERE id = ?",
                    (str(path), event["id"]),
                )
                if previous_backup is not None and previous_backup != Path(path):
                    unpin_backup(previous_backup)

            mutation_attempted = True
            with mutate(
                db_path,
                backups_root,
                retention=retention,
                expected_fingerprint=_fingerprint_tuple(plan["fingerprint"]),
                open_db=open_rekordbox,
                backup_files=backup_files,
                backup_observer=remember_backup,
                app_db_path=app_db_path,
                backup_reason="event_delete",
            ) as db:
                conn.execute(
                    "UPDATE events SET delete_phase = 'mutating' WHERE id = ?",
                    (event["id"],),
                )
                _execute_rekordbox_plan(db, plan, storage_root)
    except BaseException as error:
        if mutation_attempted:
            try:
                commit_detected = _db_plan_committed(db_path, plan, storage_root)
            except BaseException as detection_error:
                raise EventCleanupError(
                    "event deletion outcome is uncertain; sources and migration "
                    "destinations were kept for an exact retry"
                ) from detection_error
            if commit_detected:
                cache.invalidate()
                try:
                    conn.execute(
                        "UPDATE events SET delete_committed = 1, "
                        "delete_phase = 'committed' WHERE id = ?",
                        (event["id"],),
                    )
                except BaseException:
                    pass
                raise EventCleanupError(
                    "Rekordbox deletion committed after an interrupted mutation; "
                    "retry with the same preview to finish cleanup"
                ) from error
        restore_error = None
        if backup_paths:
            try:
                _assert_guarded_cleanup(db_path, plan)
                _restore_plan_support(plan, db_path, backup_paths[-1])
            except BaseException as exc:
                restore_error = exc
        removal_error = None
        if restore_error is None:
            try:
                _remove_published(created_destinations)
            except BaseException as exc:
                removal_error = exc
        else:
            removal_error = EventMigrationError(
                "migration destinations were kept until support files can be restored"
            )
        if restore_error is not None or removal_error is not None:
            raise EventMigrationError(
                "event deletion failed and precommit recovery is incomplete: "
                f"restore={restore_error!s}; cleanup={removal_error!s}"
            ) from error
        _clear_delete_state(conn, event["id"])
        for backup_path in dict.fromkeys(
            [*backup_paths, *([previous_backup] if previous_backup else [])]
        ):
            _release_backup(backup_path)
        raise

    try:
        conn.execute(
            "UPDATE events SET delete_committed = 1, delete_phase = 'committed' "
            "WHERE id = ?",
            (event["id"],),
        )
    except BaseException as error:
        cache.invalidate()
        raise EventCleanupError(
            "Rekordbox deletion committed, but Syncbox could not record the "
            "cleanup state; retry with the same preview"
        ) from error

    cache.invalidate()
    event = _get_event(conn, event["id"])
    backup_path = event.get("delete_backup") if event else None
    _assert_guarded_cleanup(db_path, plan)
    _verify_migration_destinations(plan)
    _restore_playlist_xml(plan, db_path, backup_path)
    removed = _cleanup_planned_files(event, plan, consent=consent_to_permanent_delete)
    conn.execute("DELETE FROM events WHERE id = ?", (event["id"],))
    _release_backup(backup_path)
    return {
        **plan,
        "dry_run": False,
        "deleted_event": True,
        "removed_files": removed,
        "cleanup_only": False,
    }


def _get_event(conn, event_id):
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return dict(row) if row is not None else None


def _active_acquisition_issues(conn, event_id) -> list[dict]:
    return [
        {
            "id": f"acquisition-job-{row['id']}",
            "kind": "active_acquisition",
            "title": row["title"],
            "artist": row["artist"],
            "job_id": row["id"],
            "status": row["status"],
            "resolution_options": [],
        }
        for row in conn.execute(
            "SELECT id, title, artist, status FROM acquisition_jobs "
            "WHERE event_id = ? AND status IN ('queued', 'running') ORDER BY id",
            (event_id,),
        )
    ]
