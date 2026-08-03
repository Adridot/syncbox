"""Rekordbox snapshot - read-once, cached on the mutate fingerprint
(SPEC-UNIFIED 4 "Track Rekordbox", 11.3 readout fields).

The snapshot reads through a raw sqlcipher3 connection opened mode=ro: the
SQLite layer itself refuses writes (POC #9 pattern), so no read path can
ever mutate master.db. The SQLCipher key is the public constant shipped by
pyrekordbox (research 00_RB: it is not a lock), obtained programmatically -
never persisted by Syncbox.

Write paths do NOT live here: every mutation goes through pyrekordbox
inside the safety.mutate unit-of-work.
"""

from datetime import datetime
from pathlib import Path

import sqlcipher3
from pyrekordbox.db6.database import BLOB
from pyrekordbox.utils import deobfuscate

from syncbox.safety.mutate import StaleSnapshotError, fingerprint
from syncbox.safety.paths import classify_ownership, resolve_stored_path, tcc_exists
from syncbox.spotify import scrub_obfuscated, spotify_id_from_path


def rekordbox_key() -> str:
    return deobfuscate(BLOB)


def open_readonly(db_path) -> sqlcipher3.Connection:
    conn = sqlcipher3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
    # Text-passphrase form - pyrekordbox applies the key the same way.
    conn.execute(f"PRAGMA key = '{rekordbox_key()}'")
    return conn


_CONTENT_SQL = """
SELECT c.ID, c.Title, a.Name AS artist, r.Name AS remixer, c.Length, c.ISRC, c.BitRate,
       c.FolderPath, k.ScaleName, g.Name AS genre, c.DJPlayCount,
       c.StockDate, c.created_at, c.Rating, c.FileSize, c.SampleRate,
       c.BitDepth, c.FileType, c.Analysed
FROM djmdContent c
LEFT JOIN djmdArtist a ON a.ID = c.ArtistID
LEFT JOIN djmdArtist r ON r.ID = c.RemixerID
LEFT JOIN djmdKey k ON k.ID = c.KeyID
LEFT JOIN djmdGenre g ON g.ID = c.GenreID
WHERE c.rb_local_deleted = 0
"""

_COUNT_SQL = {
    "cue_count": "SELECT ContentID, COUNT(*) FROM djmdCue WHERE rb_local_deleted = 0 GROUP BY ContentID",
    "playlist_count": "SELECT ContentID, COUNT(*) FROM djmdSongPlaylist WHERE rb_local_deleted = 0 GROUP BY ContentID",
    "tag_count": "SELECT ContentID, COUNT(*) FROM djmdSongMyTag WHERE rb_local_deleted = 0 GROUP BY ContentID",
}


def _epoch(value) -> int:
    if not value:
        return 0
    try:
        return int(datetime.fromisoformat(str(value).split("+")[0].strip()).timestamp())
    except ValueError:
        return 0


def load_snapshot(db_path, storage_root) -> list[dict]:
    """All active (non-soft-deleted) content rows as plain dicts."""
    conn = open_readonly(db_path)
    try:
        counts = {name: dict(conn.execute(sql)) for name, sql in _COUNT_SQL.items()}
        rows = []
        for (
            content_id, title, artist, remixer, length, isrc, bit_rate, folder_path,
            scale_name, genre, play_count, stock_date, created_at, rating,
            file_size, sample_rate, bit_depth, file_type, analysed,
        ) in conn.execute(_CONTENT_SQL):
            # A Spotify streaming reference has NO local file: no resolved
            # path, and by definition never a missing file.
            spotify_track_id = spotify_id_from_path(folder_path)
            resolved = (
                resolve_stored_path(folder_path, storage_root)
                if folder_path and spotify_track_id is None
                else None
            )
            rows.append(
                {
                    "content_id": str(content_id),
                    "title": scrub_obfuscated(title),
                    "artist": scrub_obfuscated(artist),
                    "remixer": scrub_obfuscated(remixer),
                    "duration_ms": int(length * 1000) if length else 0,
                    "isrc": isrc,
                    "bit_rate": bit_rate,
                    "file_path": folder_path,
                    "spotify_track_id": spotify_track_id,
                    "resolved_path": str(resolved) if resolved else None,
                    "file_missing": (
                        not tcc_exists(resolved)
                        if resolved
                        else spotify_track_id is None
                    ),
                    "ownership": (
                        classify_ownership(folder_path, storage_root)
                        if folder_path
                        else "external"
                    ),
                    "key_name": scale_name,
                    "genre": genre,
                    "play_count": play_count,
                    "stock_date": stock_date,
                    "date_created": created_at,
                    "date_created_order": _epoch(created_at),
                    "rating": rating,
                    "file_size": file_size,
                    "sample_rate": sample_rate,
                    "bit_depth": bit_depth,
                    "file_type": file_type,
                    "analysed": analysed,
                    "cue_count": counts["cue_count"].get(content_id, 0),
                    "playlist_count": counts["playlist_count"].get(content_id, 0),
                    "tag_count": counts["tag_count"].get(content_id, 0),
                }
            )
        return rows
    finally:
        conn.close()


class SnapshotCache:
    """Read-once cache keyed on the (mtime,size) fingerprint of
    master.db(+wal) - the same normalized fingerprint the mutate freshness
    guard uses, so 'what the dry-run saw' and 'what mutate re-asserts' can
    never diverge. Plug .invalidate into mutate(invalidate_cache=...)."""

    def __init__(self, db_path, loader=load_snapshot):
        self._db_path = Path(db_path)
        self._loader = loader
        self._fingerprint = None
        self._storage_root = None
        self._rows = None

    def get(self, storage_root) -> list[dict]:
        current = fingerprint(self._db_path)
        if (
            self._rows is None
            or current != self._fingerprint
            or str(storage_root) != self._storage_root
        ):
            for _ in range(3):
                rows = self._loader(self._db_path, storage_root)
                after = fingerprint(self._db_path)
                if current == after:
                    self._rows = rows
                    self._fingerprint = after
                    self._storage_root = str(storage_root)
                    break
                current = after
            else:
                raise StaleSnapshotError(
                    f"{self._db_path} kept changing while its snapshot was loaded; "
                    "nothing was written. Retry when Rekordbox is fully closed."
                )
        return self._rows

    @property
    def current_fingerprint(self):
        """Fingerprint the cached rows were loaded under - THE
        expected_fingerprint to pass to mutate() for dry-run freshness."""
        return self._fingerprint

    def invalidate(self) -> None:
        self._rows = None
        self._fingerprint = None
