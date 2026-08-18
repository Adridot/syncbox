"""Safety coverage for the one-shot legacy metadata backfill."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from syncbox import legacy_metadata_backfill as backfill
from syncbox import rb_write


def _candidate(content_id, path, **overrides):
    row = {
        "ID": str(content_id),
        "Title": f"Track {content_id}",
        "FolderPath": str(path),
        "StockDate": "2026-05-29",
        "DateCreated": "2026-05-29",
        "AlbumID": None,
        "GenreID": None,
        "TrackNo": 0,
        "DiscNo": 0,
        "ReleaseDate": None,
        "ReleaseYear": 0,
        "rb_local_deleted": 0,
    }
    row.update(overrides)
    return row


def test_discovery_requires_exact_count_and_canonicalizes_legacy_paths(tmp_path):
    storage_root = tmp_path / "AuditedVolume"
    rows = [
        _candidate(index, storage_root / "rekordbox" / f"track-{index}.flac")
        for index in range(55)
    ]
    rows[0]["FolderPath"] = "/AuditedVolume/rekordbox/track-0.flac"

    found = backfill.discover_legacy_cohort(rows, storage_root)

    assert len(found) == 55
    assert found[0]["canonical_path"] == str(
        storage_root / "rekordbox" / "track-0.flac"
    )
    with pytest.raises(backfill.BackfillError, match="exactly 55"):
        backfill.discover_legacy_cohort(rows[:-1], storage_root)


@pytest.mark.parametrize("duplicate", ["content", "path"])
def test_discovery_rejects_duplicate_identities(tmp_path, duplicate):
    storage_root = tmp_path / "Music"
    rows = [
        _candidate(index, storage_root / "rekordbox" / f"track-{index}.flac")
        for index in range(55)
    ]
    if duplicate == "content":
        rows[1]["ID"] = rows[0]["ID"]
    else:
        rows[1]["FolderPath"] = rows[0]["FolderPath"]

    with pytest.raises(backfill.BackfillError, match="duplicate"):
        backfill.discover_legacy_cohort(rows, storage_root)


@pytest.fixture
def library(tmp_path):
    storage_root = tmp_path / "Music"
    audio_root = storage_root / "rekordbox" / "Legacy"
    audio_root.mkdir(parents=True)
    db_path = tmp_path / "master.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE djmdContent (
            ID TEXT PRIMARY KEY,
            Title TEXT,
            ArtistID TEXT,
            FolderPath TEXT,
            AnalysisDataPath TEXT,
            StockDate TEXT,
            DateCreated TEXT,
            AlbumID TEXT,
            GenreID TEXT,
            TrackNo INTEGER,
            DiscNo INTEGER,
            ReleaseDate TEXT,
            ReleaseYear INTEGER,
            ISRC TEXT,
            Commnt TEXT,
            rb_data_status INTEGER,
            rb_local_data_status INTEGER,
            rb_local_deleted INTEGER,
            rb_local_synced INTEGER,
            usn INTEGER,
            rb_local_usn INTEGER,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE djmdAlbum (ID TEXT PRIMARY KEY, Name TEXT, AlbumArtistID TEXT);
        CREATE TABLE djmdArtist (ID TEXT PRIMARY KEY, Name TEXT);
        CREATE TABLE djmdGenre (ID TEXT PRIMARY KEY, Name TEXT);
        CREATE TABLE djmdCue (ID TEXT PRIMARY KEY, ContentID TEXT, Comment TEXT);
        CREATE TABLE djmdSongPlaylist (
            ID TEXT PRIMARY KEY, ContentID TEXT, PlaylistID TEXT, TrackNo INTEGER
        );
        CREATE TABLE djmdSongMyTag (
            ID TEXT PRIMARY KEY, ContentID TEXT, MyTagID TEXT, TrackNo INTEGER
        );
        CREATE TABLE djmdSongHistory (
            ID TEXT PRIMARY KEY, ContentID TEXT, HistoryID TEXT, TrackNo INTEGER
        );
        """
    )
    paths = []
    for index in range(55):
        path = audio_root / f"track-{index}.flac"
        path.write_bytes(f"audio-{index}".encode())
        paths.append(path)
        analysis = "PIONEER/USBANLZ/000/ANLZ0000.DAT" if index == 0 else None
        conn.execute(
            """
            INSERT INTO djmdContent (
                ID, Title, ArtistID, FolderPath, AnalysisDataPath,
                StockDate, DateCreated, AlbumID, GenreID, TrackNo, DiscNo,
                ReleaseDate, ReleaseYear, ISRC, Commnt, rb_data_status,
                rb_local_data_status, rb_local_deleted, rb_local_synced,
                usn, rb_local_usn, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0, 0, NULL, 0,
                      ?, ?, 256, 0, 0, 0, 1, 1, ?, ?)
            """,
            (
                str(index),
                f"Track {index}",
                "artist",
                str(path),
                analysis,
                "2026-05-29",
                "2026-05-29",
                f"ISRC{index:08d}",
                f"comment-{index}",
                "2026-05-29",
                "2026-05-29",
            ),
        )
    conn.execute("INSERT INTO djmdCue VALUES ('cue-0', '0', 'keep')")
    conn.execute("INSERT INTO djmdSongPlaylist VALUES ('pl-0', '0', 'p', 1)")
    conn.execute("INSERT INTO djmdSongMyTag VALUES ('tag-0', '0', 't', 1)")
    conn.execute("INSERT INTO djmdSongHistory VALUES ('hist-0', '0', 'h', 1)")
    conn.commit()
    conn.close()

    anlz_root = tmp_path / "share" / "PIONEER" / "USBANLZ" / "000"
    anlz_root.mkdir(parents=True)
    (anlz_root / "ANLZ0000.DAT").write_bytes(b"dat")
    (anlz_root / "ANLZ0000.EXT").write_bytes(b"ext")

    def open_connection(path):
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True)

    def metadata(path):
        index = int(Path(path).stem.split("-")[-1])
        return {
            "album": "Audited Album",
            "album_artist": "Audited Album Artist",
            "genre": "House" if index < 53 else None,
            "track_number": index + 1,
            "disc_number": 1,
            "release_date": "2026-05-01",
            "release_year": 2026,
        }

    return SimpleNamespace(
        db_path=db_path,
        storage_root=storage_root,
        paths=paths,
        open_connection=open_connection,
        metadata=metadata,
    )


