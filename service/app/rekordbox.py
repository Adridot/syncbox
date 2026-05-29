from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .models import (
    EventDeletePreview,
    EventDeleteResponse,
    EventReview,
    ProcessInfo,
    RekordboxPlaylist,
    RekordboxStatus,
    RekordboxTag,
    StorageLayout,
)
from .safety import assert_rekordbox_can_mutate, find_rekordbox_processes


EVENT_IMPORTS_PLAYLIST_FOLDER_NAME = "Event Imports"
EVENT_MY_TAG_CATEGORY_NAME = "Situation"


class RekordboxAdapter:
    def __init__(self, database_dir: Path, storage_root: Path) -> None:
        self.database_dir = database_dir.expanduser()
        self.storage_root = storage_root.expanduser()

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
        return StorageLayout(
            root=str(root),
            inbox=str(root / "inbox"),
            permanent=str(root / "permanent"),
            events=str(root / "events"),
            manualCollection=str(root / "manual_collection"),
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
        target.mkdir(parents=True, exist_ok=False)

        for suffix in ["", "-wal", "-shm"]:
            source = Path(f"{self.database_file}{suffix}")
            if source.exists():
                shutil.copy2(source, target / source.name)

        return target

    def read_library_snapshot(self) -> dict[str, Any]:
        try:
            from pyrekordbox import Rekordbox6Database
        except Exception as exc:
            return {
                "available": False,
                "reason": f"pyrekordbox is not installed or cannot be imported: {exc}",
                "tracks": [],
            }

        try:
            database = Rekordbox6Database(db_dir=str(self.database_dir))
            try:
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
                            "filePath": str(getattr(content, "FolderPath", "") or ""),
                            "isrc": str(getattr(content, "ISRC", "") or "") or None,
                        }
                    )
                return {"available": True, "tracks": tracks}
            finally:
                database.close()
        except Exception as exc:
            return {"available": False, "reason": str(exc), "tracks": []}

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

        database = Rekordbox6Database(db_dir=str(self.database_dir))
        imported = 0
        tagged = 0
        permanent = 0
        smart_playlist_name = f"{review.event_name} - Smart"
        try:
            all_tags = {
                str(tag.Name): tag
                for tag in database.get_my_tag()
                if not getattr(tag, "rb_local_deleted", 0)
            }
            event_tag = ensure_event_my_tag(
                database,
                tables,
                review.default_tag,
                EVENT_MY_TAG_CATEGORY_NAME,
            )
            all_tags[review.default_tag] = event_tag

            requested_tags = {
                tag_name
                for track in review.tracks
                for tag_name in track.tags
                if tag_name.strip()
            }
            missing_tags = sorted(tag_name for tag_name in requested_tags if tag_name not in all_tags)
            if missing_tags:
                raise RuntimeError(
                    "These MyTags must already exist before applying the event: "
                    + ", ".join(missing_tags)
                )

            all_content = list(database.get_content())
            content_by_id = {
                str(content.ID): content
                for content in all_content
                if not is_rekordbox_row_deleted(content)
            }
            content_by_path = content_path_lookup(
                content
                for content in all_content
                if not is_rekordbox_row_deleted(content)
            )
            deleted_content_by_path = content_path_lookup(
                content for content in all_content if is_rekordbox_row_deleted(content)
            )

            for track in review.tracks:
                if track.status not in {"matched", "ready"}:
                    continue
                content = None
                if track.rekordbox_content_id:
                    content = content_by_id.get(str(track.rekordbox_content_id))
                if content is None and track.staging_file_path:
                    original_path = Path(track.staging_file_path)
                    file_path = original_path
                    if track.permanent:
                        file_path = move_to_permanent(
                            original_path, Path(self.storage_layout().permanent)
                        )
                        if file_path.resolve() != original_path.resolve():
                            permanent += 1
                    content = find_content_by_path(content_by_path, file_path)
                    if content is None:
                        content = find_content_by_path(deleted_content_by_path, file_path)
                        if content is not None:
                            reactivate_rekordbox_row(content)
                            imported += 1
                        else:
                            content = add_rekordbox_content(
                                database,
                                tables,
                                str(file_path),
                                Title=track.title,
                                ISRC=track.isrc or "",
                                Length=max(1, round(track.duration_ms / 1000)),
                            )
                            imported += 1
                        content_by_id[str(content.ID)] = content
                        for key in path_lookup_keys(file_path):
                            content_by_path[key] = content

                if content is None:
                    raise RuntimeError(f"Could not resolve Rekordbox content for {track.title}.")

                tag_names = [review.default_tag, *track.tags]
                for tag_name in dict.fromkeys(tag_names):
                    ensure_content_tag(database, tables, content, all_tags[tag_name])
                    tagged += 1

            playlist = ensure_event_smart_playlist(
                database,
                name=smart_playlist_name,
                event_tag=event_tag,
                operator=int(Operator.CONTAINS),
                smart_list_class=SmartList,
            )
            smart_playlist_name = str(getattr(playlist, "Name", smart_playlist_name))

            database.commit()
            return {
                "backup_path": str(backup_path),
                "imported": imported,
                "tagged": tagged,
                "permanent": permanent,
                "smart_playlist": smart_playlist_name,
            }
        except Exception:
            if hasattr(database, "rollback"):
                database.rollback()
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
        smart_playlist_name = f"{review.event_name} - Smart"
        try:
            event_tag = ensure_event_my_tag(
                database,
                tables,
                review.default_tag,
                EVENT_MY_TAG_CATEGORY_NAME,
            )
            playlist = ensure_event_smart_playlist(
                database,
                name=smart_playlist_name,
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
                "playlist": str(getattr(playlist, "Name", smart_playlist_name)),
                "playlist_folder": EVENT_IMPORTS_PLAYLIST_FOLDER_NAME,
            }
        except Exception:
            if hasattr(database, "rollback"):
                database.rollback()
            raise
        finally:
            database.close()

    def preview_event_delete(self, review: EventReview) -> EventDeletePreview:
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
            database.commit()
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

        database = Rekordbox6Database(db_dir=str(self.database_dir))
        imported = 0
        tagged = 0
        permanent = 0
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
                content
                for content in all_content
                if not is_rekordbox_row_deleted(content)
            )
            deleted_content_by_path = content_path_lookup(
                content for content in all_content if is_rekordbox_row_deleted(content)
            )

            for track in review.tracks:
                if track.status not in {"matched", "ready"}:
                    continue
                content = None
                if track.rekordbox_content_id:
                    content = content_by_id.get(str(track.rekordbox_content_id))
                if content is None and track.staging_file_path:
                    original_path = Path(track.staging_file_path)
                    file_path = move_to_permanent(
                        original_path,
                        Path(self.storage_layout().permanent),
                    )
                    if file_path.resolve() != original_path.resolve():
                        permanent += 1
                    content = find_content_by_path(content_by_path, file_path)
                    if content is None:
                        content = find_content_by_path(deleted_content_by_path, file_path)
                        if content is not None:
                            reactivate_rekordbox_row(content)
                            imported += 1
                        else:
                            content = add_rekordbox_content(
                                database,
                                tables,
                                str(file_path),
                                Title=track.title,
                                ISRC=track.isrc or "",
                                Length=max(1, round(track.duration_ms / 1000)),
                            )
                            imported += 1
                        content_by_id[str(content.ID)] = content
                        for key in path_lookup_keys(file_path):
                            content_by_path[key] = content

                if content is None:
                    raise RuntimeError(f"Could not resolve Rekordbox content for {track.title}.")

                for tag_name in dict.fromkeys(track.tags):
                    ensure_content_tag(database, tables, content, all_tags[tag_name])
                    tagged += 1

            database.commit()
            return {
                "backup_path": str(backup_path),
                "imported": imported,
                "tagged": tagged,
                "permanent": permanent,
            }
        except Exception:
            if hasattr(database, "rollback"):
                database.rollback()
            raise
        finally:
            database.close()


