from pathlib import Path
from types import SimpleNamespace

from app.rekordbox import (
    CollectionPath,
    add_rekordbox_content,
    content_path_lookup,
    ensure_event_my_tag,
    ensure_event_smart_playlist,
    find_content_by_path,
    generated_rekordbox_id,
    is_rekordbox_row_deleted,
    mark_rekordbox_row_deleted,
    path_is_under_roots,
    reactivate_rekordbox_row,
    rekordbox_smartlist_reference_id,
    resolve_volume_path,
    to_volume_relative,
)


STORAGE_ROOT = "/Users/x/Library/CloudStorage/Dropbox/Jockey Tricolore/Musique"


def test_to_volume_relative_under_root() -> None:
    full = STORAGE_ROOT + "/rekordbox/Collection/ABBA - Dancing Queen.mp3"
    assert to_volume_relative(full, STORAGE_ROOT) == "/Musique/rekordbox/Collection/ABBA - Dancing Queen.mp3"


def test_to_volume_relative_leaves_outside_paths() -> None:
    outside = "/Users/x/Music/foo.mp3"
    assert to_volume_relative(outside, STORAGE_ROOT) == outside


def test_resolve_volume_path_roundtrip() -> None:
    full = STORAGE_ROOT + "/rekordbox/Collection/x.mp3"
    rel = to_volume_relative(full, STORAGE_ROOT)
    assert rel == "/Musique/rekordbox/Collection/x.mp3"
    assert resolve_volume_path(rel, STORAGE_ROOT) == full


def test_resolve_volume_path_leaves_full_paths() -> None:
    full = STORAGE_ROOT + "/_rekordbox_sync/permanent/y.mp3"
    assert resolve_volume_path(full, STORAGE_ROOT) == full
    assert resolve_volume_path("/Users/x/Music/z.mp3", STORAGE_ROOT) == "/Users/x/Music/z.mp3"


def test_remove_event_directory_deletes_under_events_root(tmp_path: Path) -> None:
    from app.rekordbox import RekordboxAdapter

    adapter = RekordboxAdapter(database_dir=tmp_path / "db", storage_root=tmp_path / "store")
    event_dir = tmp_path / "store" / "_rekordbox_sync" / "events" / "my-event"
    (event_dir / "audio").mkdir(parents=True)
    (event_dir / "audio" / "x.mp3").write_bytes(b"a")

    assert adapter.remove_event_directory(str(event_dir)) is True
    assert not event_dir.exists()


def test_remove_event_directory_refuses_paths_outside_events_root(tmp_path: Path) -> None:
    from app.rekordbox import RekordboxAdapter

    adapter = RekordboxAdapter(database_dir=tmp_path / "db", storage_root=tmp_path / "store")
    # Collection is NOT under the events root -> must never be deleted.
    outside = tmp_path / "store" / "rekordbox" / "Collection"
    outside.mkdir(parents=True)
    (outside / "keep.mp3").write_bytes(b"a")

    assert adapter.remove_event_directory(str(outside)) is False
    assert (outside / "keep.mp3").exists()
    # The events root itself must not be deletable either.
    events_root = tmp_path / "store" / "_rekordbox_sync" / "events"
    events_root.mkdir(parents=True)
    assert adapter.remove_event_directory(str(events_root)) is False
    assert events_root.exists()


def test_backup_list_and_restore_roundtrip(tmp_path: Path, monkeypatch) -> None:
    import app.rekordbox.adapter as adapter_module
    from app.rekordbox import RekordboxAdapter

    # The mutation guard depends on whether Rekordbox is running on the host;
    # stub it so the test is deterministic.
    monkeypatch.setattr(adapter_module, "assert_rekordbox_can_mutate", lambda: None)

    adapter = RekordboxAdapter(database_dir=tmp_path / "db", storage_root=tmp_path / "store")
    adapter.database_file.parent.mkdir(parents=True, exist_ok=True)
    adapter.database_file.write_bytes(b"ORIGINAL")

    backup = adapter.backup_database()
    assert (backup / "master.db").read_bytes() == b"ORIGINAL"

    backups = adapter.list_backups()
    assert len(backups) == 1
    assert backups[0]["name"] == backup.name
    assert backups[0]["fileCount"] >= 1

    # Mutate the live DB, then restore the backup over it.
    adapter.database_file.write_bytes(b"CORRUPTED")
    result = adapter.restore_backup(backup.name)

    assert result["restored"] == backup.name
    assert adapter.database_file.read_bytes() == b"ORIGINAL"
    # Restore snapshots the current DB first, so we now have two backups.
    assert len(adapter.list_backups()) == 2


