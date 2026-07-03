"""Rekordbox write helpers (SPEC-UNIFIED 5.7, SPEC-01 1.1/1.6/1.7,
poc/05 verdict).

Every function here operates on the pyrekordbox handle YIELDED BY
safety.mutate() - there is no other write path (3.1: no escape hatch).
Load-bearing mechanics owned by Syncbox, not pyrekordbox:
- signed32() is CONDITIONAL (x - 2^32 only when x >= 2^31): pyrekordbox
  0.4.4 SmartList.to_xml()/parse() shift unconditionally (#110-family
  quirk, measured in poc/05) and would corrupt NODE Ids < 2^31;
- new rows always use STRING IDs (mixed int+string PKs are a latent
  identity hazard: SQLite TEXT affinity silently coerces, poc/05 caveat 2);
- soft-delete integer tuples come from safety.statuses, byte-identical;
- an existing smart playlist / MyTag is REPAIRED, never duplicated (11.2);
- a soft-deleted artist found by name is self-healed (reactivated, 1.6).
"""

import uuid
from pathlib import Path

from pyrekordbox.db6 import Rekordbox6Database, tables
from pyrekordbox.db6.smartlist import LogicalOperator, Operator, SmartList

from syncbox.safety.paths import stored_form
from syncbox.safety.statuses import reactivate_values, soft_delete_values

NEW_ROW_STATUS = {
    "rb_data_status": 256,
    "rb_local_data_status": 0,
    "rb_local_deleted": 0,
    "rb_local_synced": 0,
}


def open_rekordbox(db_path) -> Rekordbox6Database:
    """The open_db callable to inject into safety.mutate()."""
    return Rekordbox6Database(path=db_path, unlock=True)


def signed32(value: int) -> int:
    """SPEC-01 1.7: IDs >= 2^31 are written as signed 32-bit in SmartList
    payloads; smaller IDs STAY POSITIVE (Syncbox owns this - pyrekordbox's
    unconditional shift is the residual #110 quirk)."""
    return value - 2**32 if value >= 2**31 else value


def _new_id(db, table) -> str:
    return str(db.generate_unused_id(table))


def _apply(row, values: dict) -> None:
    for column, value in values.items():
        setattr(row, column, value)


# --- artists -------------------------------------------------------------------


def find_or_create_artist(db, name: str):
    """Active artist by exact name; self-heals a soft-deleted one (1.6)."""
    rows = db.query(tables.DjmdArtist).filter_by(Name=name).all()
    for row in rows:
        if not int(row.rb_local_deleted or 0):
            return row
    if rows:  # soft-deleted artist with that name: reactivate instead of dup
        row = rows[0]
        _apply(row, reactivate_values())
        return row
    row = tables.DjmdArtist.create(
        ID=_new_id(db, tables.DjmdArtist),
        Name=name,
        SearchStr=None,
        UUID=str(uuid.uuid4()),
        **NEW_ROW_STATUS,
    )
    db.add(row)
    db.flush()
    return row


# --- MyTags ----------------------------------------------------------------------


def find_or_create_mytag_category(db, name: str):
    """Top-level MyTag category (Attribute=1, ParentID='root')."""
    row = (
        db.query(tables.DjmdMyTag)
        .filter_by(Name=name, ParentID="root")
        .one_or_none()
    )
    if row is not None:
        return row
    seq = max(
        (t.Seq or 0 for t in db.query(tables.DjmdMyTag).filter_by(ParentID="root")),
        default=0,
    )
    row = tables.DjmdMyTag.create(
        ID=_new_id(db, tables.DjmdMyTag),
        Seq=seq + 1,
        Name=name,
        Attribute=1,
        ParentID="root",
        UUID=str(uuid.uuid4()),
        **NEW_ROW_STATUS,
    )
    db.add(row)
    db.flush()
    return row