def safe_timestamp() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y%m%d-%H%M%S")


def content_length_ms(content: Any) -> int | None:
    length = getattr(content, "Length", None)
    if length in (None, ""):
        return None
    try:
        return int(float(length) * 1000)
    except (TypeError, ValueError):
        return None


def count_playlist_tracks(database: Any, playlist: Any) -> int:
    if getattr(playlist, "is_folder", False):
        return 0
    try:
        return len(
            [
                song
                for song in database.get_playlist_songs(PlaylistID=playlist.ID)
                if not getattr(song, "rb_local_deleted", 0)
            ]
        )
    except Exception:
        return 0


def ensure_event_my_tag(
    database: Any,
    tables: Any,
    name: str,
    category_name: str,
) -> Any:
    category = find_my_tag_category(database, category_name)
    existing = find_active_my_tag(database, name)
    if existing is not None:
        if int(getattr(existing, "Attribute", 0) or 0) == 1:
            raise RuntimeError(f'MyTag "{name}" already exists as a category.')
        parent_id = str(getattr(existing, "ParentID", "") or "")
        if parent_id not in {"", "0", str(category.ID)}:
            raise RuntimeError(
                f'MyTag "{name}" already exists outside "{category_name}". '
                "Rename the event or move the tag in Rekordbox before applying."
            )
        if parent_id != str(category.ID):
            next_seq = next_my_tag_seq(database, str(category.ID))
            existing.ParentID = str(category.ID)
            existing.Seq = next_seq
        existing.Attribute = 0
        return existing
    return create_my_tag(database, tables, name, parent_id=str(category.ID))


