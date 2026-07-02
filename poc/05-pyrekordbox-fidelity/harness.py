"""POC #5 - pyrekordbox write fidelity on a real Rekordbox 7.x master.db.

Assert-based, disposable harness. Works EXCLUSIVELY on fresh copies under build/.
Run with the sidecar venv python:

    sidecar/.venv/bin/python poc/05-pyrekordbox-fidelity/harness.py

Load-bearing mechanics verified (SPEC-UNIFIED 5.7 / 11.3, SPEC-01 sections 1.1,
1.6, 1.7):
  1. Open the SQLCipher DB with the public constant key (pyrekordbox-managed).
  2. Read DjmdContent readout fields (KeyID->ScaleName, DJPlayCount, StockDate,
     GenreID->DjmdGenre, BitRate, cues, playlists).
  3. MyTag under the "Situation" category + smart playlist, operator 8, IDs
     > 2^31 written as SIGNED 32-bit in the SmartList payload.
  4. New content/artist/playlist rows with STRING IDs (mixed int+str PK crash).
  5. Soft-delete tuple (1, 0, 258, 0) then reactivate (256, 0); reads filter.
  6. masterPlaylists6.xml snapshot before mutation, byte-identical restore.
  7. Non-regression: PRAGMA integrity_check + row counts of untouched tables.
"""

import hashlib
import re
import secrets
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path

import psutil

POC_DIR = Path(__file__).resolve().parent
BUILD = POC_DIR / "build"
TESTDATA = POC_DIR.parent / "testdata"
KEY = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497"
TESTDATA_FILES = ("master.db", "master.db-wal", "master.db-shm", "masterPlaylists6.xml")

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


def signed32(x: int) -> int:
    """Spec conversion (SPEC-01 1.7): IDs > 2^31 written as signed 32-bit."""
    return x - 2**32 if x >= 2**31 else x


# =====================================================================
print("== Phase A: preflight ==")

# Strict Rekordbox process guard (SPEC-UNIFIED 5.1 pattern, macOS names)
rb_procs = []
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
        rb_procs.append(p)
assert not rb_procs, f"ABORT: Rekordbox running: {[p.info['name'] for p in rb_procs]}"
ok("no rekordbox/rekordboxAgent process running (psutil strict filter)")

orig_hashes = {f: sha256(TESTDATA / f) for f in TESTDATA_FILES}
BUILD.mkdir(exist_ok=True)
for f in TESTDATA_FILES:
    shutil.copy2(TESTDATA / f, BUILD / f)
ok("fresh copies of master.db(+wal/shm) and masterPlaylists6.xml under build/")

DB = BUILD / "master.db"
XML = BUILD / "masterPlaylists6.xml"
xml_snapshot = XML.read_bytes()  # step 6 snapshot BEFORE any mutation
xml_snapshot_sha = hashlib.sha256(xml_snapshot).hexdigest()

# Baseline row counts through a raw sqlcipher connection on the pristine copy
import sqlcipher3  # noqa: E402  (ships with sqlcipher3-wheels)


def raw_counts(db_path: Path) -> dict[str, int]:
    con = sqlcipher3.connect(str(db_path))
    try:
        con.execute(f"PRAGMA key = '{KEY}'")
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


baseline = raw_counts(DB)
assert baseline["djmdContent"] == 8107, baseline["djmdContent"]
ok(f"baseline row counts captured through sqlcipher ({len(baseline)} tables, "
   f"djmdContent={baseline['djmdContent']})")

# =====================================================================
print("== Phase B: open with pyrekordbox (key is a public constant) ==")

from pyrekordbox.db6 import Rekordbox6Database, tables  # noqa: E402
from pyrekordbox.db6.database import BLOB  # noqa: E402
from pyrekordbox.db6.smartlist import LogicalOperator, Operator, SmartList  # noqa: E402
from pyrekordbox.utils import deobfuscate  # noqa: E402

assert deobfuscate(BLOB) == KEY
ok("pyrekordbox 0.4.4 embeds the key (deobfuscate(BLOB) == public constant); "
   "no download-key call needed")

db = Rekordbox6Database(path=DB, db_dir=BUILD, key=KEY, unlock=True)
ok("Rekordbox6Database opened the encrypted RB 7.x master.db copy")

# =====================================================================
print("== Phase C: DjmdContent reads incl. 11.3 readout fields ==")

DjmdContent = tables.DjmdContent


def active_contents():
    """Syncbox read invariant: all reads filter soft-deleted rows."""
    return db.query(DjmdContent).filter(DjmdContent.rb_local_deleted == 0)