def test_restore_backup_rejects_path_traversal(tmp_path: Path) -> None:
    import pytest

    from app.rekordbox import RekordboxAdapter

    adapter = RekordboxAdapter(database_dir=tmp_path / "db", storage_root=tmp_path / "store")
    with pytest.raises(ValueError):
        adapter.restore_backup("../../etc")
    with pytest.raises(FileNotFoundError):
        adapter.restore_backup("rekordbox-db-does-not-exist")


def test_content_path_lookup_matches_resolved_paths(tmp_path: Path) -> None:
    track_path = tmp_path / "Track.mp3"
    track_path.write_bytes(b"audio")
    content = SimpleNamespace(FolderPath=str(track_path))

    lookup = content_path_lookup([content])

    assert find_content_by_path(lookup, track_path) is content
    assert find_content_by_path(lookup, tmp_path / "." / "Track.mp3") is content


def test_collection_path_equates_volume_relative_and_absolute() -> None:
    absolute = STORAGE_ROOT + "/rekordbox/Collection/x.mp3"
    volume_relative = "/Musique/rekordbox/Collection/x.mp3"
    a = CollectionPath.of(absolute, STORAGE_ROOT)
    b = CollectionPath.of(volume_relative, STORAGE_ROOT)
    # Both forms resolve to the same absolute path and are equal / hash-equal.
    assert a.absolute == b.absolute == absolute
    assert a.volume_relative == b.volume_relative == volume_relative
    assert a == b
    assert len({a, b}) == 1
    # lookup_keys covers both representations.
    assert absolute in a.lookup_keys()
    assert volume_relative in a.lookup_keys()


def test_content_path_lookup_dedups_volume_relative_against_absolute() -> None:
    # Rekordbox stores FolderPath volume-relative; the app downloads to the
    # absolute path under storage_root. Both must dedup to the same content.
    absolute = STORAGE_ROOT + "/rekordbox/Collection/KourzaK - On est Breton.mp3"
    volume_relative = "/Musique/rekordbox/Collection/KourzaK - On est Breton.mp3"
    content = SimpleNamespace(FolderPath=volume_relative)

    lookup = content_path_lookup([content], STORAGE_ROOT)

    # A staging absolute path resolves to the volume-relative content.
    assert find_content_by_path(lookup, Path(absolute), STORAGE_ROOT) is content
    # And the reverse direction (content stored absolute, queried relative).
    content_abs = SimpleNamespace(FolderPath=absolute)
    lookup_abs = content_path_lookup([content_abs], STORAGE_ROOT)
    assert find_content_by_path(lookup_abs, Path(volume_relative), STORAGE_ROOT) is content_abs


def test_reactivate_rekordbox_row_clears_deleted_flags() -> None:
    row = SimpleNamespace(
        rb_local_deleted=1,
        rb_local_synced=1,
        rb_data_status=258,
        rb_local_data_status=2,
    )

    reactivate_rekordbox_row(row)

    assert not is_rekordbox_row_deleted(row)
    assert row.rb_local_synced == 0
    assert row.rb_data_status == 256
    assert row.rb_local_data_status == 0


def test_mark_rekordbox_row_deleted_sets_soft_delete_flags() -> None:
    row = SimpleNamespace(
        rb_local_deleted=0,
        rb_local_synced=1,
        rb_data_status=256,
        rb_local_data_status=0,
    )

    mark_rekordbox_row_deleted(row)

    assert is_rekordbox_row_deleted(row)
    assert row.rb_local_synced == 0
    assert row.rb_data_status == 258
    assert row.rb_local_data_status == 0