def find_my_tag_category(database: Any, name: str) -> Any:
    category = None
    normalized_name = name.strip().casefold()
    for tag in database.get_my_tag():
        if is_rekordbox_row_deleted(tag):
            continue
        if int(getattr(tag, "Attribute", 0) or 0) != 1:
            continue
        if str(getattr(tag, "Name", "") or "").strip().casefold() == normalized_name:
            category = tag
            break
    if category is None:
        raise RuntimeError(f'Rekordbox MyTag category "{name}" was not found.')
    return category


def find_active_my_tag(database: Any, name: str) -> Any | None:
    normalized_name = name.strip().casefold()
    for tag in database.get_my_tag():
        if is_rekordbox_row_deleted(tag):
            continue
        if str(getattr(tag, "Name", "") or "").strip().casefold() == normalized_name:
            return tag
    return None


def create_my_tag(database: Any, tables: Any, name: str, *, parent_id: str) -> Any:
    from uuid import uuid4

    tag = tables.DjmdMyTag.create(
        ID=generated_rekordbox_id(database, tables.DjmdMyTag),
        Seq=next_my_tag_seq(database, parent_id),
        Name=name,
        Attribute=0,
        ParentID=parent_id,
        UUID=str(uuid4()),
        usn=0,
        rb_local_usn=0,
    )
    database.add(tag)
    database.flush()
    return tag


def next_my_tag_seq(database: Any, parent_id: str) -> int:
    siblings = [
        tag
        for tag in database.get_my_tag()
        if not is_rekordbox_row_deleted(tag)
        and str(getattr(tag, "ParentID", "") or "") == str(parent_id)
    ]
    return max([int(getattr(tag, "Seq", 0) or 0) for tag in siblings] or [0]) + 1


def ensure_event_smart_playlist(
    database: Any,
    *,
    name: str,
    event_tag: Any,
    operator: int,
    smart_list_class: Any,
) -> Any:
    folder = ensure_event_imports_playlist_folder(database)
    smart_list = smart_list_class(logical_operator=1, auto_update=1)
    smart_list.add_condition(
        "myTag",
        operator=operator,
        value_left=rekordbox_smartlist_reference_id(event_tag.ID),
    )

    playlist = find_active_playlist(database, name)
    if playlist is None:
        return database.create_smart_playlist(name, smart_list, parent=folder, seq=1)

    if getattr(playlist, "is_folder", False):
        raise RuntimeError(f'Playlist "{name}" already exists as a folder.')
    if not getattr(playlist, "is_smart_playlist", False):
        raise RuntimeError(f'Playlist "{name}" already exists and is not a smart playlist.')

    smart_list.playlist_id = str(playlist.ID)
    playlist.SmartList = smart_list.to_xml()
    move_playlist_to_folder_top(database, playlist, folder)
    return playlist


def ensure_event_imports_playlist_folder(database: Any) -> Any:
    existing = find_active_playlist(database, EVENT_IMPORTS_PLAYLIST_FOLDER_NAME)
    if existing is not None and not getattr(existing, "is_folder", False):
        raise RuntimeError(
            f'Playlist "{EVENT_IMPORTS_PLAYLIST_FOLDER_NAME}" already exists and is not a folder.'
        )
    if existing is None:
        return database.create_playlist_folder(EVENT_IMPORTS_PLAYLIST_FOLDER_NAME, seq=1)
    if str(getattr(existing, "ParentID", "") or "") == "root":
        move_playlist_to_sequence(database, existing, 1)
    return existing


def find_active_playlist(database: Any, name: str) -> Any | None:
    normalized_name = name.strip().casefold()
    for playlist in database.get_playlist():
        if is_rekordbox_row_deleted(playlist):
            continue
        if str(getattr(playlist, "Name", "") or "").strip().casefold() == normalized_name:
            return playlist
    return None


def move_playlist_to_folder_top(database: Any, playlist: Any, folder: Any) -> None:
    if str(getattr(playlist, "ParentID", "") or "") == str(folder.ID):
        move_playlist_to_sequence(database, playlist, 1)
        return
    database.move_playlist(playlist, parent=folder, seq=1)