total = db.query(DjmdContent).count()
active = active_contents().count()
assert total == 8107 and 0 < active < total
ok(f"djmdContent: {total} rows, {active} active after soft-delete read filter")

sample = (
    db.query(DjmdContent)
    .join(tables.DjmdCue, tables.DjmdCue.ContentID == DjmdContent.ID)
    .filter(
        DjmdContent.rb_local_deleted == 0,
        DjmdContent.rb_data_status == 256,
        DjmdContent.KeyID.isnot(None),
        DjmdContent.GenreID.isnot(None),
        DjmdContent.BitRate > 0,
        DjmdContent.DJPlayCount.isnot(None),
        DjmdContent.StockDate.isnot(None),
    )
    .first()
)
assert sample is not None, "no active content row with all 11.3 readout fields"
assert isinstance(sample.ID, str), type(sample.ID)

key_row = db.query(tables.DjmdKey).filter_by(ID=sample.KeyID).one()
genre_row = db.query(tables.DjmdGenre).filter_by(ID=sample.GenreID).one()
assert key_row.ScaleName, "KeyID did not resolve to a DjmdKey.ScaleName"
assert genre_row.Name, "GenreID did not resolve to a DjmdGenre.Name"
cue_count = db.query(tables.DjmdCue).filter_by(ContentID=sample.ID).count()
assert cue_count > 0
pl_count = db.query(tables.DjmdPlaylist).count()
song_pl_count = db.query(tables.DjmdSongPlaylist).count()
assert pl_count > 0 and song_pl_count > 0
ok(
    f"11.3 readout fields on real row ID={sample.ID!r} ({sample.Title!r}): "
    f"KeyID={sample.KeyID!r}->ScaleName={key_row.ScaleName!r}, "
    f"DJPlayCount={sample.DJPlayCount!r}, StockDate={sample.StockDate!r}, "
    f"GenreID={sample.GenreID!r}->Genre={genre_row.Name!r}, BitRate={sample.BitRate}, "
    f"cues={cue_count}, playlists={pl_count}, songPlaylist rows={song_pl_count}"
)
note(f"DJPlayCount read back as {type(sample.DJPlayCount).__name__} "
     "(pyrekordbox maps it as VARCHAR; NULL/0 semantics for 'never played' hold)")

usn_start = db.get_local_usn()

# =====================================================================
print("== Phase D: mutations (MyTag, smart playlists, string-ID rows, soft-delete) ==")

# The spec's own worked example must hold, and it must match what Rekordbox
# itself wrote into this real database.
assert signed32(2662450573) == -1632516723
pop_dance_pl = db.query(tables.DjmdPlaylist).filter_by(ID="678704696").one()
assert 'ValueLeft="-1632516723"' in pop_dance_pl.SmartList
pop_dance_tag = db.query(tables.DjmdMyTag).filter_by(ID="2662450573").one()
assert pop_dance_tag.Name == "Pop Dance"
big_smart = db.query(tables.DjmdPlaylist).filter_by(ID="3644759451").one()
assert f'Id="{signed32(3644759451)}"' in big_smart.SmartList  # -650207845
small_smart = db.query(tables.DjmdPlaylist).filter_by(ID="1248102774").one()
assert 'Id="1248102774"' in small_smart.SmartList  # < 2^31 stays positive
ok("real RB 7.x rows confirm the exact spec conversion: tag 2662450573 stored as "
   "ValueLeft=\"-1632516723\"; playlist 3644759451 stored as Id=\"-650207845\"; "
   "IDs < 2^31 stay positive")


def gen_big_string_id(table) -> str:
    """Unused table ID chosen in (2^31, 2^32) to exercise the signed-32 path."""
    for _ in range(100000):
        cand = 2**31 + secrets.randbelow(2**31)
        exists = db.query(db.query(table).filter_by(ID=str(cand)).exists()).scalar()
        if not exists:
            return str(cand)
    raise RuntimeError("no unused id found")


now = datetime.now()

# --- 3a. MyTag under the Situation category -------------------------------
situation = db.query(tables.DjmdMyTag).filter_by(Name="Situation", ParentID="root").one()
assert situation.ID == "3" and situation.Attribute == 1
max_seq = max(
    (t.Seq or 0)
    for t in db.query(tables.DjmdMyTag).filter_by(ParentID=situation.ID).all()
)
tag_id = gen_big_string_id(tables.DjmdMyTag)
assert int(tag_id) > 2**31
mytag = tables.DjmdMyTag.create(
    ID=tag_id,
    Seq=max_seq + 1,
    Name="POC5 Event Situation",
    Attribute=0,
    ParentID=situation.ID,
    UUID=str(uuid.uuid4()),
    rb_data_status=256,
    rb_local_data_status=0,
    rb_local_deleted=0,
    rb_local_synced=0,
)
db.add(mytag)
db.flush()
ok(f"MyTag {tag_id!r} (string ID > 2^31) created under Situation category (ID='3')")

