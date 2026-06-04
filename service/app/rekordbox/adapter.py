from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from ..models import (
    EventDeletePreview,
    EventDeleteResponse,
    EventReview,
    ProcessInfo,
    RekordboxStatus,
    RekordboxTag,
    StorageLayout,
)
from ..logging_setup import get_logger
from ..safety import assert_rekordbox_can_mutate, find_rekordbox_processes
from .paths import (
    content_folder_path,
    content_path_lookup,
    find_content_by_path,
    path_is_under_roots,
    path_lookup_keys,
    resolve_volume_path,
    safe_timestamp,
)
from ..dedup import build_resolution_plan, find_duplicate_groups
from .content import (
    EVENT_MY_TAG_CATEGORY_NAME,
    add_rekordbox_content,
    build_event_delete_plan,
    content_length_ms,
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
# A single enriched snapshot now backs the library view, collection stats,
# duplicate detection and missing-file detection — read once, cached, keyed on
# the master.db (+ -wal) mtime/size so it auto-refreshes whenever the database
# changes (our writes invalidate it; external Rekordbox edits bump the mtime).
_LIBRARY_SNAPSHOT_CACHE: dict[str, tuple[Any, dict[str, Any]]] = {}
# On-disk existence is the only expensive signal (it stats cloud-stored files),
# so it is cached separately on the same key and computed lazily on first use.
_FILE_MISSING_CACHE: dict[str, tuple[Any, dict[str, bool]]] = {}


def invalidate_library_snapshot_cache() -> None:
    _LIBRARY_SNAPSHOT_CACHE.clear()
    _FILE_MISSING_CACHE.clear()


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

    def _read_collection_uncached(self) -> dict[str, Any]:
        """Read the whole collection into enriched per-track dicts (one DB open).

        Everything except on-disk existence (the only cloud-I/O signal, computed
        lazily by ``_file_missing_map``) is gathered here: identity, audio
        quality, and the cue/playlist/tag counts used for keeper scoring — via
        one bulk pass over each side table. ``_read_rekordbox``'s try/except
        degrades any failure (incl. missing pyrekordbox) to {available: False}.
        """
        protected_roots = self._protected_roots()

        def reader(database: Any) -> dict[str, Any]:
            from pyrekordbox.db6 import tables

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
                        "dateCreated": str(getattr(content, "DateCreated", "") or "")
                        or None,
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

    def read_collection_snapshot(self) -> dict[str, Any]:
        """Enriched collection snapshot, memoised on the master.db mtime/size.

        Single source of truth for the library view, collection stats, duplicate
        detection and missing-file detection. Recomputed only when the database
        file changes (our writes invalidate the cache; external Rekordbox edits
        bump the file mtime).
        """
        cache_id = str(self.database_file)
        key = self._snapshot_cache_key()
        cached = _LIBRARY_SNAPSHOT_CACHE.get(cache_id)
        if cached is not None and cached[0] == key:
            return cached[1]
        snapshot = self._read_collection_uncached()
        if snapshot.get("available"):
            _LIBRARY_SNAPSHOT_CACHE[cache_id] = (key, snapshot)
        return snapshot

    # Back-compat alias: callers that only need identity/path fields.
    read_library_snapshot = read_collection_snapshot

    def _file_missing_map(self, tracks: list[dict[str, Any]]) -> dict[str, bool]:
        """contentId -> "file is gone from disk", cached on the DB mtime.

        This is the only signal that touches cloud-stored files, so it is split
        out of the snapshot and computed once for Duplicates + Missing to share.
        """
        cache_id = str(self.database_file)
        key = self._snapshot_cache_key()
        cached = _FILE_MISSING_CACHE.get(cache_id)
        if cached is not None and cached[0] == key:
            return cached[1]
        missing: dict[str, bool] = {}
        for track in tracks:
            path = track.get("filePath")
            try:
                missing[str(track["contentId"])] = bool(path) and not Path(path).exists()
            except OSError:
                missing[str(track["contentId"])] = False
        _FILE_MISSING_CACHE[cache_id] = (key, missing)
        return missing

    def collection_stats(self) -> dict[str, Any]:
        """Aggregate health metrics, derived from the shared cached snapshot."""
        snapshot = self.read_collection_snapshot()
        if not snapshot.get("available"):
            return {"available": False, "reason": snapshot.get("reason")}
        contents = snapshot["tracks"]
        total = len(contents)
        tagged = sum(1 for t in contents if t["tagCount"] > 0)
        without_isrc = sum(1 for t in contents if not (t.get("isrc") or "").strip())
        without_artist = sum(1 for t in contents if not (t.get("artist") or "").strip())
        return {
            "available": True,
            "total": total,
            "tagged": tagged,
            "untagged": total - tagged,
            "withoutIsrc": without_isrc,
            "withoutArtist": without_artist,
        }

    def assert_mutation_ready(self) -> None:
        assert_rekordbox_can_mutate()
        if not self.database_file.exists():
            raise FileNotFoundError(f"Rekordbox database not found: {self.database_file}")

    @contextmanager
    def _mutate(self) -> Iterator[tuple[Any, Any, Path]]:
        """Unit-of-work for a Rekordbox DB mutation.

        Asserts it is safe to mutate (Rekordbox closed, DB present), snapshots a
        backup, opens the pyrekordbox database, and yields ``(database, tables,
        backup_path)``. On clean exit it commits and invalidates the collection
        snapshot cache; on any exception it rolls back and re-raises. The
        connection is always closed. Replaces the assert/backup/open/try/commit/
        except/rollback/finally/close boilerplate every mutation used to repeat.
        """
        self.assert_mutation_ready()
        backup_path = self.backup_database()
        try:
            from pyrekordbox import Rekordbox6Database
            from pyrekordbox.db6 import tables
        except Exception as exc:
            raise RuntimeError(f"pyrekordbox is not available: {exc}") from exc

        database = Rekordbox6Database(db_dir=str(self.database_dir))
        try:
            yield database, tables, backup_path
            database.commit()
            invalidate_library_snapshot_cache()
        except Exception:
            if hasattr(database, "rollback"):
                database.rollback()
            raise
        finally:
            database.close()

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

    # --- untagged review tool ------------------------------------------------

    def untagged_report(self) -> dict[str, Any]:
        """List collection tracks carrying no MyTag, with a "why / what to do"
        hint per track (junk, duplicate of a tagged song, alternate version, or
        a genuine track to review). Derived entirely from the cached snapshot."""
        from ..maintenance import (
            ACTION_DELETE,
            REASON_ALT_VERSION,
            REASON_DUP_OF_TAGGED,
            REASON_JUNK,
            TrackRow,
            classify_untagged,
        )

        snapshot = self.read_collection_snapshot()
        if not snapshot.get("available"):
            return {
                "available": False,
                "reason": snapshot.get("reason"),
                "tracks": [],
                "tags": [],
            }
        tracks = snapshot["tracks"]
        missing = self._file_missing_map(tracks)

        tagged_rows: list[TrackRow] = []
        untagged_rows: list[TrackRow] = []
        for track in tracks:
            row = TrackRow(
                content_id=str(track["contentId"]),
                artist=track.get("artist") or "",
                title=track.get("title") or "",
                folder_path=track.get("filePath") or "",
                is_tagged=int(track.get("tagCount", 0) or 0) > 0,
            )
            (tagged_rows if row.is_tagged else untagged_rows).append(row)

        decisions = {d.content_id: d for d in classify_untagged(tagged_rows, untagged_rows)}
        by_id = {str(track["contentId"]): track for track in tracks}
        reason_to_suggestion = {
            REASON_JUNK: "junk",
            REASON_DUP_OF_TAGGED: "dup_of_tagged",
            REASON_ALT_VERSION: "alt_version",
        }

        out: list[dict[str, Any]] = []
        for row in untagged_rows:
            track = by_id[row.content_id]
            decision = decisions.get(row.content_id)
            suggestion = "review"
            detail = ""
            if decision is not None and decision.action == ACTION_DELETE:
                suggestion = reason_to_suggestion.get(decision.reason, "review")
                if decision.reason == REASON_DUP_OF_TAGGED and decision.matched_tagged_title:
                    detail = decision.matched_tagged_title
            out.append(
                {
                    "contentId": row.content_id,
                    "title": track.get("title") or "",
                    "artist": track.get("artist") or "",
                    "durationMs": track.get("durationMs"),
                    "isrc": track.get("isrc"),
                    "filePath": track.get("filePath"),
                    "fileName": track.get("fileName"),
                    "playlistCount": int(track.get("playlistCount", 0) or 0),
                    "fileMissing": missing.get(row.content_id, False),
                    "protected": bool(track.get("protected", False)),
                    "dateCreated": track.get("dateCreated"),
                    "suggestion": suggestion,
                    "suggestionDetail": detail,
                }
            )

        order = {"junk": 0, "dup_of_tagged": 1, "alt_version": 2, "review": 3}
        out.sort(
            key=lambda r: (
                order.get(r["suggestion"], 3),
                (r["artist"] or "").lower(),
                (r["title"] or "").lower(),
            )
        )
        return {
            "available": True,
            "total": len(tracks),
            "untagged": len(out),
            "tracks": out,
            "tags": self.list_tags(),
        }

    def tag_untagged(
        self,
        content_ids: list[str],
        tag_name: str,
        category: str = "Genre",
    ) -> dict[str, Any]:
        """Apply an existing (or newly created) MyTag to the given tracks.

        If no MyTag with ``tag_name`` exists, one is created under the
        ``category`` MyTag category (default "Genre"). Soft, reversible, backed
        up first via :meth:`_mutate`."""
        from .content import create_my_tag, find_active_my_tag, find_my_tag_category

        clean_name = (tag_name or "").strip()
        if not clean_name:
            raise ValueError("A tag name is required.")
        ids = {str(cid) for cid in content_ids}
        if not ids:
            raise ValueError("No tracks selected.")

        tagged = 0
        created = False
        with self._mutate() as (database, tables, backup_path):
            tag = find_active_my_tag(database, clean_name)
            if tag is None:
                cat = find_my_tag_category(database, category)
                tag = create_my_tag(database, tables, clean_name, parent_id=str(cat.ID))
                created = True
            content_by_id = {
                str(content.ID): content
                for content in database.get_content()
                if not is_rekordbox_row_deleted(content)
            }
            for cid in ids:
                content = content_by_id.get(cid)
                if content is None:
                    continue
                ensure_content_tag(database, tables, content, tag)
                tagged += 1

        return {
            "backup_path": str(backup_path),
            "tagged": tagged,
            "created_tag": created,
            "tag_name": clean_name,
        }

    def delete_untagged(self, content_ids: list[str]) -> dict[str, Any]:
        """Soft-delete (mark rb_local_deleted) the given collection rows.

        Reversible: a backup is taken first and the row is only flagged deleted,
        never hard-removed; the file on disk is left untouched."""
        ids = {str(cid) for cid in content_ids}
        if not ids:
            raise ValueError("No tracks selected.")

        removed = 0
        with self._mutate() as (database, tables, backup_path):
            content_by_id = {
                str(content.ID): content
                for content in database.get_content()
                if not is_rekordbox_row_deleted(content)
            }
            for cid in ids:
                content = content_by_id.get(cid)
                if content is None:
                    continue
                mark_rekordbox_row_deleted(content)
                removed += 1

        return {
            "backup_path": str(backup_path),
            "removed": removed,
            "skipped_protected": 0,
        }

    def apply_event_import(self, review: EventReview) -> dict[str, Any]:
        # Rekordbox can overwrite masterPlaylists6.xml during our writes; snapshot
        # it so we can restore it whether the transaction succeeds or fails.
        xml_path = self.database_dir / "masterPlaylists6.xml"
        xml_backup: bytes | None = xml_path.read_bytes() if xml_path.exists() else None

        imported = 0
        tagged = 0
        event_playlist_name = review.event_name
        try:
            with self._mutate() as (database, tables, backup_path):
                from pyrekordbox.db6.smartlist import Operator, SmartList

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

            # Committed. Restore the XML snapshot pyrekordbox may have rewritten.
            if xml_backup is not None:
                xml_path.write_bytes(xml_backup)

            return {
                "backup_path": str(backup_path),
                "imported": imported,
                "tagged": tagged,
                "smart_playlist": event_playlist_name,
            }
        except Exception:
            # _mutate already rolled the DB back; just restore the XML snapshot.
            if xml_backup is not None and xml_path.exists():
                xml_path.write_bytes(xml_backup)
            raise

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
        with self._mutate() as (database, _tables, backup_path):
            plan = build_event_delete_plan(
                database,
                event_tag_name=review.default_tag,
                protected_roots=[
                    Path(self.storage_layout().permanent),
                    Path(self.storage_layout().manual_collection),
                ],
            )
            # Build the preview *before* leaving the session: committing expires
            # the ORM rows, so reading their titles (deletedSamples) afterwards
            # raises "instance is not bound to a Session". Capture it now while
            # the rows are still live.
            preview = event_delete_preview_from_plan(review, plan)
            deleted_count = len(plan["delete_contents"])
            removed_tag_count = len(plan["event_tag_rows"])
            for row in plan["event_tag_rows"]:
                mark_rekordbox_row_deleted(row)
            for content in plan["delete_contents"]:
                mark_rekordbox_row_deleted(content)
            for row in plan["event_mytag_rows"]:
                mark_rekordbox_row_deleted(row)
            for row in plan["event_playlist_rows"]:
                mark_rekordbox_row_deleted(row)

        # After commit: remove the event playlist from the exported XML. Cover
        # both the current name (event name) and the legacy "<name> - Smart".
        _remove_playlist_from_xml(self.database_dir, review.default_tag)
        _remove_playlist_from_xml(self.database_dir, f"{review.default_tag} - Smart")

        return EventDeleteResponse(
            **preview.model_dump(by_alias=True),
            backupPath=str(backup_path),
            deletedFromRekordbox=deleted_count,
            removedEventTags=removed_tag_count,
            localEventDeleted=True,
        )

    def apply_library_import(self, review: Any) -> dict[str, Any]:
        xml_path = self.database_dir / "masterPlaylists6.xml"
        xml_backup: bytes | None = xml_path.read_bytes() if xml_path.exists() else None

        imported = 0
        tagged = 0
        try:
            with self._mutate() as (database, tables, backup_path):
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
                missing_tags = sorted(
                    tag_name for tag_name in requested_tags if tag_name not in all_tags
                )
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
                        # The app never moves files: macOS TCC blocks file ops on
                        # Dropbox/iCloud CloudStorage from this process. Reference
                        # the downloaded file where it already is; consolidation
                        # into the canonical Collection is done by migrate_collection.
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

            # Committed. Restore the XML snapshot pyrekordbox may have rewritten.
            if xml_backup is not None:
                xml_path.write_bytes(xml_backup)

            return {
                "backup_path": str(backup_path),
                "imported": imported,
                "tagged": tagged,
            }
        except Exception:
            if xml_backup is not None and xml_path.exists():
                xml_path.write_bytes(xml_backup)
            raise

    # --- Duplicate detection -------------------------------------------------

    def _protected_roots(self) -> list[Path]:
        layout = self.storage_layout()
        return [Path(layout.permanent), Path(layout.manual_collection)]

    def read_dedup_snapshot(self) -> dict[str, Any]:
        """Enriched snapshot + on-disk existence, for duplicate / missing-file
        detection. Derives from the shared cached collection snapshot and only
        adds the lazily-computed (and separately cached) ``fileMissing`` flag.
        """
        snapshot = self.read_collection_snapshot()
        if not snapshot.get("available"):
            return {"available": False, "reason": snapshot.get("reason"), "tracks": []}
        missing = self._file_missing_map(snapshot["tracks"])
        tracks = [
            {**track, "fileMissing": missing.get(str(track["contentId"]), False)}
            for track in snapshot["tracks"]
        ]
        return {"available": True, "tracks": tracks}

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

    def find_missing_files(self) -> dict[str, Any]:
        """Collection rows whose audio file no longer exists on disk.

        Rekordbox keeps the DjmdContent entry (and its cues, playlist slots,
        tags) even after the underlying file is moved/renamed/deleted — the
        equivalent of "Display All Missing Files". Read-only.
        """
        snapshot = self.read_dedup_snapshot()
        if not snapshot.get("available"):
            return {
                "available": False,
                "reason": snapshot.get("reason"),
                "total": 0,
                "missing": 0,
                "tracks": [],
            }
        tracks = snapshot["tracks"]
        missing = [
            {
                "contentId": t["contentId"],
                "title": t["title"],
                "artist": t["artist"],
                "durationMs": t["durationMs"],
                "isrc": t["isrc"],
                "filePath": t["filePath"],
                "fileName": t["fileName"],
                "fileType": t["fileType"],
                "playlistCount": t["playlistCount"],
                "tagCount": t["tagCount"],
                "protected": t["protected"],
            }
            for t in tracks
            if t["fileMissing"]
        ]
        missing.sort(key=lambda t: (t["artist"].lower(), t["title"].lower()))
        return {
            "available": True,
            "reason": None,
            "total": len(tracks),
            "missing": len(missing),
            "tracks": missing,
        }

    def content_meta(self, content_id: str) -> dict[str, Any]:
        """Read one content row's metadata (read-only) for missing-file actions."""
        try:
            from pyrekordbox import Rekordbox6Database
            from pyrekordbox.db6 import tables
        except Exception as exc:
            raise RuntimeError(f"pyrekordbox is not available: {exc}") from exc

        database = Rekordbox6Database(db_dir=str(self.database_dir))
        try:
            content = (
                database.query(tables.DjmdContent).filter_by(ID=str(content_id)).first()
            )
            if content is None:
                raise KeyError(f"Content {content_id} not found.")
            real_path = resolve_volume_path(
                str(getattr(content, "FolderPath", "") or ""), self.storage_root
            )
            return {
                "contentId": str(content.ID),
                "title": str(getattr(content, "Title", "") or ""),
                "artist": str(getattr(content, "ArtistName", "") or ""),
                "isrc": str(getattr(content, "ISRC", "") or "") or None,
                "filePath": real_path,
                "fileName": str(getattr(content, "FileNameL", "") or ""),
            }
        finally:
            database.close()

    def relink_content(self, content_id: str, file_path: str) -> dict[str, Any]:
        """Point a collection row at a new on-disk file (fixes a missing file).

        Updates FolderPath/FileName/FileSize/FileType to the new location so the
        existing cues, tags and playlist slots are preserved. Backs up first.
        """
        new_path = Path(file_path).expanduser()
        if not new_path.exists() or not new_path.is_file():
            raise FileNotFoundError(f"File does not exist: {file_path}")

        with self._mutate() as (database, tables, backup_path):
            content = (
                database.query(tables.DjmdContent).filter_by(ID=str(content_id)).first()
            )
            if content is None:
                raise KeyError(f"Content {content_id} not found.")
            _point_content_at_file(content, new_path, self.storage_root, tables)
        return {
            "contentId": str(content_id),
            "filePath": str(new_path),
            "backupPath": str(backup_path),
        }

    def remove_content(self, content_id: str) -> dict[str, Any]:
        """Soft-delete a collection row (for orphans with no recoverable file)."""
        with self._mutate() as (database, tables, backup_path):
            content = (
                database.query(tables.DjmdContent).filter_by(ID=str(content_id)).first()
            )
            if content is None:
                raise KeyError(f"Content {content_id} not found.")
            mark_rekordbox_row_deleted(content)
        return {"contentId": str(content_id), "backupPath": str(backup_path)}

    def find_relink_candidates(self, content_id: str, *, limit: int = 8) -> list[dict[str, Any]]:
        """Search the managed storage tree for an existing file that matches a
        missing collection row, so a moved/renamed file can be re-linked without
        re-downloading. Matches by ISRC (tag) then by title/artist similarity.
        """
        from ..audio import read_audio_metadata
        from ..live_import import SUPPORTED_AUDIO_EXTENSIONS
        from ..matching import text_similarity

        meta = self.content_meta(content_id)
        target_isrc = (meta.get("isrc") or "").strip().upper()
        target_title = meta.get("title") or ""

        candidates: list[dict[str, Any]] = []
        roots = [
            Path(self.storage_layout().permanent),
            Path(self.storage_layout().manual_collection),
            Path(self.storage_layout().events),
            Path(self.storage_layout().inbox),
            self.storage_root / "rekordbox" / "Collection",
        ]
        seen: set[str] = set()
        for root in roots:
            if not root.exists():
                continue
            try:
                files = [
                    p
                    for p in root.rglob("*")
                    if p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
                ]
            except OSError:
                continue
            for path in files:
                key = str(path)
                if key in seen:
                    continue
                seen.add(key)
                file_meta = read_audio_metadata(path)
                file_isrc = (file_meta.get("isrc") or "").strip().upper()
                score = 0
                reason = ""
                if target_isrc and file_isrc and file_isrc == target_isrc:
                    score = 100
                    reason = "ISRC match"
                else:
                    title_sim = text_similarity(target_title, file_meta.get("title") or "")
                    name_sim = text_similarity(target_title, path.stem)
                    best = max(title_sim, name_sim)
                    if best >= 70:
                        score = int(best)
                        reason = "Title match"
                if score:
                    candidates.append(
                        {
                            "filePath": str(path),
                            "fileName": path.name,
                            "score": score,
                            "reason": reason,
                        }
                    )
        candidates.sort(key=lambda c: -c["score"])
        return candidates[:limit]

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

        if dry_run:
            result["removedFromRekordbox"] = sum(
                len(p["remove_content_ids"]) for p in plans
            )
            result["filesDeleted"] = len(files_to_delete)
            return result

        with self._mutate() as (database, tables, backup_path):
            result["backupPath"] = str(backup_path)
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


def _point_content_at_file(
    content: Any, new_path: Path, storage_root: Path, tables: Any
) -> None:
    """Re-point a content row at ``new_path`` (FolderPath/name/size/type), so a
    re-linked or re-downloaded file is adopted while keeping cues/tags/playlists.
    """
    # Volume-relative only inside the managed library, absolute elsewhere (a
    # relink target may live in event/permanent staging outside it) — otherwise
    # Rekordbox can't resolve it. See content_folder_path.
    content.FolderPath = content_folder_path(new_path, storage_root)
    content.FileNameL = new_path.name
    try:
        content.FileSize = new_path.stat().st_size
    except OSError:
        pass
    suffix = new_path.suffix.lstrip(".").upper()
    file_type = getattr(tables, "FileType", None)
    if suffix and file_type is not None and hasattr(file_type, suffix):
        content.FileType = getattr(file_type, suffix).value
    if hasattr(content, "rb_local_synced"):
        content.rb_local_synced = 0


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
