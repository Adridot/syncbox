"""POC #9 core prototype - Smart Fixes (A1) bulk-write safety kernel.

Minimal, disposable implementation of SPEC-UNIFIED 3.1 + 5.11:

- ``_mutate`` unit-of-work: (a) assert RB closed + DB exists -> freshness
  guard at entry (spec 5.11) -> (b) timestamped backup of master.db(+wal/shm)
  with same-second collision suffix -> (c) open -> (d) mutate -> (e) commit +
  invalidate snapshot cache; rollback + re-raise on exception; close in
  finally.
- FIXED catalog of 3 structural fixes, applied in a deterministic order,
  producing one composed final result per field.
- ``dry_run``: reads a snapshot cached on (mtime,size) of master.db(+wal),
  opened READ-ONLY (sqlcipher ``mode=ro`` URI - writes are refused by
  SQLite itself), never opens the DB for write, never calls the RB-closed
  guard. Emits exact per-track field before/after rows, no no-op rows.
- ``protected`` tracks (path rule: under ``<storage_root>/rekordbox/
  Collection``) are EXCLUDED by default; inclusion only via an explicit
  per-call opt-in argument that is never stored anywhere.
"""

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import NamedTuple, Optional

import psutil
import sqlcipher3

KEY = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497"

PROTECTED_PATH_MARKER = "/rekordbox/Collection"  # spec section 4 storage layout


class RekordboxRunningError(RuntimeError):
    pass


class StaleSnapshotError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# RB process guard (POC #5 strict filter; spec 5.1)
# ---------------------------------------------------------------------------

GUARD_CALLS = 0


def _rb_processes():  # split out so the harness can monkeypatch it
    procs = []
    for p in psutil.process_iter(["name", "exe"]):
        try:
            name = (p.info["name"] or "").lower()
            exe = (p.info["exe"] or "").lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        if (
            name in ("rekordbox", "rekordboxagent", "rekordbox.exe", "rekordboxagent.exe")
            or "/rekordbox.app/" in exe
            or "/rekordboxagent.app/" in exe
            or exe.endswith("/rekordbox")
            or exe.endswith("/rekordboxagent")
        ):
            procs.append(p)
    return procs


def assert_rb_closed():
    """Friendly message: no PID, no /Applications/ path, no --type= flag."""
    global GUARD_CALLS
    GUARD_CALLS += 1
    if _rb_processes():
        raise RekordboxRunningError(
            "Rekordbox seems to be open. Please close Rekordbox (including its "
            "background agent) and try again."
        )


# ---------------------------------------------------------------------------
# Fingerprint + read-only snapshot cache (spec section 4: (mtime,size) of
# master.db(+wal))
# ---------------------------------------------------------------------------

SNAP_LOADS = 0
_SNAP_CACHE: dict = {}


def db_fingerprint(db_path: Path) -> tuple:
    """(mtime,size) of master.db(+wal), NORMALIZED.

    Measured on this fixture (macOS/APFS, sqlcipher): closing the last rw
    connection checkpoints + DELETES the -wal, and a subsequent mode=ro open
    RECREATES a 0-byte -wal (+ -shm). An empty WAL carries no journal
    content - the logical DB state is fully determined by master.db - so
    'wal absent' and 'wal empty' must fingerprint identically (and an empty
    wal's mtime is bookkeeping noise), otherwise every read would spuriously
    stale the freshness guard."""
    st = db_path.stat()
    wal = Path(str(db_path) + "-wal")
    wal_part = None
    if wal.exists():
        wst = wal.stat()
        if wst.st_size > 0:
            wal_part = (wst.st_mtime_ns, wst.st_size)
    return ((st.st_mtime_ns, st.st_size), wal_part)


def invalidate_snapshot_cache():
    _SNAP_CACHE.clear()


class TrackRow(NamedTuple):
    id: str
    title: Optional[str]
    artist: Optional[str]
    path: Optional[str]
    protected: bool


class Snapshot(NamedTuple):
    fingerprint: tuple
    rows: dict  # id -> TrackRow