# Tag the sample content with the new MyTag (needed for the smartlist query check)
song_tag = tables.DjmdSongMyTag.create(
    ID=str(db.generate_unused_id(tables.DjmdSongMyTag)),
    MyTagID=tag_id,
    ContentID=sample.ID,
    TrackNo=1,
    UUID=str(uuid.uuid4()),
)
db.add(song_tag)
db.flush()
ok(f"djmdSongMyTag row links content {sample.ID!r} to the new MyTag")

# --- 3b. Smart playlist, native pyrekordbox path --------------------------
sl_native = SmartList(logical_operator=LogicalOperator.ALL, auto_update=0)
sl_native.add_condition("myTag", Operator.CONTAINS, str(signed32(int(tag_id))))
assert int(Operator.CONTAINS) == 8
pl_native = db.create_smart_playlist("POC5 Smart Native", sl_native)
assert isinstance(pl_native.ID, str)
assert f'ValueLeft="{signed32(int(tag_id))}"' in pl_native.SmartList
assert 'Operator="8"' in pl_native.SmartList
ok(f"create_smart_playlist wrote operator 8 + signed tag ID "
   f"{signed32(int(tag_id))} for MyTag {tag_id!r}")

# Residual quirk check: pyrekordbox to_xml() applies the -2^32 shift
# unconditionally, so the auto-generated 28-bit playlist ID lands outside the
# signed 32-bit range (real RB rows keep IDs < 2^31 positive).
m = re.search(r'Id="(-?\d+)"', pl_native.SmartList)
native_node_id = int(m.group(1))
if native_node_id != signed32(int(pl_native.ID)):
    note(
        "residual pyrekordbox #110-family quirk CONFIRMED: SmartList.to_xml() "
        f"bitshifts unconditionally -> native path wrote NODE Id={native_node_id} "
        f"for playlist {pl_native.ID!r} (out of signed-32 range; real RB keeps "
        "IDs < 2^31 positive). Syncbox must own the NODE Id conversion."
    )
    # Syncbox-side fix: rewrite payload with the spec-conformant conditional shift
    fixed = pl_native.SmartList.replace(
        f'Id="{native_node_id}"', f'Id="{signed32(int(pl_native.ID))}"'
    )
    pl_native.SmartList = fixed
assert f'Id="{signed32(int(pl_native.ID))}"' in pl_native.SmartList
ok("native smart playlist payload normalized to the spec-conformant NODE Id")

# --- 3c. Smart playlist with forced ID > 2^31 (spec-exact path) -----------
pl_big_id = gen_big_string_id(tables.DjmdPlaylist)
sl_big = SmartList(logical_operator=LogicalOperator.ALL, auto_update=0)
sl_big.playlist_id = pl_big_id
sl_big.add_condition("myTag", Operator.CONTAINS, str(signed32(int(tag_id))))
payload = sl_big.to_xml()
assert f'Id="{signed32(int(pl_big_id))}"' in payload
assert f'ValueLeft="{signed32(int(tag_id))}"' in payload
assert 'Operator="8"' in payload
# Same structural format as a row written by Rekordbox itself
rb_shape = re.sub(r'"[^"]*"', '"..."', pop_dance_pl.SmartList)
poc_shape = re.sub(r'"[^"]*"', '"..."', payload)
assert rb_shape == poc_shape, f"{rb_shape} != {poc_shape}"
seq_root = db.get_playlist(ParentID="root").count() + 1
pl_manual = tables.DjmdPlaylist.create(
    ID=pl_big_id,
    Seq=seq_root,
    Name="POC5 Smart BigID",
    Attribute=4,
    ParentID="root",
    SmartList=payload,
    UUID=str(uuid.uuid4()),
    created_at=now,
    updated_at=now,
)
db.add(pl_manual)
db.playlist_xml.add(pl_big_id, "root", 4, now)
db.flush()
ok(
    f"smart playlist {pl_big_id!r} (> 2^31) written with SIGNED payload "
    f"Id=\"{signed32(int(pl_big_id))}\"; XML structure byte-shape-identical to "
    "the RB-written 'Pop / Dance' row"
)

