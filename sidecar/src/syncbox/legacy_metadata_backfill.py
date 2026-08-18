"""One-shot, manifest-gated repair for the audited legacy Syncbox cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from syncbox import rb
from syncbox.rb_write import (
    _audio_metadata,
    backfill_content_metadata,
    open_rekordbox,
)
from syncbox.safety.mutate import fingerprint, mutate
from syncbox.safety.paths import canonical_key, classify_ownership

KIND = "syncbox-legacy-metadata-backfill"
SCHEMA_VERSION = 1
EXPECTED_TRACKS = 55
LEGACY_START_DATE = "2026-05-28"
METADATA_FIX_DATE = "2026-08-03"

TARGET_COLUMNS = {
    "album": "AlbumID",
    "genre": "GenreID",
    "track_number": "TrackNo",
    "disc_number": "DiscNo",
    "release_date": "ReleaseDate",
    "release_year": "ReleaseYear",
}
SOURCE_FIELDS = (
    "album",
    "album_artist",
    "genre",
    "track_number",
    "disc_number",
    "release_date",
    "release_year",
)
UNIVERSAL_FIELDS = (
    "album",
    "track_number",
    "disc_number",
    "release_date",
    "release_year",
)
BOOKKEEPING_COLUMNS = frozenset({"usn", "rb_local_usn", "updated_at"})
SEMANTIC_ALIASES = frozenset(
    {"current_album", "current_album_artist", "current_genre", "canonical_path"}
)
RELATIONSHIP_TABLES = {
    "cues": "djmdCue",
    "playlists": "djmdSongPlaylist",
    "mytags": "djmdSongMyTag",
    "history": "djmdSongHistory",
}


class BackfillError(RuntimeError):
    """The repair cannot safely continue."""


class StaleManifestError(BackfillError):
    """The reviewed manifest no longer matches current local state."""


class VerificationError(BackfillError):
    """A durable repair did not pass post-commit verification."""


def _blank(value) -> bool:
    return value in (None, "", 0, "0")


def _normalized(value):
    return None if _blank(value) else value


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"$bytes": bytes(value).hex()}
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _canonical_bytes(value) -> bytes:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(value) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_evidence(path: Path) -> dict:
    try:
        file_stat = path.stat()
    except OSError as exc:
        raise BackfillError(f"file is unavailable: {path}") from exc
    if not stat.S_ISREG(file_stat.st_mode):
        raise BackfillError(f"path is not a regular file: {path}")
    try:
        checksum = _sha256(path)
    except OSError as exc:
        raise BackfillError(f"file is unreadable: {path}") from exc
    return {
        "path": str(path),
        "size": str(file_stat.st_size),
        "mtime_ns": str(file_stat.st_mtime_ns),
        "sha256": checksum,
    }


def _anlz_evidence(db_path: Path, analysis_data_path) -> list[dict]:
    if not analysis_data_path:
        return []
    relative = Path(str(analysis_data_path).strip("\\/"))
    root = db_path.parent / "share" / relative.parent
    stem = relative.stem
    evidence = []
    for suffix in ("DAT", "EXT", "2EX"):
        path = (root / f"{stem}.{suffix}").resolve(strict=False)
        if path.exists():
            evidence.append(_file_evidence(path))
    return evidence


def _date(value) -> str:
    return str(value or "")[:10]


def discover_legacy_cohort(rows, storage_root) -> list[dict]:
    """Return the exact audited cohort from plain Rekordbox row mappings."""
    candidates = []
    content_ids = set()
    canonical_paths = set()
    for raw_row in rows:
        row = dict(raw_row)
        stored_path = row.get("FolderPath")
        if int(row.get("rb_local_deleted") or 0) or not stored_path:
            continue
        if classify_ownership(stored_path, storage_root) != "permanent_library":
            continue
        if not (
            LEGACY_START_DATE <= _date(row.get("StockDate")) < METADATA_FIX_DATE
            and LEGACY_START_DATE <= _date(row.get("DateCreated")) < METADATA_FIX_DATE
        ):
            continue
        if not all(_blank(row.get(column)) for column in TARGET_COLUMNS.values()):
            continue

        content_id = str(row.get("ID"))
        path = canonical_key(stored_path, storage_root)
        if content_id in content_ids:
            raise BackfillError(f"duplicate content identity: {content_id}")
        if path in canonical_paths:
            raise BackfillError(f"duplicate canonical audio path: {path}")
        content_ids.add(content_id)
        canonical_paths.add(path)
        row["canonical_path"] = path
        candidates.append(row)

    if len(candidates) != EXPECTED_TRACKS:
        raise BackfillError(
            f"legacy cohort must contain exactly {EXPECTED_TRACKS} active rows; "
            f"found {len(candidates)}"
        )
    return sorted(candidates, key=lambda row: (str(row["ID"]), row["canonical_path"]))


def _content_rows(conn, content_ids=None) -> list[dict]:
    sql = """
    SELECT c.*, album.Name AS current_album,
           album_artist.Name AS current_album_artist,
           genre.Name AS current_genre
    FROM djmdContent c
    LEFT JOIN djmdAlbum album ON album.ID = c.AlbumID
    LEFT JOIN djmdArtist album_artist ON album_artist.ID = album.AlbumArtistID
    LEFT JOIN djmdGenre genre ON genre.ID = c.GenreID
    WHERE c.rb_local_deleted = 0
    """
    params = ()
    if content_ids is not None:
        ids = tuple(str(value) for value in content_ids)
        if not ids:
            return []
        sql += f" AND c.ID IN ({','.join('?' for _ in ids)})"
        params = ids
    cursor = conn.execute(sql, params)
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _table_rows_by_content(conn, table: str, content_ids) -> dict[str, list[dict]]:
    ids = tuple(str(value) for value in content_ids)
    placeholders = ",".join("?" for _ in ids)
    cursor = conn.execute(
        f"SELECT * FROM {table} WHERE ContentID IN ({placeholders}) "
        "ORDER BY ContentID, ID",
        ids,
    )
    columns = [item[0] for item in cursor.description]
    grouped = defaultdict(list)
    for values in cursor.fetchall():
        row = dict(zip(columns, values, strict=True))
        grouped[str(row["ContentID"])].append(row)
    return grouped


def _relationship_digests(conn, content_ids) -> dict[str, dict]:
    ids = tuple(str(value) for value in content_ids)
    result = {content_id: {} for content_id in ids}
    for label, table in RELATIONSHIP_TABLES.items():
        grouped = _table_rows_by_content(conn, table, ids)
        for content_id in ids:
            result[content_id][label] = _digest(grouped.get(content_id, []))
    return result


def _non_target_content(row: dict) -> dict:
    excluded = set(TARGET_COLUMNS.values()) | BOOKKEEPING_COLUMNS | SEMANTIC_ALIASES
    return {key: value for key, value in row.items() if key not in excluded}


def _source_metadata(path: Path, reader) -> dict:
    try:
        metadata = reader(path)
    except Exception as exc:
        raise BackfillError(f"audio metadata is unreadable: {path}") from exc
    if not isinstance(metadata, dict):
        raise BackfillError(f"audio metadata parser returned an invalid result: {path}")
    return {field: _normalized(metadata.get(field)) for field in SOURCE_FIELDS}


def _proposed_fields(row: dict, source: dict) -> list[str]:
    return [
        field
        for field, column in TARGET_COLUMNS.items()
        if _blank(row.get(column)) and not _blank(source.get(field))
    ]


def _track_manifest(
    row: dict,
    relationships: dict,
    db_path: Path,
    metadata_reader,
) -> dict:
    path = Path(row["canonical_path"])
    audio = _file_evidence(path)
    source = _source_metadata(path, metadata_reader)
    before = {
        "album_id": _normalized(row.get("AlbumID")),
        "album": _normalized(row.get("current_album")),
        "album_artist": _normalized(row.get("current_album_artist")),
        "genre_id": _normalized(row.get("GenreID")),
        "genre": _normalized(row.get("current_genre")),
        "track_number": _normalized(row.get("TrackNo")),
        "disc_number": _normalized(row.get("DiscNo")),
        "release_date": _normalized(row.get("ReleaseDate")),
        "release_year": _normalized(row.get("ReleaseYear")),
    }
    after = {field: source[field] for field in SOURCE_FIELDS}
    return {
        "content_id": str(row["ID"]),
        "title": str(row.get("Title") or ""),
        "stored_path": str(row["FolderPath"]),
        "canonical_path": row["canonical_path"],
        "stock_date": _date(row.get("StockDate")),
        "date_created": _date(row.get("DateCreated")),
        "before": before,
        "source": source,
        "after": after,
        "proposed_fields": _proposed_fields(row, source),
        "audio": audio,
        "anlz": _anlz_evidence(db_path, row.get("AnalysisDataPath")),
        "preservation": {
            "content_non_target": _digest(_non_target_content(row)),
            **relationships,
        },
    }


def _aggregate(tracks) -> dict:
    counts = Counter(
        field for track in tracks for field in track.get("proposed_fields", ())
    )
    return {
        "track_count": len(tracks),
        "proposed_writes": {field: counts.get(field, 0) for field in TARGET_COLUMNS},
        "total_proposed_writes": sum(counts.values()),
        "universal_fields_per_track": len(UNIVERSAL_FIELDS),
        "intentional_genre_blanks": len(tracks) - counts.get("genre", 0),
    }


def _validate_expected_aggregate(aggregate: dict) -> None:
    writes = aggregate["proposed_writes"]
    for field in UNIVERSAL_FIELDS:
        if writes.get(field) != EXPECTED_TRACKS:
            raise BackfillError(
                f"expected {EXPECTED_TRACKS} {field} proposals; "
                f"found {writes.get(field, 0)}"
            )
    if writes.get("genre") != 53:
        raise BackfillError(
            f"expected 53 genre proposals; found {writes.get('genre', 0)}"
        )
    if aggregate["intentional_genre_blanks"] != 2:
        raise BackfillError("expected exactly two intentional genre blanks")


def _seal(payload: dict) -> dict:
    sealed = dict(payload)
    sealed["manifest_sha256"] = _digest(payload)
    return sealed


def _fingerprint_json(db_path) -> list[list[str]]:
    return [list(part) for part in fingerprint(db_path)]


def build_manifest(
    db_path,
    storage_root,
    *,
    connection_factory=None,
    metadata_reader=None,
) -> dict:
    """Collect a complete manifest through one stable read-only snapshot."""
    db_path = Path(db_path).expanduser().resolve(strict=True)
    storage_root = Path(storage_root).expanduser().resolve(strict=True)
    connection_factory = connection_factory or rb.open_readonly
    metadata_reader = metadata_reader or _audio_metadata
    before_fingerprint = _fingerprint_json(db_path)
    conn = connection_factory(db_path)
    try:
        rows = _content_rows(conn)
        candidates = discover_legacy_cohort(rows, storage_root)
        relationships = _relationship_digests(
            conn, [str(row["ID"]) for row in candidates]
        )
    finally:
        conn.close()

    tracks = [
        _track_manifest(
            row,
            relationships[str(row["ID"])],
            db_path,
            metadata_reader,
        )
        for row in candidates
    ]
    aggregate = _aggregate(tracks)
    _validate_expected_aggregate(aggregate)
    if _fingerprint_json(db_path) != before_fingerprint:
        raise StaleManifestError(
            "Rekordbox changed while the preview was collected; retry when stable"
        )
    return _seal(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "cohort": {
                "start_date_inclusive": LEGACY_START_DATE,
                "end_date_exclusive": METADATA_FIX_DATE,
                "expected_tracks": EXPECTED_TRACKS,
            },
            "database": {
                "path": str(db_path),
                "fingerprint": before_fingerprint,
            },
            "storage_root": str(storage_root),
            "aggregate": aggregate,
            "tracks": tracks,
        }
    )


def _atomic_write_json(path, payload) -> Path:
    target = Path(path).expanduser().resolve(strict=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
        if hasattr(os, "O_DIRECTORY"):
            directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target


def write_manifest(path, manifest: dict) -> Path:
    validate_manifest(manifest)
    return _atomic_write_json(path, manifest)


def validate_manifest(manifest: dict) -> None:
    if not isinstance(manifest, dict):
        raise BackfillError("manifest must be a JSON object")
    required = {
        "kind",
        "schema_version",
        "cohort",
        "database",
        "storage_root",
        "aggregate",
        "tracks",
        "manifest_sha256",
    }
    if set(manifest) != required:
        raise BackfillError("manifest has missing or unsupported top-level fields")
    if manifest["kind"] != KIND or manifest["schema_version"] != SCHEMA_VERSION:
        raise BackfillError("manifest kind or schema version is unsupported")
    unsigned = {
        key: value for key, value in manifest.items() if key != "manifest_sha256"
    }
    if manifest["manifest_sha256"] != _digest(unsigned):
        raise BackfillError("manifest digest does not match its contents")
    if manifest["cohort"] != {
        "start_date_inclusive": LEGACY_START_DATE,
        "end_date_exclusive": METADATA_FIX_DATE,
        "expected_tracks": EXPECTED_TRACKS,
    }:
        raise BackfillError("manifest cohort signature is unsupported")
    database = manifest.get("database")
    if not isinstance(database, dict) or set(database) != {"path", "fingerprint"}:
        raise BackfillError("manifest database identity is invalid")
    if not isinstance(database["path"], str) or not isinstance(
        manifest["storage_root"], str
    ):
        raise BackfillError("manifest database and storage paths are invalid")
    if (
        not Path(database["path"]).is_absolute()
        or not Path(manifest["storage_root"]).is_absolute()
    ):
        raise BackfillError("manifest database and storage paths must be absolute")
    fingerprint_parts = database["fingerprint"]
    if not isinstance(fingerprint_parts, list) or not 1 <= len(fingerprint_parts) <= 2:
        raise BackfillError("manifest database fingerprint is invalid")
    if any(
        not isinstance(part, list)
        or len(part) != 2
        or any(not isinstance(item, str) for item in part)
        for part in fingerprint_parts
    ):
        raise BackfillError("manifest database fingerprint is invalid")
    tracks = manifest.get("tracks")
    if not isinstance(tracks, list) or len(tracks) != EXPECTED_TRACKS:
        raise BackfillError(f"manifest must contain exactly {EXPECTED_TRACKS} tracks")
    track_fields = {
        "content_id",
        "title",
        "stored_path",
        "canonical_path",
        "stock_date",
        "date_created",
        "before",
        "source",
        "after",
        "proposed_fields",
        "audio",
        "anlz",
        "preservation",
    }
    before_fields = {
        "album_id",
        "album",
        "album_artist",
        "genre_id",
        "genre",
        "track_number",
        "disc_number",
        "release_date",
        "release_year",
    }
    preservation_fields = {
        "content_non_target",
        "cues",
        "playlists",
        "mytags",
        "history",
    }
    evidence_fields = {"path", "size", "mtime_ns", "sha256"}
    for track in tracks:
        if not isinstance(track, dict) or set(track) != track_fields:
            raise BackfillError("manifest track structure is invalid")
        if (
            not isinstance(track["before"], dict)
            or set(track["before"]) != before_fields
            or any(not _blank(value) for value in track["before"].values())
        ):
            raise BackfillError("manifest before-values are invalid")
        if not isinstance(track["source"], dict) or set(track["source"]) != set(
            SOURCE_FIELDS
        ):
            raise BackfillError("manifest source metadata is invalid")
        if any(_blank(track["source"][field]) for field in UNIVERSAL_FIELDS):
            raise BackfillError("manifest is missing universal source metadata")
        if not isinstance(track["after"], dict) or track["after"] != track["source"]:
            raise BackfillError("manifest after-values differ from source metadata")
        expected_fields = [
            field for field in TARGET_COLUMNS if not _blank(track["source"].get(field))
        ]
        if (
            not isinstance(track["proposed_fields"], list)
            or track["proposed_fields"] != expected_fields
        ):
            raise BackfillError("manifest proposed fields are invalid")
        if (
            not isinstance(track["audio"], dict)
            or set(track["audio"]) != evidence_fields
        ):
            raise BackfillError("manifest audio evidence is invalid")
        if track["audio"]["path"] != track["canonical_path"]:
            raise BackfillError("manifest audio identity is inconsistent")
        if not isinstance(track["anlz"], list) or any(
            not isinstance(item, dict) or set(item) != evidence_fields
            for item in track["anlz"]
        ):
            raise BackfillError("manifest ANLZ evidence is invalid")
        if (
            not isinstance(track["preservation"], dict)
            or set(track["preservation"]) != preservation_fields
        ):
            raise BackfillError("manifest preservation evidence is invalid")
    ids = [str(track.get("content_id")) for track in tracks]
    paths = [track.get("canonical_path") for track in tracks]
    if len(set(ids)) != EXPECTED_TRACKS or len(set(paths)) != EXPECTED_TRACKS:
        raise BackfillError("manifest contains duplicate content or file identities")
    if tracks != sorted(
        tracks, key=lambda track: (str(track["content_id"]), track["canonical_path"])
    ):
        raise BackfillError("manifest tracks are not deterministically ordered")
    if manifest["aggregate"] != _aggregate(tracks):
        raise BackfillError("manifest aggregate does not match its tracks")
    _validate_expected_aggregate(manifest["aggregate"])


def load_manifest(path) -> dict:
    try:
        with Path(path).expanduser().open(encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise BackfillError(f"manifest is unreadable: {path}") from exc
    validate_manifest(manifest)
    return manifest


def revalidate_manifest(manifest: dict, **kwargs) -> None:
    validate_manifest(manifest)
    try:
        current = build_manifest(
            manifest["database"]["path"], manifest["storage_root"], **kwargs
        )
    except BackfillError as exc:
        raise StaleManifestError(f"manifest is stale: {exc}") from exc
    if current != manifest:
        raise StaleManifestError(
            "manifest differs from the current database, tags, files, or relationships"
        )


def _current_track_evidence(
    row: dict,
    relationships: dict,
    db_path: Path,
    storage_root,
    metadata_reader,
) -> dict:
    canonical_path = canonical_key(row["FolderPath"], storage_root)
    path = Path(canonical_path)
    return {
        "canonical_path": canonical_path,
        "source": _source_metadata(path, metadata_reader),
        "audio": _file_evidence(path),
        "anlz": _anlz_evidence(db_path, row.get("AnalysisDataPath")),
        "target": {
            "album_id": _normalized(row.get("AlbumID")),
            "album": _normalized(row.get("current_album")),
            "album_artist": _normalized(row.get("current_album_artist")),
            "genre_id": _normalized(row.get("GenreID")),
            "genre": _normalized(row.get("current_genre")),
            "track_number": _normalized(row.get("TrackNo")),
            "disc_number": _normalized(row.get("DiscNo")),
            "release_date": _normalized(row.get("ReleaseDate")),
            "release_year": _normalized(row.get("ReleaseYear")),
        },
        "preservation": {
            "content_non_target": _digest(_non_target_content(row)),
            **relationships,
        },
    }


def _expected_target(track: dict) -> dict:
    source = track["source"]
    return {
        "album": source["album"],
        "album_artist": source["album_artist"],
        "genre": source["genre"],
        "track_number": source["track_number"],
        "disc_number": source["disc_number"],
        "release_date": source["release_date"],
        "release_year": source["release_year"],
    }


def verify_manifest(
    manifest: dict,
    *,
    backup_path=None,
    connection_factory=None,
    metadata_reader=None,
) -> dict:
    """Verify committed state through a fresh read-only connection."""
    validate_manifest(manifest)
    db_path = Path(manifest["database"]["path"])
    storage_root = manifest["storage_root"]
    connection_factory = connection_factory or rb.open_readonly
    metadata_reader = metadata_reader or _audio_metadata
    content_ids = [track["content_id"] for track in manifest["tracks"]]
    before_fingerprint = _fingerprint_json(db_path)
    conn = connection_factory(db_path)
    try:
        rows = _content_rows(conn, content_ids)
        relationships = _relationship_digests(conn, content_ids)
    finally:
        conn.close()
    rows_by_id = {str(row["ID"]): row for row in rows}

    mismatches = []
    track_results = []
    remaining_blanks = 0
    proposed_writes = 0
    for track in manifest["tracks"]:
        content_id = track["content_id"]
        row = rows_by_id.get(content_id)
        checks = {}
        if row is None:
            mismatches.append(f"content {content_id} is missing or inactive")
            track_results.append(
                {"content_id": content_id, "title": track["title"], "checks": checks}
            )
            continue
        try:
            current = _current_track_evidence(
                row,
                relationships[content_id],
                db_path,
                storage_root,
                metadata_reader,
            )
        except BackfillError as exc:
            mismatches.append(f"content {content_id} evidence is unavailable: {exc}")
            track_results.append(
                {"content_id": content_id, "title": track["title"], "checks": checks}
            )
            continue
        expected_target = _expected_target(track)
        for field, expected in expected_target.items():
            actual = current["target"][field]
            checks[field] = actual == expected
            if actual != expected:
                mismatches.append(f"content {content_id} has mismatched {field}")
            if not _blank(expected) and _blank(actual):
                remaining_blanks += 1
                proposed_writes += 1
        if current["source"] != track["source"]:
            mismatches.append(f"content {content_id} source tags changed")
        if current["canonical_path"] != track["canonical_path"]:
            mismatches.append(f"content {content_id} path identity changed")
        if current["audio"] != track["audio"]:
            mismatches.append(f"content {content_id} audio evidence changed")
        if current["anlz"] != track["anlz"]:
            mismatches.append(f"content {content_id} ANLZ evidence changed")
        for label, expected in track["preservation"].items():
            if current["preservation"].get(label) != expected:
                mismatches.append(f"content {content_id} changed preservation {label}")
        track_results.append(
            {"content_id": content_id, "title": track["title"], "checks": checks}
        )

    after_fingerprint = _fingerprint_json(db_path)
    if after_fingerprint != before_fingerprint:
        mismatches.append("database changed during post-commit verification")
    status = "success" if not mismatches else "failed"
    backup = str(backup_path) if backup_path else None
    return {
        "kind": f"{KIND}-report",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "manifest_sha256": manifest["manifest_sha256"],
        "backup_path": backup,
        "verified_tracks": EXPECTED_TRACKS if status == "success" else 0,
        "universal_fields_verified": (
            EXPECTED_TRACKS * len(UNIVERSAL_FIELDS) if status == "success" else 0
        ),
        "genre_fields_verified": 53 if status == "success" else 0,
        "intentional_genre_blanks": 2,
        "remaining_supported_blanks": remaining_blanks,
        "additional_proposed_writes": proposed_writes,
        "preservation": {
            "content_identity": not any("identity" in item for item in mismatches),
            "non_target_content": not any(
                "content_non_target" in item for item in mismatches
            ),
            "cues": not any("preservation cues" in item for item in mismatches),
            "playlist_memberships": not any(
                "preservation playlists" in item for item in mismatches
            ),
            "mytag_memberships": not any(
                "preservation mytags" in item for item in mismatches
            ),
            "history_memberships": not any(
                "preservation history" in item for item in mismatches
            ),
            "audio": not any("audio evidence" in item for item in mismatches),
            "anlz": not any("ANLZ evidence" in item for item in mismatches),
        },
        "tracks": track_results,
        "mismatches": mismatches,
        "restoration_guidance": (
            None
            if status == "success"
            else "Open Syncbox Doctor > Backups and restore the reported "
            "pre-write backup before any further repair."
        ),
    }


def apply_manifest(
    manifest: dict,
    *,
    backups_root,
    app_db_path,
    report_path,
    retention: int = 20,
    mutation=mutate,
    opener=open_rekordbox,
    connection_factory=None,
    metadata_reader=None,
) -> dict:
    """Revalidate, mutate all 55 rows once, then verify from a fresh read."""
    revalidate_manifest(
        manifest,
        connection_factory=connection_factory,
        metadata_reader=metadata_reader,
    )
    db_path = Path(manifest["database"]["path"])
    expected_fingerprint = tuple(
        tuple(part) for part in manifest["database"]["fingerprint"]
    )
    backup_files = sorted(
        {evidence["path"] for track in manifest["tracks"] for evidence in track["anlz"]}
    )
    backup_seen = []
    cache = rb.SnapshotCache(db_path)
    try:
        with mutation(
            db_path,
            backups_root,
            retention=retention,
            expected_fingerprint=expected_fingerprint,
            open_db=opener,
            invalidate_cache=cache.invalidate,
            backup_files=backup_files,
            backup_observer=backup_seen.append,
            app_db_path=app_db_path,
            backup_reason="legacy_metadata_backfill",
        ) as db:
            for track in manifest["tracks"]:
                backfill_content_metadata(db, track["content_id"], track["source"])
    except BaseException as exc:
        if backup_seen:
            _atomic_write_json(
                report_path,
                {
                    "kind": f"{KIND}-report",
                    "schema_version": SCHEMA_VERSION,
                    "status": "failed",
                    "manifest_sha256": manifest["manifest_sha256"],
                    "backup_path": str(backup_seen[-1]),
                    "mismatches": [f"mutation failed: {type(exc).__name__}: {exc}"],
                    "restoration_guidance": "Open Syncbox Doctor > Backups and "
                    "restore the reported pre-write backup before retrying.",
                },
            )
        raise

    try:
        report = verify_manifest(
            manifest,
            backup_path=backup_seen[-1],
            connection_factory=connection_factory,
            metadata_reader=metadata_reader,
        )
    except BaseException as exc:
        report = {
            "kind": f"{KIND}-report",
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "manifest_sha256": manifest["manifest_sha256"],
            "backup_path": str(backup_seen[-1]),
            "mismatches": [
                f"post-commit verification failed: {type(exc).__name__}: {exc}"
            ],
            "restoration_guidance": "Open Syncbox Doctor > Backups and restore "
            "the reported pre-write backup before any further repair.",
        }
    _atomic_write_json(report_path, report)
    if report["status"] != "success":
        raise VerificationError(
            f"post-commit verification failed; restore {backup_seen[-1]} via Doctor"
        )
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="syncbox-sidecar --legacy-metadata-backfill")
    commands = parser.add_subparsers(dest="command", required=True)
    preview = commands.add_parser("preview")
    preview.add_argument("--db-path", required=True)
    preview.add_argument("--storage-root", required=True)
    preview.add_argument("--manifest", required=True)
    apply = commands.add_parser("apply")
    apply.add_argument("--manifest", required=True)
    apply.add_argument("--backups-root", required=True)
    apply.add_argument("--app-db-path", required=True)
    apply.add_argument("--report", required=True)
    apply.add_argument("--retention", type=int, default=20)
    verify = commands.add_parser("verify")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--report", required=True)
    verify.add_argument("--backup-path")
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "preview":
            manifest = build_manifest(args.db_path, args.storage_root)
            path = write_manifest(args.manifest, manifest)
            print(
                json.dumps(
                    {"manifest": str(path), "aggregate": manifest["aggregate"]},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
        manifest = load_manifest(args.manifest)
        if args.command == "apply":
            report = apply_manifest(
                manifest,
                backups_root=args.backups_root,
                app_db_path=args.app_db_path,
                report_path=args.report,
                retention=args.retention,
            )
        else:
            report = verify_manifest(manifest, backup_path=args.backup_path)
            _atomic_write_json(args.report, report)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "report": str(Path(args.report).expanduser().resolve(strict=False)),
                },
                sort_keys=True,
            )
        )
        return 0 if report["status"] == "success" else 1
    except BackfillError as exc:
        print(str(exc), file=sys.stderr)
        return 1
