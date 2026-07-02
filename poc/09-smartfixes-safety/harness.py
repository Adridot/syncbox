"""POC #9 - Smart Fixes (A1) bulk-write safety (SPEC-UNIFIED 5.11, section 8
item 9). Assert-based, disposable. Works EXCLUSIVELY on fresh copies of
poc/testdata under build/.

Run with the sidecar venv python:

    sidecar/.venv/bin/python poc/09-smartfixes-safety/harness.py

Proves the six gate properties:
  (a) dry-run preview == the payload mutate actually writes, EXACTLY
      (full-table diff through an independent sqlcipher connection)
  (b) idempotence: a second dry-run after mutate is empty
  (c) determinism: shuffled input order yields identical composed results
  (d) protected excluded by default; only an explicit, non-persisted,
      by-name opt-in includes them
  (e) freshness guard: DB modified between dry-run and mutate -> ABORT
      with an ask-for-new-dry-run error, nothing written, no backup
  (f) exception mid-mutation -> rollback + re-raise, DB logically
      equivalent to the backup taken at step (b)
Plus unit-of-work mechanics: RB-closed guard inside _mutate only, timestamped
backup with same-second collision suffix, snapshot cache on (mtime,size) of
master.db(+wal) invalidated at commit, read-only dry-run path.
"""

import hashlib
import logging
import random
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import sqlcipher3

POC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(POC_DIR))

import smartfix_core as core  # noqa: E402
from smartfix_core import (  # noqa: E402
    KEY,
    PROTECTED_PATH_MARKER,
    RekordboxRunningError,
    StaleSnapshotError,
    compose_fixes,
    db_fingerprint,
    dry_run,
    make_backup,
    smartfix_mutate,
)

logging.getLogger("pyrekordbox").setLevel(logging.ERROR)

BUILD = POC_DIR / "build"
BACKUPS = BUILD / "backups"
TESTDATA = POC_DIR.parent / "testdata"
TESTDATA_FILES = ("master.db", "master.db-wal", "master.db-shm", "masterPlaylists6.xml")
DB = BUILD / "master.db"

RESULTS: list[str] = []
NOTES: list[str] = []


def ok(msg: str) -> None:
    RESULTS.append(msg)
    print(f"  PASS  {msg}")


