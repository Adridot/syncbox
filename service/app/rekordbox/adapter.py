from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from ..models import (
    EventDeletePreview,
    EventDeleteResponse,
    EventReview,
    ProcessInfo,
    RekordboxPlaylist,
    RekordboxStatus,
    RekordboxTag,
    StorageLayout,
)
from ..logging_setup import get_logger
from ..safety import assert_rekordbox_can_mutate, find_rekordbox_processes
from .paths import (
    content_path_lookup,
    find_content_by_path,
    path_is_under_roots,
    path_lookup_keys,
    resolve_volume_path,
    safe_timestamp,
)
from ..dedup import build_resolution_plan, find_duplicate_groups
from .content import (
    EVENT_IMPORTS_PLAYLIST_FOLDER_NAME,
    EVENT_MY_TAG_CATEGORY_NAME,
    add_rekordbox_content,
    build_event_delete_plan,
    content_length_ms,
    count_playlist_tracks,
    ensure_content_tag,
    ensure_event_my_tag,
    ensure_event_smart_playlist,
    event_delete_preview_from_plan,
    is_rekordbox_row_deleted,
    mark_rekordbox_row_deleted,
    reactivate_rekordbox_row,
)


"""RekordboxAdapter + its private read/cache/XML helpers."""

logger = get_logger("rekordbox")

# How many timestamped DB backups to keep by default. Each backup is a full
# copy of master.db (+ wal/shm) — they add up fast — so older ones are pruned
# after every new backup. Overridable per-install via the backupRetention
# setting; 0 disables rotation (keep everything).
DEFAULT_BACKUP_RETENTION = 15

# Reading the whole Rekordbox collection (open SQLCipher + iterate ~1.5k rows)
# costs ~0.4-0.9s and was happening on *every* event-review load and refresh.
# Cache the snapshot, keyed on the master.db (+ -wal) mtime/size so it auto-
# refreshes whenever the database changes (our writes or Rekordbox itself).
_LIBRARY_SNAPSHOT_CACHE: dict[str, tuple[Any, dict[str, Any]]] = {}


def invalidate_library_snapshot_cache() -> None:
    _LIBRARY_SNAPSHOT_CACHE.clear()


def _is_transient_db_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in ("disk i/o", "database is locked", "database is busy", "table is locked")
    )


def _read_rekordbox(database_dir: Any, reader: Any, *, attempts: int = 4, delay: float = 0.3):
    """Open a fresh Rekordbox connection, run ``reader(db)``, and return its
    result. Retries on *transient* SQLite errors — `disk I/O error` / `database
    is locked` are raised when Rekordbox (or one of our migration scripts) writes
    master.db at the same moment we read it. Non-transient errors propagate
    immediately; the caller handles the final failure."""
    import time

    from pyrekordbox import Rekordbox6Database

    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            database = Rekordbox6Database(db_dir=str(database_dir))
            try:
                return reader(database)
            finally:
                database.close()
        except Exception as exc:
            if attempt < attempts - 1 and _is_transient_db_error(exc):
                last_exc = exc
                time.sleep(delay * (attempt + 1))
                continue
            raise
    raise last_exc  # pragma: no cover - loop always returns or raises


