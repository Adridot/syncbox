"""Resolve tracks that live outside the canonical Rekordbox Collection.

Categories handled (everything under rekordbox/* in Dropbox is left alone):
  * LOCAL  (~/Music, ~/Downloads)  -> move the file into Collection + relink.
  * DISTANT (other machine, Google Drive) -> re-download from Deezer into
    Collection + relink when a match exists, otherwise soft-delete the entry.

Files we *create* in the Dropbox Collection are accessible to this process;
only reading pre-existing Dropbox files is blocked by macOS TCC — so local
moves (local read + new Dropbox write) and Deemix downloads both work here.

Usage (from ``service``):
    uv run python3 scripts/resolve_strays.py --dry-run
    uv run python3 scripts/resolve_strays.py --apply    # Rekordbox closed
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.acquisition import DeemixClient, DeezerResolver  # noqa: E402
from app.audio import find_downloaded_file  # noqa: E402
from app.config import load_config  # noqa: E402
from app.library import deemix_permanent_settings  # noqa: E402
from app.rekordbox import (  # noqa: E402
    RekordboxAdapter,
    is_rekordbox_row_deleted,
    mark_rekordbox_row_deleted,
    move_to_permanent,
    resolve_volume_path,
    safe_timestamp,
    to_volume_relative,
)


def _open_db(database_dir: Path):
    from pyrekordbox import Rekordbox6Database

    return Rekordbox6Database(db_dir=str(database_dir))


def classify(real: str, storage_root: str) -> str:
    sr = storage_root.rstrip("/")
    if real.startswith("/Users/adriendidot/Music") or real.startswith("/Users/adriendidot/Downloads"):
        return "local"
    if "GoogleDrive" in real:
        return "distant"
    if real.startswith("/Users/") and not real.startswith("/Users/adriendidot/"):
        return "distant"
    return "skip"  # canonical rekordbox/* (Collection, Chill background, Samples RB…), events


def scan(database_dir: Path, storage_root: str):
    db = _open_db(database_dir)
    try:
        local, distant = [], []
        for c in db.get_content():
            if is_rekordbox_row_deleted(c):
                continue
            real = resolve_volume_path(str(getattr(c, "FolderPath", "") or ""), storage_root)
            cat = classify(real, storage_root)
            row = {
                "id": str(c.ID),
                "title": str(getattr(c, "Title", "") or ""),
                "artist": str(getattr(c, "ArtistName", "") or ""),
                "isrc": str(getattr(c, "ISRC", "") or "").strip(),
                "duration_ms": int((getattr(c, "Length", 0) or 0) * 1000),
                "real": real,
            }
            if cat == "local":
                local.append(row)
            elif cat == "distant":
                distant.append(row)
        return local, distant
    finally:
        db.close()


async def _resolve(row: dict) -> dict | None:
    """Return the Deezer candidate for a stray row, or None."""
    resolver = DeezerResolver()
    track = SimpleNamespace(
        title=row["title"],
        artists=[a for a in [row["artist"]] if a],
        duration_ms=row["duration_ms"],
        isrc=row["isrc"] or None,
    )
    result = await resolver.resolve(track)
    if result.status == "resolved" and result.candidate:
        return {"id": result.candidate.id, "title": result.candidate.title,
                "artist": result.candidate.artist, "method": result.match_method}
    return None


def dry_run(config) -> None:
    sr = str(config.storage_root)
    local, distant = scan(config.rekordbox_database_dir, sr)
    print("=== DRY RUN — no changes ===")
    print(f"\nLOCAL → move into Collection: {len(local)}")
    for r in local[:8]:
        print(f"   {r['artist']} — {r['title']}   [{r['real'][-45:]}]")
    if len(local) > 8:
        print(f"   … +{len(local) - 8} more")
    print(f"\nDISTANT (other machine / Google Drive): {len(distant)} — resolving on Deezer…")
    redl, remove = [], []
    for r in distant:
        cand = asyncio.run(_resolve(r))
        if cand:
            redl.append((r, cand))
            print(f"   ✓ {r['title']} — {r['artist']}  →  Deezer: {cand['artist']} - {cand['title']} ({cand['method']})")
        else:
            remove.append(r)
            print(f"   ✗ {r['title']} — {r['artist']}  →  no Deezer match (will remove)")
    print(f"\nSummary: move {len(local)}, re-download {len(redl)}, remove {len(remove)}")


async def _download_and_locate(client: DeemixClient, deezer_id: str, collection: Path,
                               isrc: str, title: str, artist: str, timeout: float = 90.0) -> str | None:
    await client.download_batch([deezer_id], playlist_name="Syncbox strays")
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = find_downloaded_file(collection, isrc=isrc or None, title=title, artist=artist)
        if found:
            return found
        await asyncio.sleep(2)
    return find_downloaded_file(collection, isrc=isrc or None, title=title, artist=artist)


def apply(config) -> None:
    sr = str(config.storage_root)
    adapter = RekordboxAdapter(database_dir=config.rekordbox_database_dir, storage_root=config.storage_root)
    adapter.assert_mutation_ready()
    backup = adapter.backup_database()
    print(f"Backup: {backup}")
    collection = Path(sr) / "rekordbox" / "Collection"
    local, distant = scan(config.rekordbox_database_dir, sr)

    # Configure Deemix to download into Collection.
    client = DeemixClient()
    asyncio.run(client.update_settings(deemix_permanent_settings(collection)))

    # Resolve distant rows up-front (Deezer), partition into re-download / remove.
    redl, remove = [], []
    for r in distant:
        cand = asyncio.run(_resolve(r))
        (redl if cand else remove).append((r, cand) if cand else r)

    db = _open_db(config.rekordbox_database_dir)
    moved = downloaded = removed = 0
    failed_dl, by_id = [], {}
    try:
        for c in db.get_content():
            by_id[str(c.ID)] = c
        # 1. Local files → move into Collection + relink.
        for r in local:
            c = by_id.get(r["id"])
            src = Path(r["real"])
            if c is None or not src.exists():
                continue
            target = move_to_permanent(src, collection)
            c.FolderPath = to_volume_relative(target, sr)
            c.FileNameL = Path(target).name
            moved += 1
        # 2. Distant with a Deezer match → download into Collection + relink.
        for r, cand in redl:
            c = by_id.get(r["id"])
            if c is None:
                continue
            found = asyncio.run(_download_and_locate(
                client, cand["id"], collection, r["isrc"], cand["title"], cand["artist"]
            ))
            if not found:
                failed_dl.append(r)
                continue
            c.FolderPath = to_volume_relative(found, sr)
            c.FileNameL = Path(found).name
            downloaded += 1
        # 3. Distant without a match (+ failed downloads) → soft-delete.
        song_pl = [s for s in db.get_playlist_songs() if not is_rekordbox_row_deleted(s)]
        song_mt = [s for s in db.get_my_tag_songs() if not is_rekordbox_row_deleted(s)]
        refs_by_content: dict[str, list] = {}
        for s in song_pl + song_mt:
            refs_by_content.setdefault(str(s.ContentID), []).append(s)
        for r in remove + failed_dl:
            c = by_id.get(r["id"])
            if c is None:
                continue
            for ref in refs_by_content.get(str(c.ID), []):
                mark_rekordbox_row_deleted(ref)
            mark_rekordbox_row_deleted(c)
            removed += 1
        db.commit()
    except Exception:
        if hasattr(db, "rollback"):
            db.rollback()
        db.close()
        raise
    else:
        db.close()

    report = {
        "timestamp": safe_timestamp(), "backup": str(backup),
        "moved": moved, "downloaded": downloaded, "removed": removed,
        "failed_download": [r["title"] for r in failed_dl],
        "removed_titles": [r["title"] for r in remove + failed_dl],
    }
    out = Path(".local") / f"resolve-strays-report-{report['timestamp']}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("=== APPLIED ===")
    print(f"moved {moved}, re-downloaded {downloaded}, removed {removed}")
    print(f"report: {out}\nbackup: {backup}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve tracks outside the canonical Collection.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="Report only (default).")
    group.add_argument("--apply", action="store_true", help="Move/redownload/remove (Rekordbox closed).")
    args = parser.parse_args()
    config = load_config()
    if args.apply:
        apply(config)
    else:
        dry_run(config)


if __name__ == "__main__":
    main()