def test_path_is_under_roots_protects_permanent_storage(tmp_path: Path) -> None:
    permanent_root = tmp_path / "permanent"
    track_path = permanent_root / "Artist - Track.mp3"

    assert path_is_under_roots(str(track_path), [permanent_root])
    assert not path_is_under_roots(str(tmp_path / "events" / "Track.mp3"), [permanent_root])


def test_smartlist_reference_id_uses_signed_value_for_large_rekordbox_ids() -> None:
    assert rekordbox_smartlist_reference_id("664110567") == "664110567"
    assert rekordbox_smartlist_reference_id("2662450573") == "-1632516723"


def test_generated_rekordbox_id_coerces_pyrekordbox_int_ids_to_strings() -> None:
    database = SimpleNamespace(generate_unused_id=lambda _table: 123456)

    assert generated_rekordbox_id(database, object()) == "123456"


def test_add_rekordbox_content_uses_string_ids_for_varchar_primary_keys(tmp_path: Path) -> None:
    track_path = tmp_path / "Track.mp3"
    track_path.write_bytes(b"audio")
    database = FakeRekordboxDatabase()

    content = add_rekordbox_content(
        database,
        FakeTables,
        str(track_path),
        Title="Track",
    )

    assert content.ID == "1000"
    assert content.MasterSongID == "1000"
    assert content.rb_file_id == "1000"
    assert content.DeviceID == "device-1"
    assert content.MasterDBID == "master-1"
    assert database.added_rows == [content]
    assert database.flushed


def test_ensure_event_my_tag_moves_orphan_tag_to_situation_category() -> None:
    category = SimpleNamespace(
        ID="3",
        Name="Situation",
        Attribute=1,
        ParentID="root",
        Seq=3,
        rb_local_deleted=0,
    )
    orphan = SimpleNamespace(
        ID="153200749",
        Name="Client Event",
        Attribute=0,
        ParentID="0",
        Seq=24,
        rb_local_deleted=0,
    )
    database = FakeRekordboxDatabase(my_tags=[category, orphan])

    tag = ensure_event_my_tag(database, FakeTables, "Client Event", "Situation")

    assert tag is orphan
    assert tag.ParentID == "3"
    assert tag.Attribute == 0
    assert tag.Seq == 1


def test_ensure_event_my_tag_rejects_existing_tag_in_another_visible_category() -> None:
    database = FakeRekordboxDatabase(
        my_tags=[
            SimpleNamespace(
                ID="3",
                Name="Situation",
                Attribute=1,
                ParentID="root",
                Seq=3,
                rb_local_deleted=0,
            ),
            SimpleNamespace(
                ID="664110567",
                Name="Techno",
                Attribute=0,
                ParentID="1",
                Seq=1,
                rb_local_deleted=0,
            ),
        ]
    )

    try:
        ensure_event_my_tag(database, FakeTables, "Techno", "Situation")
    except RuntimeError as exc:
        assert 'already exists outside "Situation"' in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for conflicting MyTag category.")


def test_ensure_event_smart_playlist_creates_event_folder_and_uses_tag_id() -> None:
    database = FakeRekordboxDatabase()
    event_tag = SimpleNamespace(ID="153200749")

    playlist = ensure_event_smart_playlist(
        database,
        name="Client Event - Smart",
        event_tag=event_tag,
        operator=8,
        smart_list_class=FakeSmartList,
    )

    folder = database.playlists[0]
    assert folder.Name == "Event Imports"
    assert folder.ParentID == "root"
    assert folder.Seq == 1
    assert playlist.ParentID == folder.ID
    assert playlist.Seq == 1
    assert playlist.SmartList == "playlist-2:153200749"