class RekordboxAdapter:
    def __init__(
        self,
        database_dir: Path,
        storage_root: Path,
        permanent_path: str = "",
        manual_collection_path: str = "",
        backup_retention: int = DEFAULT_BACKUP_RETENTION,
    ) -> None:
        self.database_dir = database_dir.expanduser()
        self.storage_root = storage_root.expanduser()
        self._permanent_path = permanent_path.strip()
        self._manual_collection_path = manual_collection_path.strip()
        # 0 (or negative) disables rotation: keep every backup.
        self._backup_retention = int(backup_retention)
        self._backups_readable = True

    @property
    def database_file(self) -> Path:
        return self.database_dir / "master.db"

    @property
    def managed_root(self) -> Path:
        return self.storage_root / "_rekordbox_sync"

    def status(self) -> RekordboxStatus:
        processes = find_rekordbox_processes()
        return RekordboxStatus(
            databaseDir=str(self.database_dir),
            databaseFile=str(self.database_file),
            databaseExists=self.database_file.exists(),
            rekordboxRunning=bool(processes),
            mutationAllowed=not processes,
            runningProcesses=[
                ProcessInfo(pid=process.pid, command=process.command)
                for process in processes
            ],
        )

    def storage_layout(self) -> StorageLayout:
        root = self.managed_root
        permanent = self._permanent_path or str(root / "permanent")
        manual_collection = self._manual_collection_path or str(root / "manual_collection")
        return StorageLayout(
            root=str(root),
            inbox=str(root / "inbox"),
            permanent=permanent,
            events=str(root / "events"),
            manualCollection=manual_collection,
            backups=str(root / "backups"),
        )

    def ensure_storage_layout(self) -> StorageLayout:
        layout = self.storage_layout()
        for path in [
            layout.root,
            layout.inbox,
            layout.permanent,
            layout.events,
            layout.manual_collection,
            layout.backups,
        ]:
            Path(path).mkdir(parents=True, exist_ok=True)
        return layout

    def backup_database(self) -> Path:
        assert_rekordbox_can_mutate()
        layout = self.ensure_storage_layout()
        backup_root = Path(layout.backups)
        timestamp = safe_timestamp()
        target = backup_root / f"rekordbox-db-{timestamp}"
        # Timestamps have second resolution; disambiguate if two backups land in
        # the same second (e.g. a restore snapshots right after a backup).
        counter = 1
        while target.exists():
            target = backup_root / f"rekordbox-db-{timestamp}-{counter}"
            counter += 1
        target.mkdir(parents=True, exist_ok=False)

        for suffix in ["", "-wal", "-shm"]:
            source = Path(f"{self.database_file}{suffix}")
            if source.exists():
                shutil.copy2(source, target / source.name)

        # Rotate: drop the oldest backups beyond the retention window.
        self.prune_backups()

        return target

    def prune_backups(self, keep: int | None = None) -> dict[str, Any]:
        """Delete the oldest backups beyond the retention window (newest kept).

        Best-effort and TCC-safe: if the backups directory can't be listed
        (cloud storage + terminal-spawned process), it does nothing. Returns a
        small report so callers/UI can show how many were removed.
        """
        if keep is None:
            keep = self._backup_retention
        report = {"removed": 0, "kept": 0, "freedBytes": 0, "readable": True}
        if keep <= 0:
            # Rotation disabled.
            backups = self.list_backups()
            report["kept"] = len(backups)
            report["readable"] = backups is not None
            return report
        backups = self.list_backups()
        report["readable"] = self._backups_readable
        if not report["readable"]:
            return report
        report["kept"] = min(len(backups), keep)
        for backup in backups[keep:]:
            try:
                shutil.rmtree(backup["path"])
                report["removed"] += 1
                report["freedBytes"] += int(backup.get("sizeBytes", 0) or 0)
            except OSError as exc:
                logger.warning("Could not prune backup %s: %s", backup["path"], exc)
        return report

    def list_backups(self) -> list[dict[str, Any]]:
        """Timestamped Rekordbox DB backups, newest first.

        The backups directory may live under cloud storage where macOS TCC can
        deny directory listing from a terminal-spawned process; treat any OS
        error as "no readable backups" rather than failing the request.
        """
        backup_root = Path(self.storage_layout().backups)
        self._backups_readable = True
        try:
            if not backup_root.exists():
                return []
            entries = list(backup_root.iterdir())
        except OSError as exc:
            logger.warning("Cannot list backups in %s: %s", backup_root, exc)
            self._backups_readable = False
            return []
        backups: list[dict[str, Any]] = []
        for entry in entries:
            try:
                if not entry.is_dir() or not entry.name.startswith("rekordbox-db-"):
                    continue
                files = [child for child in entry.iterdir() if child.is_file()]
            except OSError:
                continue
            if not any(child.name == "master.db" for child in files):
                continue
            try:
                created = entry.stat().st_mtime
            except OSError:
                created = 0.0
            size = 0
            for child in files:
                try:
                    size += child.stat().st_size
                except OSError:
                    pass
            backups.append(
                {
                    "name": entry.name,
                    "path": str(entry),
                    "createdAt": created,
                    "sizeBytes": size,
                    "fileCount": len(files),
                }
            )
        backups.sort(key=lambda item: item["createdAt"], reverse=True)
        return backups

    def restore_backup(self, name: str) -> dict[str, Any]:
        """Restore a previous Rekordbox DB backup over the live database.

        Safety: refuses while Rekordbox runs, validates the name resolves
        strictly inside the backups root, and snapshots the *current* DB first
        so a restore is itself undoable.
        """
        # Validate input first (cheap, no mutation) so bad names fail fast even
        # while Rekordbox is open.
        if not name or "/" in name or "\\" in name or name in {".", ".."}:
            raise ValueError("Invalid backup name.")

        backup_root = Path(self.storage_layout().backups).resolve()
        candidate = (backup_root / name).resolve()
        if backup_root not in candidate.parents:
            raise ValueError("Backup is outside the managed backups directory.")
        if not candidate.is_dir():
            raise FileNotFoundError(f"Backup not found: {name}")
        master = candidate / "master.db"
        if not master.exists():
            raise FileNotFoundError(f"Backup is missing master.db: {name}")

        assert_rekordbox_can_mutate()

        # Snapshot the live DB before overwriting it.
        safety_backup = self.backup_database()

        self.database_dir.mkdir(parents=True, exist_ok=True)
        # Clear stale WAL/SHM so the restored master.db is authoritative.
        for suffix in ["-wal", "-shm"]:
            live = Path(f"{self.database_file}{suffix}")
            if live.exists():
                live.unlink()
        restored_files = 0
        for child in candidate.iterdir():
            if child.is_file():
                shutil.copy2(child, self.database_dir / child.name)
                restored_files += 1

        invalidate_library_snapshot_cache()
        return {
            "restored": name,
            "restoredFiles": restored_files,
            "safetyBackupPath": str(safety_backup),
        }

    def remove_event_directory(self, event_dir: str | None) -> bool:
        """Delete an event's on-disk folder (audio included) when the event is
        deleted.

        Safety: only removes a path strictly inside the managed *events* root.
        The permanent and manual_collection folders are siblings of events, so
        they can never be reached here — only files that physically live inside
        this event's folder are removed. Best-effort: cloud/permission errors
        are swallowed (the DB delete still stands; the folder can be cleaned
        later).
        """
        if not event_dir:
            return False
        target = Path(event_dir).expanduser()
        events_root = (self.managed_root / "events").expanduser()
        try:
            target_resolved = target.resolve()
            root_resolved = events_root.resolve()
        except OSError:
            target_resolved, root_resolved = target, events_root
        if root_resolved not in target_resolved.parents:
            return False  # never delete outside the managed events root
        if not target.exists():
            return False
        try:
            shutil.rmtree(target)
            return True
        except OSError:
            return False

    def _read_library_snapshot_uncached(self) -> dict[str, Any]:
        # _read_rekordbox imports pyrekordbox and its try/except below turns any
        # failure (incl. a missing pyrekordbox) into {available: False, reason}.
        def reader(database: Any) -> dict[str, Any]:
            tracks = []
            for content in database.get_content():
                if getattr(content, "rb_local_deleted", 0):
                    continue
                tracks.append(
                    {
                        "contentId": str(content.ID),
                        "title": str(getattr(content, "Title", "") or ""),
                        "artist": str(getattr(content, "ArtistName", "") or ""),
                        "durationMs": content_length_ms(content),
                        "filePath": resolve_volume_path(
                            str(getattr(content, "FolderPath", "") or ""),
                            self.storage_root,
                        ),
                        "isrc": str(getattr(content, "ISRC", "") or "") or None,
                    }
                )
            return {"available": True, "tracks": tracks}

        try:
            return _read_rekordbox(self.database_dir, reader)
        except Exception as exc:
            return {"available": False, "reason": str(exc), "tracks": []}

    def _snapshot_cache_key(self) -> tuple[Any, ...]:
        parts: list[Any] = []
        for suffix in ("", "-wal"):
            path = Path(f"{self.database_file}{suffix}")
            try:
                stat = path.stat()
                parts.append((suffix, stat.st_mtime_ns, stat.st_size))
            except OSError:
                parts.append((suffix, 0, 0))
        return tuple(parts)

    def read_library_snapshot(self) -> dict[str, Any]:
        """Rekordbox collection snapshot, memoised on the master.db mtime/size.

        Reading the whole collection costs ~0.4-0.9s; repeated reads (event
        loads, refreshes, matching) reuse the in-memory snapshot. It is
        recomputed only when the database file changes (our writes invalidate
        the cache; external Rekordbox edits bump the file mtime).
        """
        cache_id = str(self.database_file)
        key = self._snapshot_cache_key()
        cached = _LIBRARY_SNAPSHOT_CACHE.get(cache_id)
        if cached is not None and cached[0] == key:
            return cached[1]
        snapshot = self._read_library_snapshot_uncached()
        if snapshot.get("available"):
            _LIBRARY_SNAPSHOT_CACHE[cache_id] = (key, snapshot)
        return snapshot

    def collection_stats(self) -> dict[str, Any]:
        """Aggregate health metrics about the Rekordbox collection."""

        # _read_rekordbox imports pyrekordbox; its try/except below degrades any
        # failure (incl. a missing pyrekordbox) to {available: False, reason}.
        def reader(database: Any) -> dict[str, Any]:
            contents = [
                content
                for content in database.get_content()
                if not is_rekordbox_row_deleted(content)
            ]
            tagged_ids = {
                str(song.ContentID)
                for song in database.get_my_tag_songs()
                if not is_rekordbox_row_deleted(song)
            }
            total = len(contents)
            tagged = sum(1 for content in contents if str(content.ID) in tagged_ids)
            without_isrc = sum(
                1 for content in contents if not str(getattr(content, "ISRC", "") or "").strip()
            )
            without_artist = sum(
                1 for content in contents if not str(getattr(content, "ArtistName", "") or "").strip()
            )
            return {
                "available": True,
                "total": total,
                "tagged": tagged,
                "untagged": total - tagged,
                "withoutIsrc": without_isrc,
                "withoutArtist": without_artist,
            }

        try:
            return _read_rekordbox(self.database_dir, reader)
        except Exception as exc:
            return {"available": False, "reason": str(exc)}

    def assert_mutation_ready(self) -> None:
        assert_rekordbox_can_mutate()
        if not self.database_file.exists():
            raise FileNotFoundError(f"Rekordbox database not found: {self.database_file}")

    def list_tags(self) -> list[RekordboxTag]:
        try:
            from pyrekordbox import Rekordbox6Database
        except Exception as exc:
            raise RuntimeError(f"pyrekordbox is not available: {exc}") from exc

        database = Rekordbox6Database(db_dir=str(self.database_dir))
        try:
            tags = []
            for tag in database.get_my_tag():
                if getattr(tag, "rb_local_deleted", 0):
                    continue
                tags.append(
                    RekordboxTag(
                        id=str(tag.ID),
                        name=str(getattr(tag, "Name", "") or ""),
                        parentId=str(getattr(tag, "ParentID", "") or "") or None,
                    )
                )
            return sorted(tags, key=lambda tag: tag.name.lower())
        finally:
            database.close()

    def list_playlists(self) -> list[RekordboxPlaylist]:
        try:
            from pyrekordbox import Rekordbox6Database
        except Exception as exc:
            raise RuntimeError(f"pyrekordbox is not available: {exc}") from exc

        database = Rekordbox6Database(db_dir=str(self.database_dir))
        try:
            playlists = []
            for playlist in database.get_playlist():
                if getattr(playlist, "rb_local_deleted", 0):
                    continue
                playlists.append(
                    RekordboxPlaylist(
                        id=str(playlist.ID),
                        name=str(getattr(playlist, "Name", "") or ""),
                        parentId=str(getattr(playlist, "ParentID", "") or "") or None,
                        isFolder=bool(getattr(playlist, "is_folder", False)),
                        isSmartPlaylist=bool(getattr(playlist, "is_smart_playlist", False)),
                        trackCount=count_playlist_tracks(database, playlist),
                    )
                )
            return sorted(playlists, key=lambda playlist: playlist.name.lower())
        finally:
            database.close()

    def apply_event_import(self, review: EventReview) -> dict[str, Any]:
        self.assert_mutation_ready()
        backup_path = self.backup_database()

        try:
            from pyrekordbox import Rekordbox6Database
            from pyrekordbox.db6 import tables
            from pyrekordbox.db6.smartlist import Operator, SmartList
        except Exception as exc:
            raise RuntimeError(f"pyrekordbox is not available: {exc}") from exc

        xml_path = self.database_dir / "masterPlaylists6.xml"
        xml_backup: bytes | None = None
        if xml_path.exists():
            xml_backup = xml_path.read_bytes()

        database = Rekordbox6Database(db_dir=str(self.database_dir))
        imported = 0
        tagged = 0
        event_playlist_name = review.event_name
        try:
            event_tag = ensure_event_my_tag(
                database,
                tables,
                review.default_tag,
                EVENT_MY_TAG_CATEGORY_NAME,
            )

            all_content = list(database.get_content())
            content_by_id = {
                str(content.ID): content
                for content in all_content
                if not is_rekordbox_row_deleted(content)
            }
            content_by_path = content_path_lookup(
                (
                    content
                    for content in all_content
                    if not is_rekordbox_row_deleted(content)
                ),
                self.storage_root,
            )
            deleted_content_by_path = content_path_lookup(
                (content for content in all_content if is_rekordbox_row_deleted(content)),
                self.storage_root,
            )

            for track in review.tracks:
                if track.status not in {"matched", "ready"}:
                    continue
                content = None
                if track.rekordbox_content_id:
                    content = content_by_id.get(str(track.rekordbox_content_id))
                if content is None and track.staging_file_path:
                    file_path = Path(track.staging_file_path)
                    content = find_content_by_path(
                        content_by_path, file_path, self.storage_root
                    )
                    if content is None:
                        content = find_content_by_path(
                            deleted_content_by_path, file_path, self.storage_root
                        )
                        if content is not None:
                            reactivate_rekordbox_row(content)
                            imported += 1
                        else:
                            content = add_rekordbox_content(
                                database,
                                tables,
                                str(file_path),
                                artist=", ".join(track.artists),
                                storage_root=self.storage_root,
                                Title=track.title,
                                ISRC=track.isrc or "",
                                Length=max(1, round(track.duration_ms / 1000)),
                            )
                            imported += 1
                        content_by_id[str(content.ID)] = content
                        for key in path_lookup_keys(file_path, self.storage_root):
                            content_by_path[key] = content

                if content is None:
                    raise RuntimeError(f"Could not resolve Rekordbox content for {track.title}.")

                ensure_content_tag(database, tables, content, event_tag)
                tagged += 1

            playlist = ensure_event_smart_playlist(
                database,
                name=event_playlist_name,
                event_tag=event_tag,
                operator=int(Operator.CONTAINS),
                smart_list_class=SmartList,
            )
            event_playlist_name = str(getattr(playlist, "Name", event_playlist_name))

            database.commit()
            invalidate_library_snapshot_cache()

            if xml_backup is not None:
                xml_path.write_bytes(xml_backup)

            return {
                "backup_path": str(backup_path),
                "imported": imported,
                "tagged": tagged,
                "smart_playlist": event_playlist_name,
            }
        except Exception:
            if hasattr(database, "rollback"):
                database.rollback()
            if xml_backup is not None and xml_path.exists():
                xml_path.write_bytes(xml_backup)
            raise
        finally:
            database.close()

    def repair_event_import_structure(self, review: EventReview) -> dict[str, Any]:
        self.assert_mutation_ready()
        backup_path = self.backup_database()

        try:
            from pyrekordbox import Rekordbox6Database
            from pyrekordbox.db6 import tables
            from pyrekordbox.db6.smartlist import Operator, SmartList
        except Exception as exc:
            raise RuntimeError(f"pyrekordbox is not available: {exc}") from exc

        database = Rekordbox6Database(db_dir=str(self.database_dir))
        event_playlist_name = review.event_name
        try:
            event_tag = ensure_event_my_tag(
                database,
                tables,
                review.default_tag,
                EVENT_MY_TAG_CATEGORY_NAME,
            )
            playlist = ensure_event_smart_playlist(
                database,
                name=event_playlist_name,
                event_tag=event_tag,
                operator=int(Operator.CONTAINS),
                smart_list_class=SmartList,
            )
            database.commit()
            return {
                "backup_path": str(backup_path),
                "tag_id": str(event_tag.ID),
                "tag_parent": EVENT_MY_TAG_CATEGORY_NAME,
                "playlist_id": str(playlist.ID),
                "playlist": str(getattr(playlist, "Name", event_playlist_name)),
                "playlist_folder": EVENT_IMPORTS_PLAYLIST_FOLDER_NAME,
            }
        except Exception:
            if hasattr(database, "rollback"):
                database.rollback()
            raise
        finally:
            database.close()

    def preview_event_delete(self, review: EventReview) -> EventDeletePreview:
        # Read-only: opens the DB to compute what *would* be deleted. It must
        # work even while Rekordbox is running so the user can see the impact;
        # only the actual delete (delete_event_import) requires mutation rights.
        try:
            from pyrekordbox import Rekordbox6Database
        except Exception as exc:
            raise RuntimeError(f"pyrekordbox is not available: {exc}") from exc

        try:
            database = Rekordbox6Database(db_dir=str(self.database_dir))
        except Exception as exc:
            raise RuntimeError(
                f"Cannot read Rekordbox database: {exc} — close Rekordbox and retry"
            ) from exc
        try:
            plan = build_event_delete_plan(
                database,
                event_tag_name=review.default_tag,
                protected_roots=[
                    Path(self.storage_layout().permanent),
                    Path(self.storage_layout().manual_collection),
                ],
            )
            return event_delete_preview_from_plan(review, plan)
        finally:
            database.close()

    def delete_event_import(self, review: EventReview) -> EventDeleteResponse:
        self.assert_mutation_ready()
        backup_path = self.backup_database()

        try:
            from pyrekordbox import Rekordbox6Database
        except Exception as exc:
            raise RuntimeError(f"pyrekordbox is not available: {exc}") from exc

        database = Rekordbox6Database(db_dir=str(self.database_dir))
        try:
            plan = build_event_delete_plan(
                database,
                event_tag_name=review.default_tag,
                protected_roots=[
                    Path(self.storage_layout().permanent),
                    Path(self.storage_layout().manual_collection),
                ],
            )
            for row in plan["event_tag_rows"]:
                mark_rekordbox_row_deleted(row)
            for content in plan["delete_contents"]:
                mark_rekordbox_row_deleted(content)
            for row in plan["event_mytag_rows"]:
                mark_rekordbox_row_deleted(row)
            for row in plan["event_playlist_rows"]:
                mark_rekordbox_row_deleted(row)
            database.commit()
            invalidate_library_snapshot_cache()

            # Remove the event playlist from the exported XML. Cover both the
            # current name (event name) and the legacy "<name> - Smart".
            _remove_playlist_from_xml(self.database_dir, review.default_tag)
            _remove_playlist_from_xml(self.database_dir, f"{review.default_tag} - Smart")

            preview = event_delete_preview_from_plan(review, plan)
            return EventDeleteResponse(
                **preview.model_dump(by_alias=True),
                backupPath=str(backup_path),
                deletedFromRekordbox=len(plan["delete_contents"]),
                removedEventTags=len(plan["event_tag_rows"]),
                localEventDeleted=True,
            )
        except Exception:
            if hasattr(database, "rollback"):
                database.rollback()
            raise
        finally:
            database.close()

    def apply_library_import(self, review: Any) -> dict[str, Any]:
        self.assert_mutation_ready()
        backup_path = self.backup_database()

        try:
            from pyrekordbox import Rekordbox6Database
            from pyrekordbox.db6 import tables
        except Exception as exc:
            raise RuntimeError(f"pyrekordbox is not available: {exc}") from exc

        xml_path = self.database_dir / "masterPlaylists6.xml"
        xml_backup: bytes | None = None
        if xml_path.exists():
            xml_backup = xml_path.read_bytes()

        database = Rekordbox6Database(db_dir=str(self.database_dir))
        imported = 0
        tagged = 0
        try:
            all_tags = {
                str(tag.Name): tag
                for tag in database.get_my_tag()
                if not getattr(tag, "rb_local_deleted", 0)
            }
            requested_tags = {
                tag_name
                for track in review.tracks
                if track.status in {"matched", "ready"}
                for tag_name in track.tags
                if tag_name.strip()
            }
            missing_tags = sorted(tag_name for tag_name in requested_tags if tag_name not in all_tags)
            if missing_tags:
                raise RuntimeError(
                    "These MyTags must already exist before applying the library import: "
                    + ", ".join(missing_tags)
                )

            all_content = list(database.get_content())
            content_by_id = {
                str(content.ID): content
                for content in all_content
                if not is_rekordbox_row_deleted(content)
            }
            content_by_path = content_path_lookup(
                (
                    content
                    for content in all_content
                    if not is_rekordbox_row_deleted(content)
                ),
                self.storage_root,
            )
            deleted_content_by_path = content_path_lookup(
                (content for content in all_content if is_rekordbox_row_deleted(content)),
                self.storage_root,
            )

            for track in review.tracks:
                if track.status not in {"matched", "ready"}:
                    continue
                content = None
                if track.rekordbox_content_id:
                    content = content_by_id.get(str(track.rekordbox_content_id))
                if content is None and track.staging_file_path:
                    # The app never moves files: macOS TCC blocks file operations
                    # on Dropbox/iCloud CloudStorage from this process. Reference
                    # the downloaded file where it already is; consolidation into
                    # the canonical Collection is done by migrate_collection.py.
                    file_path = Path(track.staging_file_path)
                    content = find_content_by_path(
                        content_by_path, file_path, self.storage_root
                    )
                    if content is None:
                        content = find_content_by_path(
                            deleted_content_by_path, file_path, self.storage_root
                        )
                        if content is not None:
                            reactivate_rekordbox_row(content)
                            imported += 1
                        else:
                            content = add_rekordbox_content(
                                database,
                                tables,
                                str(file_path),
                                artist=", ".join(track.artists),
                                storage_root=self.storage_root,
                                Title=track.title,
                                ISRC=track.isrc or "",
                                Length=max(1, round(track.duration_ms / 1000)),
                            )
                            imported += 1
                        content_by_id[str(content.ID)] = content
                        for key in path_lookup_keys(file_path, self.storage_root):
                            content_by_path[key] = content

                if content is None:
                    raise RuntimeError(f"Could not resolve Rekordbox content for {track.title}.")

                for tag_name in dict.fromkeys(track.tags):
                    ensure_content_tag(database, tables, content, all_tags[tag_name])
                    tagged += 1

            if imported > 0 or tagged > 0:
                database.commit()
                invalidate_library_snapshot_cache()
            else:
                database.rollback()

            if xml_backup is not None:
                xml_path.write_bytes(xml_backup)

            return {
                "backup_path": str(backup_path),
                "imported": imported,
                "tagged": tagged,
            }
        except Exception:
            if hasattr(database, "rollback"):
                database.rollback()
            if xml_backup is not None and xml_path.exists():
                xml_path.write_bytes(xml_backup)
            raise
        finally:
            database.close()

    # --- Duplicate detection -------------------------------------------------

    def _protected_roots(self) -> list[Path]:
        layout = self.storage_layout()
        return [Path(layout.permanent), Path(layout.manual_collection)]

    def read_dedup_snapshot(self) -> dict[str, Any]:
        """Heavier collection read enriched with the signals needed for
        duplicate detection and keeper scoring (format, bitrate, cues, playlist
        memberships, tag counts, on-disk existence). Not cached: only run on
        demand from the Duplicates view, never on the hot refresh path.
        """
        protected_roots = self._protected_roots()

        def reader(database: Any) -> dict[str, Any]:
            from pyrekordbox.db6 import tables

            # Per-content aggregate counts (one pass each).
            cue_counts: dict[str, int] = {}
            for cue in database.get_cue():
                if is_rekordbox_row_deleted(cue):
                    continue
                key = str(getattr(cue, "ContentID", "") or "")
                cue_counts[key] = cue_counts.get(key, 0) + 1

            playlist_counts: dict[str, int] = {}
            for row in database.query(tables.DjmdSongPlaylist):
                if is_rekordbox_row_deleted(row):
                    continue
                key = str(getattr(row, "ContentID", "") or "")
                playlist_counts[key] = playlist_counts.get(key, 0) + 1

            tag_counts: dict[str, int] = {}
            for row in database.get_my_tag_songs():
                if is_rekordbox_row_deleted(row):
                    continue
                key = str(getattr(row, "ContentID", "") or "")
                tag_counts[key] = tag_counts.get(key, 0) + 1

            tracks = []
            for content in database.get_content():
                if is_rekordbox_row_deleted(content):
                    continue
                cid = str(content.ID)
                real_path = resolve_volume_path(
                    str(getattr(content, "FolderPath", "") or ""),
                    self.storage_root,
                )
                missing = False
                if real_path:
                    try:
                        missing = not Path(real_path).exists()
                    except OSError:
                        missing = False
                bpm_raw = getattr(content, "BPM", None)
                tracks.append(
                    {
                        "contentId": cid,
                        "title": str(getattr(content, "Title", "") or ""),
                        "artist": str(getattr(content, "ArtistName", "") or ""),
                        "durationMs": content_length_ms(content),
                        "isrc": str(getattr(content, "ISRC", "") or "") or None,
                        "filePath": real_path,
                        "fileName": str(getattr(content, "FileNameL", "") or "")
                        or (Path(real_path).name if real_path else None),
                        "fileType": _file_type_name(getattr(content, "FileType", None)),
                        "bitRate": _int_or_none(getattr(content, "BitRate", None)),
                        "sampleRate": _int_or_none(getattr(content, "SampleRate", None)),
                        "bitDepth": _int_or_none(getattr(content, "BitDepth", None)),
                        "fileSize": _int_or_none(getattr(content, "FileSize", None)),
                        "bpm": (float(bpm_raw) / 100.0) if bpm_raw else None,
                        "rating": _int_or_none(getattr(content, "Rating", None)),
                        "cueCount": cue_counts.get(cid, 0),
                        "playlistCount": playlist_counts.get(cid, 0),
                        "tagCount": tag_counts.get(cid, 0),
                        "analysed": bool(getattr(content, "Analysed", 0)),
                        "protected": path_is_under_roots(real_path, protected_roots),
                        "fileMissing": missing,
                        "dateCreated": str(getattr(content, "DateCreated", "") or "")
                        or None,
                    }
                )
            return {"available": True, "tracks": tracks}

        try:
            return _read_rekordbox(self.database_dir, reader)
        except Exception as exc:
            return {"available": False, "reason": str(exc), "tracks": []}

    def scan_duplicates(
        self,
        *,
        strategies: list[str],
        fuzzy_threshold: float,
        dismissed: set[str],
    ) -> dict[str, Any]:
        snapshot = self.read_dedup_snapshot()
        if not snapshot.get("available"):
            return {
                "available": False,
                "reason": snapshot.get("reason"),
                "totalTracks": 0,
                "strategies": strategies,
                "groups": [],
            }
        tracks = snapshot["tracks"]
        groups = find_duplicate_groups(
            tracks,
            strategies=strategies,
            fuzzy_threshold=fuzzy_threshold,
            dismissed=dismissed,
        )
        return {
            "available": True,
            "reason": None,
            "totalTracks": len(tracks),
            "strategies": strategies,
            "groups": groups,
        }

    def resolve_duplicates(
        self,
        items: list[Any],
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Apply duplicate resolutions: relink playlist/tag memberships from the
        removed copies onto the keeper, then soft-delete the removed rows and,
        when allowed, delete their files on disk (never under a protected root).

        ``items`` are ``DuplicateResolutionItem``-shaped objects.
        """
        result = {
            "backupPath": None,
            "removedFromRekordbox": 0,
            "filesDeleted": 0,
            "relinkedPlaylists": 0,
            "relinkedTags": 0,
            "skippedProtected": 0,
            "dismissed": 0,
            "dryRun": dry_run,
            "warnings": [],
        }
        if not items:
            return result

        # Build a fresh snapshot keyed by id for plan-building / safety checks.
        snapshot = self.read_dedup_snapshot()
        if not snapshot.get("available"):
            raise RuntimeError(
                snapshot.get("reason") or "Cannot read Rekordbox database."
            )
        tracks_by_id = {str(t["contentId"]): t for t in snapshot["tracks"]}

        plans = []
        files_to_delete: list[str] = []
        for item in items:
            keeper = str(getattr(item, "keeper_content_id"))
            remove_ids = [str(x) for x in getattr(item, "remove_content_ids", [])]
            allow_delete = bool(getattr(item, "delete_files", False))
            plan = build_resolution_plan(
                tracks_by_id,
                keeper_content_id=keeper,
                remove_content_ids=remove_ids,
                allow_file_delete=allow_delete,
            )
            plans.append(plan)
            files_to_delete.extend(plan["files_to_delete"])
            result["skippedProtected"] += len(plan["skipped_protected"])
            result["warnings"].extend(plan["warnings"])

        if dry_run:
            result["removedFromRekordbox"] = sum(
                len(p["remove_content_ids"]) for p in plans
            )
            result["filesDeleted"] = len(files_to_delete)
            return result

        self.assert_mutation_ready()
        backup_path = self.backup_database()
        result["backupPath"] = str(backup_path)

        try:
            from pyrekordbox import Rekordbox6Database
            from pyrekordbox.db6 import tables
        except Exception as exc:
            raise RuntimeError(f"pyrekordbox is not available: {exc}") from exc

        database = Rekordbox6Database(db_dir=str(self.database_dir))
        try:
            for plan in plans:
                keeper = plan["keeper_content_id"]
                for loser in plan["remove_content_ids"]:
                    relinked_pl, relinked_tag = _relink_memberships(
                        database, tables, loser, keeper
                    )
                    result["relinkedPlaylists"] += relinked_pl
                    result["relinkedTags"] += relinked_tag
                    content = _content_by_id(database, tables, loser)
                    if content is not None:
                        mark_rekordbox_row_deleted(content)
                        result["removedFromRekordbox"] += 1
            database.commit()
            invalidate_library_snapshot_cache()
        except Exception:
            if hasattr(database, "rollback"):
                database.rollback()
            raise
        finally:
            database.close()

        # File deletion happens only after the DB commit succeeded.
        for path_str in files_to_delete:
            try:
                file_path = Path(path_str)
                if file_path.exists():
                    file_path.unlink()
                    result["filesDeleted"] += 1
            except OSError as exc:
                result["warnings"].append(f"Could not delete {path_str}: {exc}")

        return result


def _file_type_name(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        from pyrekordbox.db6.tables import FileType

        return FileType(int(value)).name
    except Exception:
        return str(value)


def _int_or_none(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _content_by_id(database: Any, tables: Any, content_id: str) -> Any | None:
    row = database.query(tables.DjmdContent).filter_by(ID=str(content_id)).first()
    return row


def _relink_memberships(
    database: Any, tables: Any, loser_id: str, keeper_id: str
) -> tuple[int, int]:
    """Move playlist and MyTag memberships from ``loser_id`` onto ``keeper_id``
    so removing a duplicate never drops the keeper out of a playlist or tag.

    Re-points each membership row, skipping any where the keeper is already a
    member (those rows are soft-deleted to avoid duplicates).
    """
    relinked_playlists = 0
    relinked_tags = 0

    keeper_playlists = {
        str(getattr(r, "PlaylistID", "") or "")
        for r in database.query(tables.DjmdSongPlaylist).filter_by(ContentID=str(keeper_id))
        if not is_rekordbox_row_deleted(r)
    }
    for row in database.query(tables.DjmdSongPlaylist).filter_by(ContentID=str(loser_id)):
        if is_rekordbox_row_deleted(row):
            continue
        playlist_id = str(getattr(row, "PlaylistID", "") or "")
        if playlist_id in keeper_playlists:
            mark_rekordbox_row_deleted(row)
            continue
        row.ContentID = str(keeper_id)
        row.rb_local_synced = 0
        keeper_playlists.add(playlist_id)
        relinked_playlists += 1

    keeper_tags = {
        str(getattr(r, "MyTagID", "") or "")
        for r in database.query(tables.DjmdSongMyTag).filter_by(ContentID=str(keeper_id))
        if not is_rekordbox_row_deleted(r)
    }
    for row in database.query(tables.DjmdSongMyTag).filter_by(ContentID=str(loser_id)):
        if is_rekordbox_row_deleted(row):
            continue
        tag_id = str(getattr(row, "MyTagID", "") or "")
        if tag_id in keeper_tags:
            mark_rekordbox_row_deleted(row)
            continue
        row.ContentID = str(keeper_id)
        row.rb_local_synced = 0
        keeper_tags.add(tag_id)
        relinked_tags += 1

    return relinked_playlists, relinked_tags


def _remove_playlist_from_xml(database_dir: Path, playlist_name: str) -> None:
    xml_path = database_dir / "masterPlaylists6.xml"
    if not xml_path.exists():
        return

    backup_path = xml_path.with_suffix(f".xml.bak-{safe_timestamp()}")
    shutil.copy2(xml_path, backup_path)

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        _remove_xml_node_by_name(root, playlist_name)
        ET.indent(tree, space="  ")
        tree.write(str(xml_path), encoding="utf-8", xml_declaration=True)
    except Exception:
        shutil.copy2(backup_path, xml_path)
        raise


def _remove_xml_node_by_name(element: ET.Element, name: str) -> None:
    for child in list(element):
        if child.get("Name") == name:
            element.remove(child)
        else:
            _remove_xml_node_by_name(child, name)
