"""Probe: which mixed int+string PK scenarios crash SQLAlchemy at flush/commit.
Runs on the already-mutated build copy (disposable)."""
import uuid
from pathlib import Path
import sqlalchemy
from pyrekordbox.db6 import Rekordbox6Database, tables

BUILD = Path(__file__).resolve().parent / "build"
KEY = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497"
print("SQLAlchemy version:", sqlalchemy.__version__)

def fresh():
    return Rekordbox6Database(path=BUILD / "master.db", db_dir=BUILD, key=KEY, unlock=True)

def probe(label, fn):
    db = fresh()
    try:
        fn(db)
        print(f"{label}: NO CRASH")
    except Exception as e:
        print(f"{label}: {type(e).__name__}: {str(e)[:200]}")
    finally:
        try:
            db.rollback()
        except Exception as e2:
            print(f"   rollback failed: {type(e2).__name__}")
        db.close()

def s1(db):  # two inserts, int + str PK, flush
    db.add(tables.DjmdArtist.create(ID=db.generate_unused_id(tables.DjmdArtist), Name="P1i", UUID=str(uuid.uuid4())))
    db.add(tables.DjmdArtist.create(ID=str(db.generate_unused_id(tables.DjmdArtist)), Name="P1s", UUID=str(uuid.uuid4())))
    db.flush()

def s2(db):  # int-PK insert + update of existing str-PK row, flush
    db.add(tables.DjmdArtist.create(ID=db.generate_unused_id(tables.DjmdArtist), Name="P2i", UUID=str(uuid.uuid4())))
    row = db.query(tables.DjmdArtist).filter(tables.DjmdArtist.Name.isnot(None)).first()
    row.SearchStr = "poc5probe"
    db.flush()

def s3(db):  # int-PK insert then query the same table before flush (autoflush path)
    db.add(tables.DjmdArtist.create(ID=db.generate_unused_id(tables.DjmdArtist), Name="P3i", UUID=str(uuid.uuid4())))
    db.query(tables.DjmdArtist).filter_by(Name="P3i").all()

def s4(db):  # int-PK insert whose value collides with an existing string PK
    existing = db.query(tables.DjmdArtist).first()
    db.add(tables.DjmdArtist.create(ID=int(existing.ID), Name="P4i", UUID=str(uuid.uuid4())))
    db.flush()

def s5(db):  # session.get identity-map mixing: load str row then get with int key
    existing = db.query(tables.DjmdArtist).first()
    got = db.session.get(tables.DjmdArtist, int(existing.ID))
    print("   s5 got:", got)

probe("s1 int+str inserts flush", s1)
probe("s2 int insert + str-row update flush", s2)
probe("s3 int insert + autoflush query", s3)
probe("s4 int insert colliding with existing str PK", s4)
probe("s5 identity map int vs str get", s5)