def move_playlist_to_sequence(database: Any, playlist: Any, seq: int) -> None:
    try:
        current_seq = int(getattr(playlist, "Seq", 0) or 0)
    except (TypeError, ValueError):
        current_seq = 0
    if current_seq != seq:
        database.move_playlist(playlist, seq=seq)


def rekordbox_smartlist_reference_id(row_id: Any) -> str:
    value = int(row_id)
    if value > 2**31 - 1:
        value -= 2**32
    return str(value)


def ensure_content_tag(database: Any, tables: Any, content: Any, tag: Any) -> None:
    from uuid import uuid4

    existing = database.get_my_tag_songs(MyTagID=tag.ID, ContentID=content.ID)
    if hasattr(existing, "first"):
        existing_song_tag = existing.first()
        if existing_song_tag is not None:
            if is_rekordbox_row_deleted(existing_song_tag):
                reactivate_rekordbox_row(existing_song_tag)
            return
    elif existing:
        return
    song_tag = tables.DjmdSongMyTag.create(
        ID=generated_rekordbox_id(database, tables.DjmdSongMyTag),
        MyTagID=tag.ID,
        ContentID=content.ID,
        TrackNo=0,
        UUID=str(uuid4()),
        usn=0,
        rb_local_usn=0,
    )
    database.add(song_tag)
    database.flush()


def generated_rekordbox_id(database: Any, table: Any) -> str:
    return str(database.generate_unused_id(table))


def add_rekordbox_content(database: Any, tables: Any, path: str, **kwargs: Any) -> Any:
    from datetime import date
    from uuid import uuid4

    from pyrekordbox.db6.tables import FileType

    file_path = Path(path)
    path_string = str(file_path)
    existing = database.query(tables.DjmdContent).filter_by(FolderPath=path_string)
    if existing.count() > 0:
        raise ValueError(f"Track with path '{file_path}' already exists in database")

    file_type_name = file_path.suffix.lstrip(".").upper()
    try:
        file_type = getattr(FileType, file_type_name)
    except AttributeError as exc:
        raise ValueError(f"Invalid file type: {file_path.suffix}") from exc

    content_id = generated_rekordbox_id(database, tables.DjmdContent)
    content_link = database.get_menu_items(Name="TRACK").one()
    current_device = database.get_device().first()
    created_on = date.today()
    content = tables.DjmdContent.create(
        ID=content_id,
        UUID=str(uuid4()),
        ContentLink=content_link.rb_local_usn,
        DateCreated=created_on,
        DeviceID=str(current_device.ID),
        FileNameL=file_path.name,
        FileSize=file_path.stat().st_size,
        FileType=file_type.value,
        FolderPath=path_string,
        HotCueAutoLoad="on",
        MasterDBID=str(current_device.MasterDBID),
        MasterSongID=content_id,
        StockDate=created_on,
        rb_file_id=generated_rekordbox_id(database, tables.DjmdContent),
        **kwargs,
    )
    database.add(content)
    database.flush()
    return content


def is_rekordbox_row_deleted(row: Any) -> bool:
    return bool(getattr(row, "rb_local_deleted", 0))


def reactivate_rekordbox_row(row: Any) -> None:
    row.rb_local_deleted = 0
    row.rb_local_synced = 0
    if hasattr(row, "rb_data_status"):
        row.rb_data_status = 256
    if hasattr(row, "rb_local_data_status"):
        row.rb_local_data_status = 0


def mark_rekordbox_row_deleted(row: Any) -> None:
    row.rb_local_deleted = 1
    row.rb_local_synced = 0
    if hasattr(row, "rb_data_status"):
        row.rb_data_status = 258
    if hasattr(row, "rb_local_data_status"):
        row.rb_local_data_status = 0


def content_path_lookup(contents: Any) -> dict[str, Any]:
    lookup = {}
    for content in contents:
        for key in path_lookup_keys(getattr(content, "FolderPath", "")):
            lookup[key] = content
    return lookup


def find_content_by_path(lookup: dict[str, Any], path: Path) -> Any | None:
    for key in path_lookup_keys(path):
        content = lookup.get(key)
        if content is not None:
            return content
    return None


def path_lookup_keys(path: Path | str) -> list[str]:
    if not path:
        return []
    path_object = Path(path).expanduser()
    keys = [str(path_object)]
    try:
        keys.append(str(path_object.resolve()))
    except OSError:
        pass
    return list(dict.fromkeys(keys))