# Round-trip: parse + filter_clause resolve back to the tagged content
sl_check = SmartList()
sl_check.parse(payload)
assert sl_check.playlist_id == pl_big_id  # right_bitshift back to unsigned
hits = db.query(DjmdContent).filter(sl_check.filter_clause()).all()
assert [c.ID for c in hits] == [sample.ID]
ok("SmartList payload round-trips (parse -> unsigned IDs) and filter_clause "
   f"resolves exactly the tagged content {sample.ID!r}")

# --- 4. New rows with STRING IDs ------------------------------------------
artist_id = gen_big_string_id(tables.DjmdArtist)
artist = tables.DjmdArtist.create(
    ID=artist_id, Name="POC5 Artist", SearchStr=None, UUID=str(uuid.uuid4())
)
db.add(artist)
db.flush()

content_id = gen_big_string_id(tables.DjmdContent)
fake_path = f"/Users/poc5/inbox/POC5 Artist - POC5 Track {content_id}.mp3"
device = db.get_device().first()
new_content = tables.DjmdContent.create(
    ID=content_id,
    MasterSongID=content_id,
    rb_file_id=content_id,  # SPEC-01 1.6: ID = MasterSongID = rb_file_id
    UUID=str(uuid.uuid4()),
    Title="POC5 Track",
    ArtistID=artist_id,
    FolderPath=fake_path,
    FileNameL=Path(fake_path).name,
    FileType=int(tables.FileType.MP3),
    FileSize=1024,
    BitRate=320,
    DeviceID=device.ID if device else None,
    MasterDBID=device.MasterDBID if device else None,
    StockDate=now.strftime("%Y-%m-%d"),
    DateCreated=now.strftime("%Y-%m-%d"),
    HotCueAutoLoad="on",
    rb_data_status=0,
    rb_local_deleted=0,
    rb_local_synced=0,
)
db.add(new_content)
db.flush()

pl_plain = db.create_playlist("POC5 Plain Playlist")
assert isinstance(pl_plain.ID, str)
song_row = db.add_to_playlist(pl_plain, new_content)
assert isinstance(song_row.ID, str)
ok(
    f"string-ID rows flushed cleanly: artist {artist_id!r}, content "
    f"{content_id!r} (ID=MasterSongID=rb_file_id), playlist {pl_plain.ID!r} "
    f"+ song row"
)

# --- 5. Soft-delete tuple, then reactivation ------------------------------
target = (
    db.query(DjmdContent)
    .filter(
        DjmdContent.rb_local_deleted == 0,
        DjmdContent.rb_data_status == 256,
        DjmdContent.ID != sample.ID,
    )
    .first()
)
target_id = target.ID
target.rb_local_deleted = 1
target.rb_local_synced = 0
target.rb_data_status = 258
target.rb_local_data_status = 0

db.commit()  # commit #1 (also autoincrements USNs and rewrites the XML)
ok("commit #1 succeeded (MyTag + 3 playlists + artist + content + soft-delete)")

# Verify the exact tuple through an independent sqlcipher connection
con = sqlcipher3.connect(str(DB))
con.execute(f"PRAGMA key = '{KEY}'")
row = con.execute(
    "SELECT rb_local_deleted, rb_local_synced, rb_data_status, rb_local_data_status "
    "FROM djmdContent WHERE ID = ?",
    (target_id,),
).fetchone()
con.close()
assert row == (1, 0, 258, 0), row
ok(f"soft-delete tuple on {target_id!r} verified on disk: "
   "(rb_local_deleted, rb_local_synced, rb_data_status, rb_local_data_status) "
   "= (1, 0, 258, 0)")

assert active_contents().filter(DjmdContent.ID == target_id).count() == 0
ok("read filter excludes the soft-deleted row")
note("pyrekordbox's own get_content() does NOT filter soft-deleted rows - the "
     "read filter is a Syncbox-side invariant (as specified)")

# Reactivate
target = db.query(DjmdContent).filter_by(ID=target_id).one()
target.rb_data_status = 256
target.rb_local_deleted = 0
db.commit()  # commit #2

con = sqlcipher3.connect(str(DB))
con.execute(f"PRAGMA key = '{KEY}'")
row = con.execute(
    "SELECT rb_local_deleted, rb_local_synced, rb_data_status, rb_local_data_status "
    "FROM djmdContent WHERE ID = ?",
    (target_id,),
).fetchone()
con.close()
assert row == (0, 0, 256, 0), row
assert active_contents().filter(DjmdContent.ID == target_id).count() == 1
ok(f"reactivation verified: rb_data_status=256, rb_local_deleted=0; row visible again")

