"""POC #5 exploration (read-only, on a fresh copy): inspect real DB shape before
writing the harness. Disposable."""

import shutil
import sys
from pathlib import Path

import psutil

POC_DIR = Path(__file__).resolve().parent
BUILD = POC_DIR / "build"
TESTDATA = POC_DIR.parent / "testdata"

# --- Abort if Rekordbox is running (strict filter) ---
RB_NAMES = {"rekordbox", "rekordboxagent"}
for p in psutil.process_iter(["name"]):
    try:
        name = (p.info["name"] or "").lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        continue
    if name in RB_NAMES or name in {n + ".exe" for n in RB_NAMES}:
        sys.exit(f"ABORT: Rekordbox process running: {p.info['name']}")

# --- Fresh copies ---
BUILD.mkdir(exist_ok=True)
for f in ("master.db", "master.db-wal", "master.db-shm", "masterPlaylists6.xml"):
    shutil.copy2(TESTDATA / f, BUILD / f)

from pyrekordbox.db6 import Rekordbox6Database, tables  # noqa: E402
from pyrekordbox.db6.database import BLOB  # noqa: E402
from pyrekordbox.utils import deobfuscate  # noqa: E402

KEY = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497"
print("embedded key == public constant:", deobfuscate(BLOB) == KEY)

db = Rekordbox6Database(path=BUILD / "master.db", db_dir=BUILD, key=KEY, unlock=True)

print("\n--- MyTag tree (djmdMyTag) ---")
for t in db.get_my_tag().order_by(tables.DjmdMyTag.ParentID, tables.DjmdMyTag.Seq):
    print(
        f"ID={t.ID!r} Parent={t.ParentID!r} Attr={t.Attribute} Seq={t.Seq} "
        f"Name={t.Name!r} UUID={t.UUID!r} rb_data_status={t.rb_data_status} "
        f"rb_local_deleted={t.rb_local_deleted} rb_local_synced={t.rb_local_synced}"
    )

print("\n--- Existing smart playlists (SmartList payloads) ---")
n = 0
for pl in db.get_playlist():
    if pl.SmartList:
        n += 1
        print(f"ID={pl.ID!r} Attr={pl.Attribute} Parent={pl.ParentID!r} Name={pl.Name!r}")
        print("   ", pl.SmartList[:400])
        if n >= 8:
            break
print("smart playlist count sample done")

print("\n--- Playlist tree roots ---")
for pl in db.get_playlist(ParentID="root").order_by(tables.DjmdPlaylist.Seq):
    print(f"ID={pl.ID!r} Attr={pl.Attribute} Name={pl.Name!r}")

print("\n--- Content stats ---")
total = db.query(tables.DjmdContent).count()
print("djmdContent rows:", total)
from sqlalchemy import func  # noqa: E402

for col in ("rb_data_status", "rb_local_deleted"):
    rows = (
        db.query(getattr(tables.DjmdContent, col), func.count())
        .group_by(getattr(tables.DjmdContent, col))
        .all()
    )
    print(f"{col} distribution:", rows)

c = (
    db.query(tables.DjmdContent)
    .filter(
        tables.DjmdContent.KeyID.isnot(None),
        tables.DjmdContent.GenreID.isnot(None),
        tables.DjmdContent.BitRate.isnot(None),
        tables.DjmdContent.rb_local_deleted == 0,
    )
    .first()
)
print("\n--- Sample content with readout fields ---")
print(f"ID={c.ID!r} type={type(c.ID).__name__} Title={c.Title!r}")
print(
    f"KeyID={c.KeyID!r} DJPlayCount={c.DJPlayCount!r} ({type(c.DJPlayCount).__name__}) "
    f"StockDate={c.StockDate!r} GenreID={c.GenreID!r} BitRate={c.BitRate!r} "
    f"rb_data_status={c.rb_data_status} rb_file_id={getattr(c, 'rb_file_id', None)!r}"
)
key = db.get_key(ID=c.KeyID).one_or_none()
genre = db.get_genre(ID=c.GenreID).one_or_none()
print("DjmdKey.ScaleName:", key.ScaleName if key else None)
print("DjmdGenre.Name:", genre.Name if genre else None)

print("\n--- Cue / playlist volumes ---")
print("djmdCue rows:", db.query(tables.DjmdCue).count())
print("djmdPlaylist rows:", db.query(tables.DjmdPlaylist).count())
print("djmdSongPlaylist rows:", db.query(tables.DjmdSongPlaylist).count())
print("djmdSongMyTag rows:", db.query(tables.DjmdSongMyTag).count())
print("djmdArtist rows:", db.query(tables.DjmdArtist).count())

print("\n--- AgentRegistry localUpdateCount ---")
print("local USN:", db.get_local_usn())

print("\n--- MenuItems TRACK / Device (add_content prerequisites) ---")
mi = db.get_menu_items(Name="TRACK").one_or_none()
print("menu item TRACK:", mi.ID if mi else None)
dev = db.get_device().first()
print("device:", (dev.ID, dev.Name) if dev else None)

db.close()
print("\nEXPLORE OK")