def _manifest(library):
    return backfill.build_manifest(
        library.db_path,
        library.storage_root,
        connection_factory=library.open_connection,
        metadata_reader=library.metadata,
    )


def test_manifest_is_complete_deterministic_and_round_trips_atomically(
    library, tmp_path
):
    first = _manifest(library)
    second = _manifest(library)

    assert first == second
    assert first["aggregate"] == {
        "track_count": 55,
        "proposed_writes": {
            "album": 55,
            "genre": 53,
            "track_number": 55,
            "disc_number": 55,
            "release_date": 55,
            "release_year": 55,
        },
        "total_proposed_writes": 328,
        "universal_fields_per_track": 5,
        "intentional_genre_blanks": 2,
    }
    first_track = first["tracks"][0]
    assert first_track["audio"]["sha256"]
    assert {item["path"] for item in first_track["anlz"]} == {
        str(library.db_path.parent / "share/PIONEER/USBANLZ/000/ANLZ0000.DAT"),
        str(library.db_path.parent / "share/PIONEER/USBANLZ/000/ANLZ0000.EXT"),
    }
    assert set(first_track["preservation"]) == {
        "content_non_target",
        "cues",
        "playlists",
        "mytags",
        "history",
    }
    target = tmp_path / "local" / "manifest.json"
    assert backfill.write_manifest(target, first) == target.resolve()
    assert backfill.load_manifest(target) == first
    assert not list(target.parent.glob(f".{target.name}.*"))


def test_preview_rejects_unavailable_file_without_replacing_existing_manifest(
    library, tmp_path
):
    target = tmp_path / "manifest.json"
    target.write_text("reviewed-old-value", encoding="utf-8")
    library.paths[0].unlink()

    with pytest.raises(backfill.BackfillError, match="unavailable"):
        backfill.build_manifest(
            library.db_path,
            library.storage_root,
            connection_factory=library.open_connection,
            metadata_reader=library.metadata,
        )
    assert target.read_text(encoding="utf-8") == "reviewed-old-value"


