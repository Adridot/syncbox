from __future__ import annotations

from pathlib import Path
from typing import Any
from ..models import (
    EventDeletePreview,
    EventReview,
)
from .paths import (
    content_folder_path,
    path_is_under_roots,
)


"""Rekordbox-DB helper functions: MyTags, smart playlists, content rows,
artists, and the event-delete plan. Operate on a pyrekordbox database/tables
handle passed in by the adapter."""

EVENT_IMPORTS_PLAYLIST_FOLDER_NAME = "Event Imports"


EVENT_MY_TAG_CATEGORY_NAME = "Situation"


def content_length_ms(content: Any) -> int | None:
    length = getattr(content, "Length", None)
    if length in (None, ""):
        return None
    try:
        return int(float(length) * 1000)
    except (TypeError, ValueError):
        return None


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


def _find_artist_by_name(database: Any, name: str) -> Any | None:
    from pyrekordbox.db6 import tables

    # Exact match first.
    for row in database.query(tables.DjmdArtist).filter(tables.DjmdArtist.Name == name):
        if not is_rekordbox_row_deleted(row):
            return row
    # Fallback: case/whitespace-insensitive scan. Rekordbox's add_artist refuses
    # duplicates by a normalized key, so existing artists may differ only by
    # trailing spaces or casing (e.g. "Alan Walker   ").
    target = name.strip().casefold()
    for row in database.query(tables.DjmdArtist):
        if is_rekordbox_row_deleted(row):
            continue
        if str(getattr(row, "Name", "") or "").strip().casefold() == target:
            return row
    return None


def ensure_artist(database: Any, name: str) -> Any | None:
    """Return an existing (active) DjmdArtist by exact name, creating if needed.

    The artist row is created with a **string** ID via ``generated_rekordbox_id``
    to stay uniform with every existing ``DjmdArtist.ID`` (all stored as strings).
    pyrekordbox's own ``add_artist`` assigns an *int* ID, which makes SQLAlchemy
    crash on flush ("'<' not supported between instances of 'int' and 'str'")
    whenever string-keyed rows are pending in the same session — exactly what
    happens the moment an import touches an artist that isn't already in the
    collection. Creating the row ourselves keeps the primary-key types uniform.
    """
    from uuid import uuid4

    from pyrekordbox.db6 import tables

    name = (name or "").strip()
    if not name:
        return None
    existing = _find_artist_by_name(database, name)
    if existing is not None:
        return existing
    # add_artist's duplicate check counts soft-deleted rows too, so a
    # rb_local_deleted artist with this exact name would block creation.
    # Detect it up front, reactivate, and reuse it.
    duplicate = database.query(tables.DjmdArtist).filter_by(Name=name).first()
    if duplicate is not None:
        if is_rekordbox_row_deleted(duplicate):
            reactivate_rekordbox_row(duplicate)
        return duplicate
    artist = tables.DjmdArtist.create(
        ID=generated_rekordbox_id(database, tables.DjmdArtist),
        Name=name,
        SearchStr=None,
        UUID=str(uuid4()),
    )
    database.add(artist)
    database.flush()
    return artist


def add_rekordbox_content(
    database: Any,
    tables: Any,
    path: str,
    *,
    artist: str = "",
    storage_root: Path | str | None = None,
    **kwargs: Any,
) -> Any:
    from datetime import date
    from uuid import uuid4

    from pyrekordbox.db6.tables import FileType

    file_path = Path(path)  # real, full path on disk
    # Volume-relative only inside the managed library, absolute elsewhere — else
    # Rekordbox shows "file could not be found". See content_folder_path.
    path_string = content_folder_path(file_path, storage_root)
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
    artist_row = ensure_artist(database, artist)
    if artist_row is not None:
        content.ArtistID = artist_row.ID
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
    event_mytag_rows = [tag for tag in tags if str(tag.ID) in event_tag_ids]

    if not event_tag_ids:
        return {
            "event_tag_rows": [],
            "event_mytag_rows": [],
            "event_playlist_rows": [],
            "delete_contents": [],
            "protected_contents": [],
            "warnings": [f'Event MyTag "{event_tag_name}" was not found in Rekordbox.'],
        }

    # The event playlist is named after the event; also match the legacy
    # "<name> - Smart" so events applied before the rename are still cleaned up.
    event_playlist_names = {event_tag_name, f"{event_tag_name} - Smart"}
    event_playlist_rows = [
        playlist
        for playlist in database.get_playlist()
        if str(getattr(playlist, "Name", "") or "") in event_playlist_names
        and not is_rekordbox_row_deleted(playlist)
    ]

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
        "event_mytag_rows": event_mytag_rows,
        "event_playlist_rows": event_playlist_rows,
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


def playlist_exists(database: Any, name: str) -> bool:
    try:
        playlist = database.get_playlist(Name=name)
        return bool(playlist.first() if hasattr(playlist, "first") else list(playlist))
    except Exception:
        return False