def get_snapshot(db_path: Path) -> Snapshot:
    """Read-only snapshot of active tracks, cached on (mtime,size)."""
    fp = db_fingerprint(db_path)
    cached = _SNAP_CACHE.get(fp)
    if cached is not None:
        return cached
    global SNAP_LOADS
    SNAP_LOADS += 1
    con = sqlcipher3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        con.execute(f"PRAGMA key = '{KEY}'")
        rows = {}
        for cid, title, aname, fpath in con.execute(
            "SELECT c.ID, c.Title, a.Name, c.FolderPath FROM djmdContent c "
            "LEFT JOIN djmdArtist a ON a.ID = c.ArtistID "
            "WHERE c.rb_local_deleted = 0"  # read invariant: filter soft-deleted
        ):
            rows[cid] = TrackRow(
                id=cid,
                title=title or None,
                artist=aname or None,
                path=fpath or None,
                protected=bool(fpath and PROTECTED_PATH_MARKER in fpath),
            )
    finally:
        con.close()
    snap = Snapshot(fingerprint=fp, rows=rows)
    _SNAP_CACHE.clear()
    _SNAP_CACHE[fp] = snap
    return snap


# ---------------------------------------------------------------------------
# FIXED fix catalog - deterministic order, composed result per field
# ---------------------------------------------------------------------------

_URL_RE = re.compile(
    r"(?:https?://\S+|www\.\S+|\S+\.(?:com|net|org|io|kz|ru|info)(?:/\S*)?)",
    re.IGNORECASE,
)
_EDGE_JUNK_RE = re.compile(r"^[\s\-|/•~]+|[\s\-|/•~\[\(]+$")
_WS_RE = re.compile(r"\s+")


def _fix_strip_url_junk(fields: dict) -> dict:
    t = fields["title"]
    if t:
        new = _URL_RE.sub("", t)
        new = _EDGE_JUNK_RE.sub("", new)
        if new.strip():  # never empty a field
            fields["title"] = new
    return fields


def _fix_extract_artist_from_title(fields: dict) -> dict:
    t, a = fields["title"], fields["artist"]
    if t and " - " in t and not (a or "").strip():
        left, right = t.split(" - ", 1)
        if left.strip() and right.strip():
            fields["artist"] = left.strip()
            fields["title"] = right.strip()
    return fields


def _fix_collapse_whitespace(fields: dict) -> dict:
    for k in ("title", "artist"):
        v = fields[k]
        if v:
            new = _WS_RE.sub(" ", v.replace("\u00a0", " ")).strip()
            if new:
                fields[k] = new
    return fields


# Deterministic order (spec 5.11): junk/URL strip MUST run before extraction
# (otherwise "Track - www.x.com" would extract "Track" as the artist);
# whitespace collapse runs last to clean residue left by the first two.
CATALOG = (
    ("strip_url_junk", _fix_strip_url_junk),
    ("extract_artist_from_title", _fix_extract_artist_from_title),
    ("collapse_whitespace", _fix_collapse_whitespace),
)


def compose_fixes(title: Optional[str], artist: Optional[str]) -> dict:
    """Apply the whole catalog in order; one composed final result per field."""
    fields = {"title": title, "artist": artist}
    for _name, fn in CATALOG:
        fields = fn(fields)
    return fields


# ---------------------------------------------------------------------------
# Dry-run (read-only, cached snapshot, no RB-closed requirement)
# ---------------------------------------------------------------------------

class PayloadRow(NamedTuple):
    content_id: str
    track_name: Optional[str]  # display name for the B10 confirm text
    field: str  # "title" | "artist"
    before: Optional[str]
    after: Optional[str]


class DryRun(NamedTuple):
    fingerprint: tuple
    payload: tuple  # PayloadRow, deterministic order, no no-op rows
    protected_skipped: tuple  # (id, name) of protected tracks with diffs, excluded
    protected_included: tuple  # (id, name) of opted-in protected tracks in payload


def dry_run(db_path: Path, include_protected: frozenset = frozenset()) -> DryRun:
    """READ-ONLY preview. Never opens the DB for write, never requires RB
    closed. ``include_protected`` is a per-call, never-persisted opt-in that
    lists protected track IDs explicitly."""
    snap = get_snapshot(db_path)
    payload, prot_skipped, prot_included = [], [], []
    for cid in sorted(snap.rows):
        row = snap.rows[cid]
        composed = compose_fixes(row.title, row.artist)
        diffs = [
            (field, before, composed[field])
            for field, before in (("title", row.title), ("artist", row.artist))
            if composed[field] != before
        ]
        if not diffs:
            continue  # already conform -> no no-op row
        if row.protected and cid not in include_protected:
            prot_skipped.append((cid, row.title))  # enumerated BY NAME
            continue
        if row.protected:
            prot_included.append((cid, row.title))
        for field, before, after in diffs:
            payload.append(PayloadRow(cid, row.title, field, before, after))
    return DryRun(
        fingerprint=snap.fingerprint,
        payload=tuple(payload),
        protected_skipped=tuple(prot_skipped),
        protected_included=tuple(prot_included),
    )