def test_preview_rejects_unexpected_genre_count(library):
    def missing_extra_genre(path):
        result = library.metadata(path)
        if Path(path).name == "track-52.flac":
            result["genre"] = None
        return result

    with pytest.raises(backfill.BackfillError, match="53 genre"):
        backfill.build_manifest(
            library.db_path,
            library.storage_root,
            connection_factory=library.open_connection,
            metadata_reader=missing_extra_genre,
        )


def test_manifest_tampering_and_audio_tag_drift_are_rejected(library, tmp_path):
    manifest = _manifest(library)
    path = tmp_path / "manifest.json"
    backfill.write_manifest(path, manifest)
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["tracks"][0]["source"]["album"] = "Tampered"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(backfill.BackfillError, match="digest"):
        backfill.load_manifest(path)

    def drifted_metadata(audio_path):
        result = library.metadata(audio_path)
        if Path(audio_path).name == "track-0.flac":
            result["album"] = "Changed Tag"
        return result

    with pytest.raises(backfill.StaleManifestError, match="differs"):
        backfill.revalidate_manifest(
            manifest,
            connection_factory=library.open_connection,
            metadata_reader=drifted_metadata,
        )


def test_revalidation_rejects_audio_byte_drift(library):
    manifest = _manifest(library)
    library.paths[0].write_bytes(b"replaced audio")

    with pytest.raises(backfill.StaleManifestError, match="differs"):
        backfill.revalidate_manifest(
            manifest,
            connection_factory=library.open_connection,
            metadata_reader=library.metadata,
        )


def test_fill_only_writer_assigns_supported_blanks_and_preserves_everything_else(
    monkeypatch,
):
    row = SimpleNamespace(
        AlbumID=None,
        GenreID=0,
        TrackNo=0,
        DiscNo=None,
        ReleaseDate="",
        ReleaseYear=0,
        Title="Protected Title",
        ArtistID="protected-artist",
        Commnt="protected-comment",
    )

    class Query:
        def filter_by(self, **values):
            assert values == {"ID": "content"}
            return self

        def one(self):
            return row

    class Database:
        flushed = False

        def query(self, _table):
            return Query()

        def flush(self):
            self.flushed = True

    monkeypatch.setattr(
        rb_write,
        "find_or_create_artist",
        lambda _db, _name: SimpleNamespace(ID="album-artist"),
    )
    monkeypatch.setattr(
        rb_write,
        "find_or_create_album",
        lambda _db, _name, _artist: SimpleNamespace(ID="album"),
    )
    monkeypatch.setattr(
        rb_write,
        "find_or_create_genre",
        lambda _db, _name: SimpleNamespace(ID="genre"),
    )
    database = Database()

    changed = rb_write.backfill_content_metadata(
        database,
        "content",
        {
            "album": "Album",
            "album_artist": "Album Artist",
            "genre": "House",
            "track_number": 7,
            "disc_number": 2,
            "release_date": "2026-05-01",
            "release_year": 2026,
            "title": "Must Not Be Used",
        },
    )

    assert changed == (
        "album",
        "genre",
        "track_number",
        "disc_number",
        "release_date",
        "release_year",
    )
    assert (row.AlbumID, row.GenreID, row.TrackNo, row.DiscNo) == (
        "album",
        "genre",
        7,
        2,
    )
    assert (row.ReleaseDate, row.ReleaseYear) == ("2026-05-01", 2026)
    assert (row.Title, row.ArtistID, row.Commnt) == (
        "Protected Title",
        "protected-artist",
        "protected-comment",
    )
    assert database.flushed