def build_event_delete_plan(
    database: Any,
    *,
    event_tag_name: str,
    protected_roots: list[Path],
) -> dict[str, Any]:
    tags = [
        tag
        for tag in database.get_my_tag()
        if not is_rekordbox_row_deleted(tag)
    ]
    tags_by_id = {str(tag.ID): tag for tag in tags}
    event_tag_ids = {
        str(tag.ID)
        for tag in tags
        if str(getattr(tag, "Name", "") or "") == event_tag_name
    }
    if not event_tag_ids:
        return {
            "event_tag_rows": [],
            "delete_contents": [],
            "protected_contents": [],
            "warnings": [f'Event MyTag "{event_tag_name}" was not found in Rekordbox.'],
        }

    contents_by_id = {
        str(content.ID): content
        for content in database.get_content()
        if not is_rekordbox_row_deleted(content)
    }
    tag_rows = [
        row
        for row in database.get_my_tag_songs()
        if not is_rekordbox_row_deleted(row)
    ]
    tag_rows_by_content: dict[str, list[Any]] = {}
    for row in tag_rows:
        tag_rows_by_content.setdefault(str(row.ContentID), []).append(row)

    event_content_ids = {
        str(row.ContentID)
        for row in tag_rows
        if str(row.MyTagID) in event_tag_ids
    }
    delete_contents = []
    protected_contents = []
    event_tag_rows = []
    for content_id in sorted(event_content_ids):
        content = contents_by_id.get(content_id)
        if content is None:
            continue
        rows = tag_rows_by_content.get(content_id, [])
        event_rows = [row for row in rows if str(row.MyTagID) in event_tag_ids]
        event_tag_rows.extend(event_rows)
        tag_names = {
            tag_name_for_my_tag_row(row, tags_by_id)
            for row in rows
        }
        other_tags = {
            tag_name
            for tag_name in tag_names
            if tag_name and tag_name != event_tag_name
        }
        if other_tags or path_is_under_roots(
            getattr(content, "FolderPath", "") or "",
            protected_roots,
        ):
            protected_contents.append(content)
        else:
            delete_contents.append(content)

    return {
        "event_tag_rows": event_tag_rows,
        "delete_contents": delete_contents,
        "protected_contents": protected_contents,
        "warnings": [],
    }


def event_delete_preview_from_plan(
    review: EventReview,
    plan: dict[str, Any],
    *,
    local_only: bool = False,
) -> EventDeletePreview:
    delete_contents = plan["delete_contents"]
    protected_contents = plan["protected_contents"]
    return EventDeletePreview(
        eventId=review.id,
        eventName=review.event_name,
        defaultTag=review.default_tag,
        localOnly=local_only,
        tracksWithEventTag=len(delete_contents) + len(protected_contents),
        willDeleteFromRekordbox=0 if local_only else len(delete_contents),
        willRemoveEventTag=0 if local_only else len(plan["event_tag_rows"]),
        protectedTracks=len(protected_contents),
        deletedSamples=[content_title(content) for content in delete_contents[:5]],
        protectedSamples=[content_title(content) for content in protected_contents[:5]],
        warnings=plan["warnings"],
    )


def tag_name_for_my_tag_row(row: Any, tags_by_id: dict[str, Any]) -> str:
    tag = tags_by_id.get(str(row.MyTagID))
    if tag is not None:
        return str(getattr(tag, "Name", "") or "")
    return str(getattr(row, "MyTagName", "") or "")


def content_title(content: Any) -> str:
    return str(getattr(content, "Title", "") or getattr(content, "FolderPath", "") or "")


def path_is_under_roots(path: str, roots: list[Path]) -> bool:
    if not path:
        return False
    try:
        resolved_path = Path(path).expanduser().resolve()
    except OSError:
        resolved_path = Path(path).expanduser()
    for root in roots:
        try:
            resolved_root = root.expanduser().resolve()
        except OSError:
            resolved_root = root.expanduser()
        if resolved_path == resolved_root or resolved_root in resolved_path.parents:
            return True
    return False


def playlist_exists(database: Any, name: str) -> bool:
    try:
        playlist = database.get_playlist(Name=name)
        return bool(playlist.first() if hasattr(playlist, "first") else list(playlist))
    except Exception:
        return False


def move_to_permanent(source: Path, permanent_root: Path) -> Path:
    permanent_root.mkdir(parents=True, exist_ok=True)
    target = permanent_root / source.name
    if target.exists() and target.resolve() != source.resolve():
        stem = source.stem
        suffix = source.suffix
        counter = 2
        while target.exists():
            target = permanent_root / f"{stem}-{counter}{suffix}"
            counter += 1
    if source.resolve() != target.resolve():
        shutil.move(str(source), str(target))
    return target
