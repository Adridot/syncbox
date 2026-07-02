"""Probe: read-only SQLCipher open (mode=ro URI) on a WAL master.db copy,
plus a look at real dirty-data shapes (NULL-artist titles with ' - ',
all-caps titles, URLs) to calibrate the fixed catalog expectations.
"""
import shutil
import sys
from pathlib import Path

import sqlcipher3

POC = Path(__file__).resolve().parent
BUILD = POC / "build"
TESTDATA = POC.parent / "testdata"
KEY = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497"

BUILD.mkdir(exist_ok=True)
for f in ("master.db", "master.db-wal", "master.db-shm"):
    shutil.copy2(TESTDATA / f, BUILD / f)
db = BUILD / "master.db"

# 1. mode=ro URI open
con = sqlcipher3.connect(f"file:{db}?mode=ro", uri=True)
con.execute(f"PRAGMA key = '{KEY}'")
print("journal_mode:", con.execute("PRAGMA journal_mode").fetchone())
n = con.execute("SELECT COUNT(*) FROM djmdContent").fetchone()[0]
print("djmdContent rows via mode=ro:", n)

# 2. write attempt on the ro connection must fail
try:
    con.execute("UPDATE djmdContent SET Title = Title WHERE 1=0")
    print("WRITE DID NOT FAIL - mode=ro not enforced")
    sys.exit(1)
except sqlcipher3.OperationalError as e:
    print("write on ro connection correctly refused:", e)

# 3. real data shapes for the catalog
rows = con.execute(
    "SELECT c.ID, c.Title, c.ArtistID, a.Name FROM djmdContent c "
    "LEFT JOIN djmdArtist a ON a.ID = c.ArtistID "
    "WHERE c.rb_local_deleted = 0"
).fetchall()
print("active rows (rb_local_deleted=0):", len(rows))
noartist_dash = [r for r in rows if (r[3] is None or r[3] == "") and r[1] and " - " in r[1]]
caps = [r for r in rows if r[1] and r[1].isupper() and sum(ch.isalpha() for ch in r[1]) >= 4]
urls = [r for r in rows if r[1] and ("www." in r[1].lower() or "http" in r[1].lower())]
multispace = [r for r in rows if r[1] and ("  " in r[1] or r[1] != r[1].strip())]
print("NULL/empty-artist titles containing ' - ':", len(noartist_dash))
for r in noartist_dash[:5]:
    print("   ", r[0], repr(r[1]))
print("all-caps titles (>=4 alpha):", len(caps))
for r in caps[:5]:
    print("   ", r[0], repr(r[1]))
print("titles containing URL-ish:", len(urls))
for r in urls[:5]:
    print("   ", r[0], repr(r[1]))
print("titles with doubled/edge whitespace:", len(multispace))
for r in multispace[:5]:
    print("   ", r[0], repr(r[1]))

# 4. status distribution of the protected-path rule false-positive check
fp = con.execute(
    "SELECT COUNT(*) FROM djmdContent WHERE rb_local_deleted = 0 "
    "AND FolderPath LIKE '%/rekordbox/Collection/%'"
).fetchone()[0]
print("existing rows matching the protected path rule:", fp)
con.close()
print("PROBE OK")