def test_fill_only_writer_never_overwrites_existing_target_values(monkeypatch):
    row = SimpleNamespace(
        AlbumID="album-old",
        GenreID="genre-old",
        TrackNo=4,
        DiscNo=1,
        ReleaseDate="2020-01-01",
        ReleaseYear=2020,
    )

    class Query:
        def filter_by(self, **_values):
            return self

        def one(self):
            return row

    database = SimpleNamespace(query=lambda _table: Query(), flush=lambda: None)
    monkeypatch.setattr(
        rb_write,
        "find_or_create_album",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must not resolve album")),
    )
    monkeypatch.setattr(
        rb_write,
        "find_or_create_genre",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must not resolve genre")),
    )

    assert (
        rb_write.backfill_content_metadata(
            database,
            "content",
            {
                "album": "New",
                "genre": "New",
                "track_number": 9,
                "disc_number": 2,
                "release_date": "2026-01-01",
                "release_year": 2026,
            },
        )
        == ()
    )
    assert row.__dict__ == {
        "AlbumID": "album-old",
        "GenreID": "genre-old",
        "TrackNo": 4,
        "DiscNo": 1,
        "ReleaseDate": "2020-01-01",
        "ReleaseYear": 2020,
    }


def test_linked_row_helpers_safely_reactivate_matching_rows():
    deleted_artist = SimpleNamespace(ID="artist", rb_local_deleted=1)
    deleted_album = SimpleNamespace(
        ID="album", AlbumArtistID="artist", rb_local_deleted=1
    )
    deleted_genre = SimpleNamespace(ID="genre", rb_local_deleted=1)
    responses = {
        rb_write.tables.DjmdArtist: [deleted_artist],
        rb_write.tables.DjmdAlbum: [deleted_album],
        rb_write.tables.DjmdGenre: [deleted_genre],
    }

    class Query:
        def __init__(self, rows):
            self.rows = rows

        def filter_by(self, **_values):
            return self

        def all(self):
            return self.rows

    database = SimpleNamespace(query=lambda table: Query(responses[table]))
    artist = rb_write.find_or_create_artist(database, "Album Artist")
    album = rb_write.find_or_create_album(database, "Album", artist)
    genre = rb_write.find_or_create_genre(database, "House")

    assert (artist.ID, album.ID, genre.ID) == ("artist", "album", "genre")
    assert not any(
        int(row.rb_local_deleted or 0)
        for row in (deleted_artist, deleted_album, deleted_genre)
    )


def _apply_sqlite_metadata(library):
    conn = sqlite3.connect(library.db_path)
    conn.execute(
        "INSERT INTO djmdArtist VALUES ('album-artist', 'Audited Album Artist')"
    )
    conn.execute(
        "INSERT INTO djmdAlbum VALUES ('album', 'Audited Album', 'album-artist')"
    )
    conn.execute("INSERT INTO djmdGenre VALUES ('genre', 'House')")
    conn.execute(
        """
        UPDATE djmdContent
        SET AlbumID='album',
            GenreID=CASE WHEN CAST(ID AS INTEGER) < 53 THEN 'genre' ELSE NULL END,
            TrackNo=CAST(ID AS INTEGER) + 1,
            DiscNo=1,
            ReleaseDate='2026-05-01',
            ReleaseYear=2026,
            usn=usn + 1,
            rb_local_usn=rb_local_usn + 1,
            updated_at='2026-08-18'
        """
    )
    conn.commit()
    conn.close()


def test_fresh_read_verification_reports_exact_success_and_repeat_noop(library):
    manifest = _manifest(library)
    _apply_sqlite_metadata(library)

    first = backfill.verify_manifest(
        manifest,
        backup_path="/backups/safety-copy",
        connection_factory=library.open_connection,
        metadata_reader=library.metadata,
    )
    second = backfill.verify_manifest(
        manifest,
        backup_path="/backups/safety-copy",
        connection_factory=library.open_connection,
        metadata_reader=library.metadata,
    )

    assert first == second
    assert first["status"] == "success"
    assert first["verified_tracks"] == 55
    assert first["universal_fields_verified"] == 275
    assert first["genre_fields_verified"] == 53
    assert first["intentional_genre_blanks"] == 2
    assert first["remaining_supported_blanks"] == 0
    assert first["additional_proposed_writes"] == 0
    assert all(first["preservation"].values())