usn_end = db.get_local_usn()
assert usn_end > usn_start
ok(f"local USN advanced {usn_start} -> {usn_end} (AgentRegistry updated, no new row)")

db.close()

# =====================================================================
print("== Phase E: mixed int+string PK crash demonstration ==")

db2 = Rekordbox6Database(path=DB, db_dir=BUILD, key=KEY, unlock=True)
crashed = None
try:
    a_int = tables.DjmdArtist.create(
        ID=db2.generate_unused_id(tables.DjmdArtist),  # int ID (pyrekordbox default!)
        Name="POC5 Crash Int",
        UUID=str(uuid.uuid4()),
    )
    a_str = tables.DjmdArtist.create(
        ID=str(db2.generate_unused_id(tables.DjmdArtist)),  # string ID (spec path)
        Name="POC5 Crash Str",
        UUID=str(uuid.uuid4()),
    )
    db2.add(a_int)
    db2.add(a_str)
    db2.flush()
except TypeError as exc:
    crashed = exc
finally:
    db2.rollback()
if crashed is not None:
    ok(f"mixed int+string PK flush crash REPRODUCED: TypeError: {crashed}")
else:
    note("mixed int+string PK flush did not raise on this SQLAlchemy version; "
         "string-ID path remains the only safe, spec-mandated path")
db2.close()

# =====================================================================
print("== Phase F: masterPlaylists6.xml snapshot/restore ==")

xml_after = XML.read_bytes()
assert hashlib.sha256(xml_after).hexdigest() != xml_snapshot_sha, (
    "commit did not rewrite masterPlaylists6.xml - snapshot/restore untestable"
)
for pid in (pl_native.ID, pl_big_id, pl_plain.ID):
    assert f"{int(pid):X}".encode() in xml_after
ok("pyrekordbox rewrote masterPlaylists6.xml at commit (3 new hex playlist IDs "
   "present) - confirms the spec's snapshot/restore requirement")

XML.write_bytes(xml_snapshot)
assert sha256(XML) == xml_snapshot_sha
ok("masterPlaylists6.xml restored byte-identical to the pre-mutation snapshot")

# =====================================================================
print("== Phase G: non-regression (re-open, integrity, row counts) ==")

# Re-open the mutated DB with pyrekordbox (fresh session) and re-read
db3 = Rekordbox6Database(path=DB, db_dir=BUILD, key=KEY, unlock=True)
assert db3.query(DjmdContent).filter_by(ID=content_id).one().Title == "POC5 Track"
assert db3.query(tables.DjmdMyTag).filter_by(ID=tag_id).one().Name == "POC5 Event Situation"
stored_payload = db3.query(tables.DjmdPlaylist).filter_by(ID=pl_big_id).one().SmartList
assert f'Id="{signed32(int(pl_big_id))}"' in stored_payload
assert f'ValueLeft="{signed32(int(tag_id))}"' in stored_payload
db3.close()
ok("DB re-opened after all mutations; new rows and signed SmartList payload persisted")

con = sqlcipher3.connect(str(DB))
con.execute(f"PRAGMA key = '{KEY}'")
integrity = con.execute("PRAGMA integrity_check").fetchall()
con.close()
assert integrity == [("ok",)], integrity
ok("PRAGMA integrity_check == ok (through sqlcipher)")

after = raw_counts(DB)
expected_delta = {
    "djmdMyTag": 1,
    "djmdSongMyTag": 1,
    "djmdPlaylist": 3,
    "djmdSongPlaylist": 1,
    "djmdArtist": 1,
    "djmdContent": 1,
}
diffs = {}
for t in sorted(set(baseline) | set(after)):
    d = after.get(t, 0) - baseline.get(t, 0)
    if d:
        diffs[t] = d
assert diffs == expected_delta, f"unexpected table deltas: {diffs}"
untouched = [t for t in baseline if t not in expected_delta]
ok(f"row counts: exactly the expected deltas {expected_delta}; "
   f"{len(untouched)} other tables unchanged (incl. agentRegistry, uuidIDMap, "
   "djmdCue, contentCue, djmdSongHistory)")

for f in TESTDATA_FILES:
    assert sha256(TESTDATA / f) == orig_hashes[f], f"testdata original touched: {f}"
ok("poc/testdata originals byte-identical (sha256) - never touched")

# =====================================================================
print(f"\n{len(RESULTS)} assertions passed, {len(NOTES)} notes")
for n in NOTES:
    print(f"NOTE: {n}")
print("POC5 HARNESS: ALL PASS")
sys.exit(0)