# ---------------------------------------------------------------------------
# Backup (timestamped, same-second collision suffix; spec 3.1/5.1)
# ---------------------------------------------------------------------------

def make_backup(db_path: Path, backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = backup_root / f"master.db.{stamp}"
    n = 1
    while dest.exists():  # same-second collision -> suffix
        n += 1
        dest = backup_root / f"master.db.{stamp}-{n}"
    dest.mkdir()
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(db_path) + suffix)
        if src.exists():
            shutil.copy2(src, dest / src.name)
    return dest


# ---------------------------------------------------------------------------
# _mutate unit-of-work (spec 3.1) + Smart Fixes entry point (spec 5.11)
# ---------------------------------------------------------------------------

def _mutate(db_path: Path, backup_root: Path, apply_fn,
            expected_fingerprint: Optional[tuple] = None) -> Path:
    # (a) assert RB closed + DB exists
    assert_rb_closed()
    if not db_path.exists():
        raise FileNotFoundError(f"master.db not found: {db_path}")
    # freshness guard at _mutate entry (spec 5.11): same (mtime,size) of
    # master.db(+wal) as the snapshot the dry-run was computed from
    if expected_fingerprint is not None and db_fingerprint(db_path) != expected_fingerprint:
        raise StaleSnapshotError(
            "The Rekordbox database changed since the preview was computed. "
            "Nothing was written. Please run a new dry-run and review it "
            "before applying."
        )
    # (b) timestamped backup
    backup_dir = make_backup(db_path, backup_root)
    # (c) open
    from pyrekordbox.db6 import Rekordbox6Database

    db = Rekordbox6Database(path=db_path, db_dir=db_path.parent, key=KEY, unlock=True)
    try:
        # (d) mutate
        apply_fn(db)
        # (e) commit + invalidate snapshot cache
        db.commit()
        invalidate_snapshot_cache()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return backup_dir


def apply_payload_rows(db, payload) -> None:
    """Write EXACTLY the previewed payload - nothing more, nothing less."""
    import uuid as _uuid

    from pyrekordbox.db6 import tables

    for row in payload:
        content = db.query(tables.DjmdContent).filter_by(ID=row.content_id).one()
        if row.field == "title":
            if (content.Title or None) != row.before:
                raise AssertionError(
                    f"payload contract broken on {row.content_id}: Title is "
                    f"{content.Title!r}, preview said {row.before!r}"
                )
            content.Title = row.after
        elif row.field == "artist":
            current = None
            if content.ArtistID:
                art = db.query(tables.DjmdArtist).filter_by(ID=content.ArtistID).one_or_none()
                current = (art.Name or None) if art is not None else None
            if current != row.before:
                raise AssertionError(
                    f"payload contract broken on {row.content_id}: artist is "
                    f"{current!r}, preview said {row.before!r}"
                )
            artist = db.query(tables.DjmdArtist).filter_by(Name=row.after).first()
            if artist is None:
                artist = tables.DjmdArtist.create(
                    ID=str(db.generate_unused_id(tables.DjmdArtist)),  # string ID (POC #5)
                    Name=row.after,
                    UUID=str(_uuid.uuid4()),
                )
                db.add(artist)
                db.flush()
            content.ArtistID = artist.ID
        else:
            raise AssertionError(f"unknown payload field {row.field!r}")


def smartfix_mutate(db_path: Path, dryrun: DryRun, backup_root: Path) -> Path:
    """The ONLY write path for Smart Fixes - goes through _mutate, applies the
    exact previewed payload, guarded by the dry-run's fingerprint."""
    # internal consistency: protected rows may only appear in the payload if
    # the dry-run listed them as explicitly opted-in
    opted = {cid for cid, _name in dryrun.protected_included}
    snap_rows = get_snapshot(db_path).rows if db_fingerprint(db_path) == dryrun.fingerprint else None

    def apply_fn(db):
        if snap_rows is not None:
            for row in dryrun.payload:
                track = snap_rows.get(row.content_id)
                if track is not None and track.protected and row.content_id not in opted:
                    raise AssertionError(
                        f"protected track {row.content_id} in payload without opt-in"
                    )
        apply_payload_rows(db, dryrun.payload)

    return _mutate(db_path, backup_root, apply_fn,
                   expected_fingerprint=dryrun.fingerprint)