def test_verification_detects_relationship_and_non_target_drift(library):
    manifest = _manifest(library)
    _apply_sqlite_metadata(library)
    conn = sqlite3.connect(library.db_path)
    conn.execute("UPDATE djmdCue SET Comment='changed' WHERE ID='cue-0'")
    conn.execute("UPDATE djmdContent SET Title='changed' WHERE ID='0'")
    conn.commit()
    conn.close()

    report = backfill.verify_manifest(
        manifest,
        backup_path="/backups/safety-copy",
        connection_factory=library.open_connection,
        metadata_reader=library.metadata,
    )

    assert report["status"] == "failed"
    assert any("content_non_target" in item for item in report["mismatches"])
    assert any("preservation cues" in item for item in report["mismatches"])
    assert "Doctor" in report["restoration_guidance"]


def test_stale_preview_never_enters_mutation(library, monkeypatch, tmp_path):
    manifest = _manifest(library)
    entered = []
    monkeypatch.setattr(
        backfill,
        "revalidate_manifest",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            backfill.StaleManifestError("stale")
        ),
    )

    with pytest.raises(backfill.StaleManifestError):
        backfill.apply_manifest(
            manifest,
            backups_root=tmp_path / "backups",
            app_db_path=tmp_path / "syncbox.db",
            report_path=tmp_path / "report.json",
            mutation=lambda *_args, **_kwargs: entered.append(True),
        )
    assert entered == []


def test_apply_routes_all_55_rows_through_one_guarded_mutation(
    library, monkeypatch, tmp_path
):
    manifest = _manifest(library)
    calls = []
    mutation_calls = []
    invalidations = []
    monkeypatch.setattr(backfill, "revalidate_manifest", lambda *_a, **_k: None)
    monkeypatch.setattr(
        backfill,
        "backfill_content_metadata",
        lambda _db, content_id, source: calls.append((content_id, source)),
    )
    success = {
        "status": "success",
        "kind": "report",
        "schema_version": 1,
    }
    monkeypatch.setattr(backfill, "verify_manifest", lambda *_a, **_k: success)
    monkeypatch.setattr(
        backfill.rb.SnapshotCache,
        "invalidate",
        lambda self: invalidations.append(self),
    )

    @contextmanager
    def one_mutation(*args, **kwargs):
        mutation_calls.append((args, kwargs))
        kwargs["backup_observer"](tmp_path / "backups" / "backup")
        yield object()
        kwargs["invalidate_cache"]()

    report_path = tmp_path / "report.json"
    assert (
        backfill.apply_manifest(
            manifest,
            backups_root=tmp_path / "backups",
            app_db_path=tmp_path / "syncbox.db",
            report_path=report_path,
            retention=7,
            mutation=one_mutation,
        )
        == success
    )
    assert len(mutation_calls) == 1
    assert len(calls) == 55
    assert len(invalidations) == 1
    kwargs = mutation_calls[0][1]
    assert kwargs["backup_reason"] == "legacy_metadata_backfill"
    assert kwargs["retention"] == 7
    assert kwargs["app_db_path"] == tmp_path / "syncbox.db"
    assert json.loads(report_path.read_text(encoding="utf-8")) == success


def test_transaction_failure_keeps_backup_location_in_failure_report(
    library, monkeypatch, tmp_path
):
    manifest = _manifest(library)
    monkeypatch.setattr(backfill, "revalidate_manifest", lambda *_a, **_k: None)
    monkeypatch.setattr(
        backfill, "backfill_content_metadata", lambda *_args, **_kwargs: None
    )
    backup_path = tmp_path / "backups" / "pre-write"

    @contextmanager
    def failing_mutation(*_args, **kwargs):
        kwargs["backup_observer"](backup_path)
        yield object()
        raise RuntimeError("commit failed")

    report_path = tmp_path / "report.json"
    with pytest.raises(RuntimeError, match="commit failed"):
        backfill.apply_manifest(
            manifest,
            backups_root=tmp_path / "backups",
            app_db_path=tmp_path / "syncbox.db",
            report_path=report_path,
            mutation=failing_mutation,
        )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["backup_path"] == str(backup_path)
    assert "Doctor" in report["restoration_guidance"]