def note(msg: str) -> None:
    NOTES.append(msg)
    print(f"  NOTE  {msg}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rw_con(db_path: Path):
    con = sqlcipher3.connect(str(db_path))
    con.execute(f"PRAGMA key = '{KEY}'")
    return con


def ro_con(db_path: Path):
    con = sqlcipher3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.execute(f"PRAGMA key = '{KEY}'")
    return con


def raw_exec(db_path: Path, sql: str, params=()):
    con = rw_con(db_path)
    try:
        con.execute(sql, params)
        con.commit()
    finally:
        con.close()


def dump_fields(db_path: Path) -> dict:
    """ALL djmdContent rows (incl. soft-deleted): id -> (title, artist name).
    Independent read-only sqlcipher connection - the ground truth for (a)/(f).
    '' normalized to None, matching the snapshot normalization."""
    con = ro_con(db_path)
    try:
        return {
            r[0]: (r[1] or None, r[2] or None)
            for r in con.execute(
                "SELECT c.ID, c.Title, a.Name FROM djmdContent c "
                "LEFT JOIN djmdArtist a ON a.ID = c.ArtistID"
            )
        }
    finally:
        con.close()


def raw_counts(db_path: Path) -> dict:
    con = ro_con(db_path)
    try:
        names = [
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        return {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in names}
    finally:
        con.close()


def integrity_ok(db_path: Path) -> bool:
    con = ro_con(db_path)
    try:
        return con.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    finally:
        con.close()


def payload_map(payload) -> dict:
    m = {}
    for r in payload:
        key = (r.content_id, r.field)
        assert key not in m, f"duplicate payload row for {key}"
        m[key] = (r.before, r.after)
    return m


def changed_fields(d0: dict, d1: dict) -> dict:
    assert d0.keys() == d1.keys(), "row set changed"
    out = {}
    for cid in d0:
        (t0, a0), (t1, a1) = d0[cid], d1[cid]
        if t0 != t1:
            out[(cid, "title")] = (t0, t1)
        if a0 != a1:
            out[(cid, "artist")] = (a0, a1)
    return out


# =====================================================================
print("== Phase A: preflight + fresh copies + dirty-data seeding ==")

assert not core._rb_processes(), "ABORT: rekordbox/rekordboxAgent is running"
ok("no rekordbox/rekordboxAgent process running (strict psutil filter)")

orig_hashes = {f: sha256(TESTDATA / f) for f in TESTDATA_FILES}
BUILD.mkdir(exist_ok=True)
if BACKUPS.exists():
    shutil.rmtree(BACKUPS)
for f in TESTDATA_FILES:
    shutil.copy2(TESTDATA / f, BUILD / f)
ok("fresh copies of master.db(+wal/shm) + masterPlaylists6.xml under build/")

# Pick seed rows among active tracks: 6 non-protected + 2 protected (the
# fixture genuinely uses the spec storage layout, so the section 4 path rule
# is exercised on REAL FolderPath values).
con = ro_con(DB)
nonprot_ids = [
    r[0] for r in con.execute(
        "SELECT ID FROM djmdContent WHERE rb_local_deleted = 0 AND "
        "rb_data_status = 256 AND FolderPath NOT LIKE ? "
        "ORDER BY CAST(ID AS INTEGER) LIMIT 6",
        (f"%{PROTECTED_PATH_MARKER}%",),
    )
]
prot_ids = [
    r[0] for r in con.execute(
        "SELECT ID FROM djmdContent WHERE rb_local_deleted = 0 AND "
        "rb_data_status = 256 AND FolderPath LIKE ? "
        "ORDER BY CAST(ID AS INTEGER) LIMIT 2",
        (f"%{PROTECTED_PATH_MARKER}%",),
    )
]
# a known-clean artist to pin on title-only seeds (no artist-field noise)
clean_artist = None
for aid, name in con.execute("SELECT ID, Name FROM djmdArtist WHERE Name IS NOT NULL"):
    c = compose_fixes("x", name)
    if c["artist"] == name:
        clean_artist = (aid, name)
        break
con.close()
assert len(nonprot_ids) == 6 and len(prot_ids) == 2 and clean_artist
S1, S2, S3, S4, S5, S6 = nonprot_ids
P7, P8 = prot_ids

SEEDS = {
    # id: (Title, ArtistID)   ArtistID: keep=..., None=NULL
    S1: ("Cool Track www.slider.kz", clean_artist[0]),
    S2: ("  Second   Track  ", clean_artist[0]),
    S3: ("Paradise Deep  Mix", clean_artist[0]),
    S4: ("DJ Someone - Hidden Gem", None),
    S5: ("DJ Other -  Neat Tune   www.freemp3.example.com", None),
    S6: ("Already Clean Track", clean_artist[0]),
    P7: ("Protected Dirty www.store.example", clean_artist[0]),
    P8: ("P2 -  Protected  Two", None),
}
EXPECT_COMPOSED = {
    S1: {"title": "Cool Track", "artist": clean_artist[1]},
    S2: {"title": "Second Track", "artist": clean_artist[1]},
    S3: {"title": "Paradise Deep Mix", "artist": clean_artist[1]},
    S4: {"title": "Hidden Gem", "artist": "DJ Someone"},
    S5: {"title": "Neat Tune", "artist": "DJ Other"},
    S6: {"title": "Already Clean Track", "artist": clean_artist[1]},  # no-op
    P7: {"title": "Protected Dirty", "artist": clean_artist[1]},
    P8: {"title": "Protected Two", "artist": "P2"},
}
for cid, (title, artist_id) in SEEDS.items():
    raw_exec(DB, "UPDATE djmdContent SET Title = ?, ArtistID = ? WHERE ID = ?",
             (title, artist_id, cid))
ok(f"seeded 8 dirty/clean fixture rows (6 non-protected {nonprot_ids}, "
   f"2 protected {prot_ids}); pinned clean artist {clean_artist[1]!r}")

n_prot = 0
con = ro_con(DB)
n_prot = con.execute(
    "SELECT COUNT(*) FROM djmdContent WHERE rb_local_deleted = 0 AND FolderPath LIKE ?",
    (f"%{PROTECTED_PATH_MARKER}%",),
).fetchone()[0]
con.close()
note(f"fixture uses the spec storage layout for real: {n_prot}/1417 active rows "
     f"match the protected path rule '{PROTECTED_PATH_MARKER}'")

# =====================================================================
print("== Phase B: dry-run - read-only, cached, no RB-closed requirement ==")

# Simulate Rekordbox RUNNING during the whole dry-run phase: dry-run must
# neither care nor call the guard.
real_probe = core._rb_processes
core._rb_processes = lambda: [SimpleNamespace(info={"name": "rekordbox"})]

def fstat(p: Path):
    return (p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None


def wal_logical(p: Path):
    s = fstat(p)
    return None if s is None or s[1] == 0 else s  # absent == empty (no journal)


guard_before = core.GUARD_CALLS
loads_before = core.SNAP_LOADS
db_stat_before = fstat(DB)
wal_before = wal_logical(Path(str(DB) + "-wal"))
fp_before = db_fingerprint(DB)

dr = dry_run(DB)

assert fstat(DB) == db_stat_before, "dry-run touched master.db itself"
assert wal_logical(Path(str(DB) + "-wal")) == wal_before, "dry-run wrote journal content"
assert db_fingerprint(DB) == fp_before == dr.fingerprint, "fingerprint unstable across a read"
assert core.GUARD_CALLS == guard_before, "dry-run called the RB-closed guard"
ok("dry-run ran with a simulated 'rekordbox running' probe active, never "
   "called the RB guard, left master.db byte-stat-untouched, wrote no journal "
   "content, and the normalized (mtime,size) fingerprint is stable across reads")
note("SQLite bookkeeping measured: closing the last rw connection deletes the "
     "-wal; a mode=ro open recreates a 0-byte -wal (+ -shm). The freshness "
     "fingerprint therefore normalizes 'wal absent' == 'wal empty' and ignores "
     "the empty wal's mtime - build-phase requirement for section 4 / 5.11")

# read-only enforcement is at the SQLite level (probe also asserted this)
try:
    c = ro_con(DB)
    c.execute("UPDATE djmdContent SET Title = Title WHERE 1=0")
    raise AssertionError("mode=ro connection accepted a write")
except sqlcipher3.OperationalError:
    c.close()
ok("snapshot connection is mode=ro at the SQLite level: writes refused "
   "('attempt to write a readonly database')")

dr_again = dry_run(DB)
assert core.SNAP_LOADS == loads_before + 1, "snapshot not cached on (mtime,size)"
assert dr_again == dr
ok("snapshot cached on (mtime,size) of master.db(+wal): second dry-run hit "
   "the cache (1 load) and returned an identical result")

core._rb_processes = real_probe  # restore the real probe

pm = payload_map(dr.payload)
for cid, exp in EXPECT_COMPOSED.items():
    if cid in (P7, P8):
        continue  # protected: checked below
    seeded_title = SEEDS[cid][0]
    seeded_artist = clean_artist[1] if SEEDS[cid][1] else None
    for field, before in (("title", seeded_title), ("artist", seeded_artist)):
        key = (cid, field)
        if exp[field] != before:
            assert pm.get(key) == (before, exp[field]), (key, pm.get(key), exp[field])
        else:
            assert key not in pm, f"no-op row emitted for {key}"
ok("payload matches the expected composed results exactly for all 6 "
   "non-protected seeds (multi-fix composition on S5: URL strip + artist "
   "extraction + whitespace collapse -> one final result per field)")
assert (S6, "title") not in pm and (S6, "artist") not in pm
assert all(before != after for (before, after) in pm.values())
ok("already-conform fields produce NO no-op rows (clean seed absent; every "
   f"payload row has before != after; payload = {len(dr.payload)} field "
   f"changes on {len({r.content_id for r in dr.payload})} tracks)")

prot_skipped_ids = {cid for cid, _ in dr.protected_skipped}
assert P7 in prot_skipped_ids and P8 in prot_skipped_ids
assert not any(cid in (P7, P8) for cid, _f in pm)
assert all(cid not in {r.content_id for r in dr.payload} for cid in prot_skipped_ids)
names = dict(dr.protected_skipped)
assert names[P7] == SEEDS[P7][0] and names[P8] == SEEDS[P8][0]
assert dr.protected_included == ()
ok(f"(d) protected EXCLUDED by default: {len(dr.protected_skipped)} protected "
   "track(s) with pending diffs skipped and enumerated BY NAME "
   f"(incl. {names[P7]!r}, {names[P8]!r}); none in the payload")

# =====================================================================
print("== Phase C: (c) determinism - shuffled input order, stable compose ==")

snap = core.get_snapshot(DB)
ref = {cid: compose_fixes(r.title, r.artist) for cid, r in snap.rows.items()}
for seed in range(5):
    items = list(snap.rows.items())
    random.Random(seed).shuffle(items)
    shuffled = {cid: compose_fixes(r.title, r.artist) for cid, r in items}
    assert shuffled == ref, f"shuffle seed {seed} diverged"
ok(f"5 shuffled passes over all {len(snap.rows)} snapshot rows yield "
   "identical composed results per track")

for cid, r in snap.rows.items():
    once = compose_fixes(r.title, r.artist)
    twice = compose_fixes(once["title"], once["artist"])
    assert twice == once, f"catalog not idempotent on {cid}: {r} -> {once} -> {twice}"
ok("catalog is a fixpoint on REAL data: compose(compose(x)) == compose(x) "
   f"for all {len(snap.rows)} rows (incl. the fixture's genuine dirty titles)")

core.invalidate_snapshot_cache()
dr_reload = dry_run(DB)
assert dr_reload == dr
ok("dry-run re-computed from a fresh disk read (cache invalidated) is "
   "byte-identical to the cached one")

# =====================================================================
print("== Phase D: (e) freshness guard - external write between dry-run and mutate ==")

EXTERNAL_ROW = None
con = ro_con(DB)
EXTERNAL_ROW = con.execute(
    "SELECT ID FROM djmdContent WHERE rb_local_deleted = 0 AND rb_data_status = 256 "
    "AND FolderPath NOT LIKE ? AND ID NOT IN ({}) ORDER BY CAST(ID AS INTEGER) DESC LIMIT 1"
    .format(",".join("?" * len(SEEDS))),
    (f"%{PROTECTED_PATH_MARKER}%", *SEEDS.keys()),
).fetchone()[0]
con.close()

dr_stale = dry_run(DB)
raw_exec(DB, "UPDATE djmdContent SET Title = ? WHERE ID = ?",
         ("Externally Renamed", EXTERNAL_ROW))  # simulates RB writing meanwhile
assert db_fingerprint(DB) != dr_stale.fingerprint
d_before = dump_fields(DB)
backups_before = sorted(BACKUPS.glob("*")) if BACKUPS.exists() else []
try:
    smartfix_mutate(DB, dr_stale, BACKUPS)
    raise AssertionError("stale mutate did not abort")
except StaleSnapshotError as e:
    msg = str(e)
assert "dry-run" in msg and "Nothing was written" in msg
backups_after = sorted(BACKUPS.glob("*")) if BACKUPS.exists() else []
assert backups_after == backups_before, "stale abort still created a backup"
assert dump_fields(DB) == d_before, "stale abort wrote something"
ok("(e) freshness guard: external write between dry-run and mutate -> "
   f"ABORT with StaleSnapshotError ({msg!r}), no backup, no write")

# RB-running guard inside _mutate (and friendliness of the message)
core._rb_processes = lambda: [SimpleNamespace(info={"name": "rekordbox"})]
dr_fresh = dry_run(DB)  # fresh preview (dry-run still fine with RB 'running')
try:
    smartfix_mutate(DB, dr_fresh, BACKUPS)
    raise AssertionError("mutate did not abort with RB running")
except RekordboxRunningError as e:
    rb_msg = str(e)
finally:
    core._rb_processes = real_probe
assert "PID" not in rb_msg and "/Applications/" not in rb_msg and "--type=" not in rb_msg
assert (sorted(BACKUPS.glob("*")) if BACKUPS.exists() else []) == backups_before
assert dump_fields(DB) == d_before
ok("(unit-of-work a) RB-running probe at _mutate entry -> abort BEFORE backup "
   f"and open; friendly message ({rb_msg!r}) has no PID, no /Applications/ "
   "path, no --type= flag")

# =====================================================================
print("== Phase E: (a) mutate writes EXACTLY the previewed payload ==")

assert dr_fresh.fingerprint == db_fingerprint(DB)
d0 = dump_fields(DB)
counts0 = raw_counts(DB)
artist_names0 = None
con = ro_con(DB)
artist_names0 = {r[0] for r in con.execute("SELECT Name FROM djmdArtist")}
con.close()

guard_before = core.GUARD_CALLS
backup1 = smartfix_mutate(DB, dr_fresh, BACKUPS)
assert core.GUARD_CALLS == guard_before + 1, "_mutate did not run the RB guard"
assert backup1.is_dir() and (backup1 / "master.db").exists()
captured = sorted(p.name for p in backup1.iterdir())
ok(f"(unit-of-work b/c/d/e) mutate committed through _mutate; RB guard ran; "
   f"timestamped backup {backup1.name} captured {captured}")

assert dump_fields(backup1 / "master.db") == d0
ok("backup is pre-mutation state: full field dump of the backup DB == dump "
   "taken just before mutate")

d1 = dump_fields(DB)
diff = changed_fields(d0, d1)
assert diff == payload_map(dr_fresh.payload), (
    f"written != previewed: extra={set(diff) - set(payload_map(dr_fresh.payload))} "
    f"missing={set(payload_map(dr_fresh.payload)) - set(diff)}"
)
ok(f"(a) EXACT: on-disk diff across ALL {len(d1)} djmdContent rows "
   f"(incl. soft-deleted) == the previewed payload, field by field "
   f"({len(diff)} field writes, not one more, not one less)")

new_names = {r.after for r in dr_fresh.payload if r.field == "artist"} - artist_names0
counts1 = raw_counts(DB)
deltas = {t: counts1[t] - counts0[t] for t in counts0 if counts1[t] != counts0[t]}
assert deltas == ({"djmdArtist": len(new_names)} if new_names else {}), deltas
assert integrity_ok(DB)
ok(f"non-regression: table deltas == {{djmdArtist: +{len(new_names)}}} "
   f"(find-or-create for extracted artists {sorted(new_names)}), all other "
   "tables untouched; PRAGMA integrity_check == ok")

assert core._SNAP_CACHE == {}
loads = core.SNAP_LOADS
dr_post = dry_run(DB)
assert core.SNAP_LOADS == loads + 1
ok("(unit-of-work e) snapshot cache invalidated at commit: next dry-run "
   "re-read from disk")

# =====================================================================
print("== Phase F: (b) idempotence - second dry-run after mutate is empty ==")

assert dr_post.payload == (), f"second dry-run not empty: {dr_post.payload[:5]}"
assert {cid for cid, _ in dr_post.protected_skipped} == prot_skipped_ids
ok("(b) second dry-run after mutate: payload EMPTY (re-run = no-op); the "
   "untouched protected tracks still enumerated as skipped")

# =====================================================================
print("== Phase G: (d) opt-in - explicit, by-name, never persisted ==")

dr_p7 = dry_run(DB, include_protected=frozenset({P7}))
pm7 = payload_map(dr_p7.payload)
assert set(pm7) == {(P7, "title")}
assert pm7[(P7, "title")] == (SEEDS[P7][0], EXPECT_COMPOSED[P7]["title"])
assert dict(dr_p7.protected_included) == {P7: SEEDS[P7][0]}
assert P8 in {cid for cid, _ in dr_p7.protected_skipped}
ok(f"opt-in dry-run for {P7} only: payload = exactly its title fix; the "
   "opted-in track is listed by name for the confirm text; the OTHER "
   "protected track stays skipped")

backup2 = smartfix_mutate(DB, dr_p7, BACKUPS)
d2 = dump_fields(DB)
assert d2[P7][0] == EXPECT_COMPOSED[P7]["title"]
assert d2[P8][0] == SEEDS[P8][0], "non-opted-in protected row was mutated"
ok(f"opt-in mutate fixed ONLY {P7}; {P8} untouched")

# opt-in is per-call state: the NEXT default dry-run must exclude protected
# again (if the opt-in were persisted, P8 would now be in the payload)
dr_default = dry_run(DB)
assert dr_default.payload == ()
assert {cid for cid, _ in dr_default.protected_skipped} >= {P8}
assert P7 not in {cid for cid, _ in dr_default.protected_skipped}
ok("(d) opt-in NOT persisted: next default dry-run excludes protected again "
   f"({P8} back in the skipped list, empty payload)")

remaining = frozenset(cid for cid, _ in dr_default.protected_skipped)
dr_rest = dry_run(DB, include_protected=remaining)
assert {cid for cid, _n in dr_rest.protected_included} == remaining
backup3 = smartfix_mutate(DB, dr_rest, BACKUPS)
dr_final = dry_run(DB, include_protected=remaining)
assert dr_final.payload == () and dr_final.protected_skipped == ()
d3 = dump_fields(DB)
assert d3[P8] == (EXPECT_COMPOSED[P8]["title"], EXPECT_COMPOSED[P8]["artist"])
ok(f"remaining {len(remaining)} protected track(s) fixed via explicit opt-in; "
   "final dry-run (even WITH opt-in) is completely empty - full-collection "
   "idempotence incl. protected")

# =====================================================================
print("== Phase H: same-second backup collision suffix ==")

# land both backups inside the same wall-clock second
while True:
    t0 = time.time()
    if t0 % 1 < 0.35:
        break
    time.sleep(0.02)
b_a = make_backup(DB, BACKUPS)
b_b = make_backup(DB, BACKUPS)
assert b_a != b_b and b_a.exists() and b_b.exists()
stamp_a = b_a.name.split("master.db.")[1][:15]
stamp_b = b_b.name.split("master.db.")[1][:15]
assert stamp_a == stamp_b, f"crossed a second boundary: {b_a.name} / {b_b.name}"
assert b_b.name == f"{b_a.name}-2"
ok(f"same-second backup collision -> suffix: {b_a.name} then {b_b.name}")

# =====================================================================
print("== Phase I: (f) exception mid-mutation -> rollback == backup ==")

raw_exec(DB, "UPDATE djmdContent SET Title = ? WHERE ID = ?",
         ("Crash  Test   www.crash.example", EXTERNAL_ROW))
dr_crash = dry_run(DB)
assert (EXTERNAL_ROW, "title") in payload_map(dr_crash.payload)

d_pre = dump_fields(DB)
counts_pre = raw_counts(DB)
backups_before = set(BACKUPS.glob("*"))


class MidMutationBoom(RuntimeError):
    pass


def crashing_apply(db):
    core.apply_payload_rows(db, dr_crash.payload)  # real pending writes
    db.flush()
    raise MidMutationBoom("simulated crash after the payload was applied")


try:
    core._mutate(DB, BACKUPS, crashing_apply, expected_fingerprint=dr_crash.fingerprint)
    raise AssertionError("crashing mutate did not raise")
except MidMutationBoom:
    pass  # (f) re-raised with the original exception type
crash_backup = (set(BACKUPS.glob("*")) - backups_before).pop()

assert dump_fields(DB) == d_pre, "rollback left changes behind"
assert dump_fields(DB) == dump_fields(crash_backup / "master.db")
assert raw_counts(DB) == counts_pre
assert integrity_ok(DB)
ok("(f) exception AFTER the payload was applied+flushed -> rollback + "
   "re-raise (original exception type); full field dump and row counts "
   f"identical to pre-mutate state AND to the step-(b) backup "
   f"{crash_backup.name}; integrity ok")

# recovery: the crashed attempt invalidated nothing on disk; a fresh
# dry-run + mutate completes normally
dr_recover = dry_run(DB)
assert payload_map(dr_recover.payload)[(EXTERNAL_ROW, "title")] == (
    "Crash  Test   www.crash.example", "Crash Test")
smartfix_mutate(DB, dr_recover, BACKUPS)
assert dry_run(DB).payload == ()
assert dump_fields(DB)[EXTERNAL_ROW][0] == "Crash Test"
ok("recovery after the crash: fresh dry-run -> mutate -> clean, idempotent")

# =====================================================================
print("== Phase J: originals untouched + summary ==")

for f in TESTDATA_FILES:
    assert sha256(TESTDATA / f) == orig_hashes[f], f"testdata original touched: {f}"
ok("poc/testdata originals byte-identical (sha256) - never touched")

print(f"\n{len(RESULTS)} assertions passed, {len(NOTES)} notes")
for n in NOTES:
    print(f"NOTE: {n}")
print("POC9 HARNESS: ALL PASS")
sys.exit(0)