def test_ensure_event_smart_playlist_repairs_existing_playlist() -> None:
    folder = SimpleNamespace(
        ID="folder-1",
        Name="Event Imports",
        ParentID="root",
        Seq=4,
        is_folder=True,
        is_smart_playlist=False,
        rb_local_deleted=0,
    )
    playlist = SimpleNamespace(
        ID="playlist-1",
        Name="Client Event - Smart",
        ParentID="root",
        Seq=12,
        is_folder=False,
        is_smart_playlist=True,
        SmartList="broken",
        rb_local_deleted=0,
    )
    database = FakeRekordboxDatabase(playlists=[folder, playlist])
    event_tag = SimpleNamespace(ID="153200749")

    repaired = ensure_event_smart_playlist(
        database,
        name="Client Event - Smart",
        event_tag=event_tag,
        operator=8,
        smart_list_class=FakeSmartList,
    )

    assert repaired is playlist
    assert folder.Seq == 1
    assert playlist.ParentID == "folder-1"
    assert playlist.Seq == 1
    assert playlist.SmartList == "playlist-1:153200749"


class FakeTables:
    DjmdMyTag = type(
        "DjmdMyTag",
        (),
        {"create": staticmethod(lambda **kwargs: SimpleNamespace(**kwargs, rb_local_deleted=0))},
    )
    DjmdContent = type(
        "DjmdContent",
        (),
        {"create": staticmethod(lambda **kwargs: SimpleNamespace(**kwargs, rb_local_deleted=0))},
    )


class FakeRekordboxDatabase:
    def __init__(self, my_tags=None, playlists=None) -> None:
        self.my_tags = list(my_tags or [])
        self.playlists = list(playlists or [])
        self.added_rows = []
        self.flushed = False

    def get_my_tag(self):
        return self.my_tags

    def get_playlist(self):
        return self.playlists

    def generate_unused_id(self, _table, is_28_bit=True):
        return len(self.playlists) + len(self.my_tags) + 1000

    def add(self, row) -> None:
        self.added_rows.append(row)
        if hasattr(row, "ParentID") and hasattr(row, "Attribute"):
            self.my_tags.append(row)

    def flush(self) -> None:
        self.flushed = True

    def query(self, _table):
        return FakeQuery()

    def get_menu_items(self, Name: str):
        assert Name == "TRACK"
        return SimpleNamespace(one=lambda: SimpleNamespace(rb_local_usn=10))

    def get_device(self):
        return SimpleNamespace(first=lambda: SimpleNamespace(ID="device-1", MasterDBID="master-1"))

    def create_playlist_folder(self, name: str, seq: int):
        folder = SimpleNamespace(
            ID=f"folder-{len(self.playlists) + 1}",
            Name=name,
            ParentID="root",
            Seq=seq,
            is_folder=True,
            is_smart_playlist=False,
            rb_local_deleted=0,
        )
        self.playlists.append(folder)
        return folder

    def create_smart_playlist(self, name: str, smart_list, parent, seq: int):
        playlist = SimpleNamespace(
            ID=f"playlist-{len(self.playlists) + 1}",
            Name=name,
            ParentID=parent.ID,
            Seq=seq,
            is_folder=False,
            is_smart_playlist=True,
            rb_local_deleted=0,
        )
        smart_list.playlist_id = playlist.ID
        playlist.SmartList = smart_list.to_xml()
        self.playlists.append(playlist)
        return playlist

    def move_playlist(self, playlist, parent=None, seq=None) -> None:
        if parent is not None:
            playlist.ParentID = parent.ID
        if seq is not None:
            playlist.Seq = seq


class FakeQuery:
    def filter_by(self, **_kwargs):
        return self

    def count(self) -> int:
        return 0


class FakeSmartList:
    def __init__(self, logical_operator: int, auto_update: int) -> None:
        self.playlist_id = ""
        self.value_left = ""

    def add_condition(self, _prop: str, operator: int, value_left: str) -> None:
        assert operator == 8
        self.value_left = value_left

    def to_xml(self) -> str:
        return f"{self.playlist_id}:{self.value_left}"