def find_or_create_mytag(db, name: str, category_name: str):
    category = find_or_create_mytag_category(db, category_name)
    existing = (
        db.query(tables.DjmdMyTag)
        .filter_by(Name=name, ParentID=category.ID)
        .one_or_none()
    )
    if existing is not None:
        if int(existing.rb_local_deleted or 0):
            _apply(existing, reactivate_values())
        return existing
    seq = max(
        (t.Seq or 0 for t in db.query(tables.DjmdMyTag).filter_by(ParentID=category.ID)),
        default=0,
    )
    row = tables.DjmdMyTag.create(
        ID=_new_id(db, tables.DjmdMyTag),
        Seq=seq + 1,
        Name=name,
        Attribute=0,
        ParentID=category.ID,
        UUID=str(uuid.uuid4()),
        **NEW_ROW_STATUS,
    )
    db.add(row)
    db.flush()
    return row


def tag_content(db, content_id: str, tag_id: str) -> None:
    """Idempotent MyTag link; reactivates a soft-deleted link row."""
    link = (
        db.query(tables.DjmdSongMyTag)
        .filter_by(ContentID=str(content_id), MyTagID=str(tag_id))
        .one_or_none()
    )
    if link is not None:
        if int(link.rb_local_deleted or 0):
            _apply(link, reactivate_values())
        return
    row = tables.DjmdSongMyTag.create(
        ID=_new_id(db, tables.DjmdSongMyTag),
        MyTagID=str(tag_id),
        ContentID=str(content_id),
        TrackNo=1,
        UUID=str(uuid.uuid4()),
        **NEW_ROW_STATUS,
    )
    db.add(row)
    db.flush()


def untag_content(db, content_id: str, tag_id: str) -> None:
    """Delta remove (D16): soft-deletes the link row - reversible (D21)."""
    link = (
        db.query(tables.DjmdSongMyTag)
        .filter_by(ContentID=str(content_id), MyTagID=str(tag_id))
        .one_or_none()
    )
    if link is not None and not int(link.rb_local_deleted or 0):
        _apply(link, soft_delete_values())


def apply_tag_delta(db, content_id: str, add_tag_ids=(), remove_tag_ids=()) -> None:
    """D16: bulk tag edits are ADD/REMOVE deltas, never a union overwrite."""
    for tag_id in add_tag_ids:
        tag_content(db, content_id, tag_id)
    for tag_id in remove_tag_ids:
        untag_content(db, content_id, tag_id)


# --- smart playlists --------------------------------------------------------------


def smartlist_payload(playlist_id: str, tag_id: str) -> str:
    """SmartList XML: operator 8 (contains) on the MyTag, with the
    spec-conformant CONDITIONAL signed-32 NODE Id and ValueLeft (poc/05:
    byte-shape-identical to rows Rekordbox 7 itself writes)."""
    sl = SmartList(logical_operator=LogicalOperator.ALL, auto_update=0)
    sl.playlist_id = str(playlist_id)
    sl.add_condition("myTag", Operator.CONTAINS, str(signed32(int(tag_id))))
    payload = sl.to_xml()
    # pyrekordbox to_xml() shifts the NODE Id unconditionally; rewrite it
    # with the conditional conversion (Syncbox owns this - #110 quirk).
    import re as _re

    return _re.sub(
        r'(<NODE [^>]*Id=")-?\d+(")',
        rf"\g<1>{signed32(int(playlist_id))}\g<2>",
        payload,
        count=1,
    )


def ensure_playlist_folder(db, name: str, parent_id: str = "root"):
    """Playlist FOLDER (Attribute=1), e.g. 'Event Imports' (5.7)."""
    row = (
        db.query(tables.DjmdPlaylist)
        .filter_by(Name=name, ParentID=parent_id, Attribute=1)
        .one_or_none()
    )
    if row is not None:
        return row
    from datetime import datetime

    now = datetime.now()
    row = tables.DjmdPlaylist.create(
        ID=_new_id(db, tables.DjmdPlaylist),
        Seq=db.get_playlist(ParentID=parent_id).count() + 1,
        Name=name,
        Attribute=1,
        ParentID=parent_id,
        SmartList=None,
        UUID=str(uuid.uuid4()),
        created_at=now,
        updated_at=now,
        **NEW_ROW_STATUS,
    )
    db.add(row)
    if db.playlist_xml is not None:
        db.playlist_xml.add(row.ID, parent_id, 1, now)
    db.flush()
    return row


def create_or_repair_smart_playlist(db, name: str, parent_id: str, tag_id: str):
    """Create the event smart playlist, or REPAIR the existing one in place
    (payload rewritten, never duplicated - 5.7/11.2)."""
    existing = (
        db.query(tables.DjmdPlaylist)
        .filter_by(Name=name, ParentID=parent_id)
        .one_or_none()
    )
    if existing is not None:
        if int(existing.rb_local_deleted or 0):
            _apply(existing, reactivate_values())
        existing.SmartList = smartlist_payload(existing.ID, tag_id)
        existing.Attribute = 4
        db.flush()
        return existing
    from datetime import datetime

    now = datetime.now()
    playlist_id = _new_id(db, tables.DjmdPlaylist)
    row = tables.DjmdPlaylist.create(
        ID=playlist_id,
        Seq=db.get_playlist(ParentID=parent_id).count() + 1,
        Name=name,
        Attribute=4,
        ParentID=parent_id,
        SmartList=smartlist_payload(playlist_id, tag_id),
        UUID=str(uuid.uuid4()),
        created_at=now,
        updated_at=now,
        **NEW_ROW_STATUS,
    )
    db.add(row)
    if db.playlist_xml is not None:
        db.playlist_xml.add(playlist_id, parent_id, 4, now)
    db.flush()
    return row


# --- content -----------------------------------------------------------------------

_FILE_TYPE_BY_EXT = {
    ".mp3": int(tables.FileType.MP3),
    ".m4a": int(tables.FileType.M4A),
    ".flac": int(tables.FileType.FLAC),
    ".wav": int(tables.FileType.WAV),
    ".aiff": int(tables.FileType.AIFF),
    ".aif": int(tables.FileType.AIFF),
}


def add_content(db, staging_path, metadata: dict, *, storage_root):
    """New content row for a staged event file (SPEC-01 1.6, the poc/05
    phase-4 pattern verified on a real RB 7.x master.db).

    Load-bearing: STRING primary key with ID = MasterSongID = rb_file_id;
    FolderPath written in stored form (safety.paths.stored_form - staging
    paths are outside <storage_root>/rekordbox/ so they stay absolute);
    the artist goes through find-or-create including the soft-deleted
    self-heal. ``metadata``: {title, artist, duration_ms?, isrc?}.
    """
    from datetime import datetime

    path = Path(staging_path)
    content_id = _new_id(db, tables.DjmdContent)
    artist = find_or_create_artist(db, metadata.get("artist") or "Unknown Artist")
    device = db.get_device().first()
    now = datetime.now()
    duration_ms = metadata.get("duration_ms") or 0
    try:
        file_size = path.stat().st_size
    except OSError:
        file_size = 0
    row = tables.DjmdContent.create(
        ID=content_id,
        MasterSongID=content_id,
        rb_file_id=content_id,  # SPEC-01 1.6: ID = MasterSongID = rb_file_id
        UUID=str(uuid.uuid4()),
        Title=metadata.get("title"),
        ArtistID=artist.ID,
        ISRC=metadata.get("isrc"),
        Length=duration_ms // 1000 if duration_ms else None,
        FolderPath=stored_form(path, storage_root),
        FileNameL=path.name,
        # ponytail: unrecognized extensions land as FileType 0 (unknown) -
        # Rekordbox re-derives the real type at import/analysis. Extend the
        # map only when a real event stages another container.
        FileType=_FILE_TYPE_BY_EXT.get(path.suffix.lower(), 0),
        FileSize=file_size,
        DeviceID=device.ID if device else None,
        MasterDBID=device.MasterDBID if device else None,
        StockDate=now.strftime("%Y-%m-%d"),
        DateCreated=now.strftime("%Y-%m-%d"),
        HotCueAutoLoad="on",
        **NEW_ROW_STATUS,
    )
    db.add(row)
    db.flush()
    return row


def find_active_content_by_path(db, stored_path: str):
    """Active content row whose FolderPath equals the stored (3.2) form, or
    None. The event-apply retry guard: after a crash in the window between
    the durable master.db commit and the app-DB update, the event row is
    still 'ready' and re-running add_content would create a DUPLICATE
    content row for the same staged file - the retry must reuse this one."""
    rows = db.query(tables.DjmdContent).filter_by(FolderPath=str(stored_path)).all()
    for row in rows:
        if not int(row.rb_local_deleted or 0):
            return row
    return None


def soft_delete_content(db, content_id: str) -> None:
    row = db.query(tables.DjmdContent).filter_by(ID=str(content_id)).one()
    _apply(row, soft_delete_values())
    db.flush()


def reactivate_content(db, content_id: str) -> None:
    row = db.query(tables.DjmdContent).filter_by(ID=str(content_id)).one()
    _apply(row, reactivate_values())
    db.flush()


def soft_delete_playlist(db, playlist_id: str) -> None:
    """Reversible playlist removal (event delete cleanup, SPEC-01 1.8)."""
    row = db.query(tables.DjmdPlaylist).filter_by(ID=str(playlist_id)).one()
    _apply(row, soft_delete_values())
    db.flush()


def soft_delete_mytag(db, tag_id: str) -> None:
    """Reversible MyTag removal (event delete cleanup, SPEC-01 1.8)."""
    row = db.query(tables.DjmdMyTag).filter_by(ID=str(tag_id)).one()
    _apply(row, soft_delete_values())
    db.flush()


def reassign_memberships(db, from_content_id: str, to_content_id: str) -> None:
    """Dedup keeper relink (SPEC-UNIFIED 5.4): move the loser's ACTIVE
    playlist and MyTag memberships onto the keeper, BEFORE the loser row is
    soft-deleted.

    Same discipline as tag_content/untag_content: never rewrite a link row's
    ContentID in place - the keeper gets an equivalent link (created with the
    byte-identical NEW_ROW_STATUS tuple, or a soft-deleted one reactivated)
    and the loser's link is soft-deleted. Idempotent: a loser with no active
    links (e.g. a consent-retry after the mutation already committed) is a
    no-op. Cues stay with the loser row - they describe its audio file.
    """
    from_id, to_id = str(from_content_id), str(to_content_id)
    for tag_link in db.query(tables.DjmdSongMyTag).filter_by(ContentID=from_id).all():
        if int(tag_link.rb_local_deleted or 0):
            continue
        tag_content(db, to_id, tag_link.MyTagID)
        _apply(tag_link, soft_delete_values())
    for song in db.query(tables.DjmdSongPlaylist).filter_by(ContentID=from_id).all():
        if int(song.rb_local_deleted or 0):
            continue
        existing = (
            db.query(tables.DjmdSongPlaylist)
            .filter_by(ContentID=to_id, PlaylistID=song.PlaylistID)
            .one_or_none()
        )
        if existing is None:
            track_no = max(
                (
                    int(row.TrackNo or 0)
                    for row in db.query(tables.DjmdSongPlaylist).filter_by(
                        PlaylistID=song.PlaylistID
                    )
                ),
                default=0,
            )
            db.add(
                tables.DjmdSongPlaylist.create(
                    ID=_new_id(db, tables.DjmdSongPlaylist),
                    PlaylistID=song.PlaylistID,
                    ContentID=to_id,
                    TrackNo=track_no + 1,
                    UUID=str(uuid.uuid4()),
                    **NEW_ROW_STATUS,
                )
            )
        elif int(existing.rb_local_deleted or 0):
            _apply(existing, reactivate_values())
        _apply(song, soft_delete_values())
    db.flush()


def relink_content_path(db, content_id: str, stored_path: str) -> None:
    """Manual relink writer (5.5): ONLY FolderPath changes. Cues, MyTag
    links and playlist memberships live in separate rows keyed by ContentID
    and are preserved by construction. ``stored_path`` must already be in
    the 3.2 stored form (safety.paths.stored_form) - this layer never
    re-derives it."""
    row = db.query(tables.DjmdContent).filter_by(ID=str(content_id)).one()
    row.FolderPath = stored_path
    db.flush()


def set_content_fields(db, content_id: str, changes: dict) -> None:
    """Smart Fixes writer: {'title': str, 'artist': str}. The artist change
    goes through find-or-create (artist rows are SHARED - editing the row
    in place would rename every track of that artist)."""
    row = db.query(tables.DjmdContent).filter_by(ID=str(content_id)).one()
    for field, value in changes.items():
        if field == "title":
            row.Title = value
        elif field == "artist":
            row.ArtistID = find_or_create_artist(db, value).ID
        else:
            raise ValueError(f"unsupported smart-fix field: {field}")
    db.flush()
