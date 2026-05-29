"""Backfill the artist (ArtistName) on Rekordbox tracks that have none.

Two classes of empty-artist tracks exist:
  * legacy imports where the artist was baked into the title
    ("Maitre Gims - Zombie (Dj Last One)") -> parsed from the title;
  * tracks added by this app (e.g. "Alicante", "APT.") whose artist is known
    from the local library database, matched by ISRC.

Usage (from the ``service`` directory):

    # 1. inspect — writes .local/artist-repair-manifest.csv, mutates nothing
    uv run python3 scripts/repair_artists.py --dry-run

    # 2. (optional) edit the CSV: blank a `proposed_artist` to skip that row
    # 3. apply — backs up master.db, then sets the artist. Rekordbox closed.
    uv run python3 scripts/repair_artists.py --apply .local/artist-repair-manifest.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_config  # noqa: E402
from app.maintenance import parse_leading_artist  # noqa: E402
from app.rekordbox import (  # noqa: E402
    RekordboxAdapter,
    ensure_artist,
    is_rekordbox_row_deleted,
    safe_timestamp,
)

MANIFEST_FIELDS = ["content_id", "title", "proposed_artist", "source"]
DEFAULT_MANIFEST = Path(".local/artist-repair-manifest.csv")


def _open_database(database_dir: Path):
    from pyrekordbox import Rekordbox6Database

    return Rekordbox6Database(db_dir=str(database_dir))


def _isrc_to_artist(app_db_path: Path) -> dict[str, str]:
    """Map ISRC -> artist string from the local library, for app-added tracks."""
    import sqlite3

    mapping: dict[str, str] = {}
    con = sqlite3.connect(app_db_path)
    con.row_factory = sqlite3.Row
    try:
        for row in con.execute(
            "SELECT isrc, artists_json FROM library_tracks WHERE isrc IS NOT NULL AND isrc != ''"
        ):
            try:
                artists = json.loads(row["artists_json"] or "[]")
            except json.JSONDecodeError:
                artists = []
            artist = ", ".join(a for a in artists if a).strip()
            if artist:
                mapping.setdefault(str(row["isrc"]).upper(), artist)
    finally:
        con.close()
    return mapping


def _empty_artist_rows(database) -> list:
    rows = []
    for content in database.get_content():
        if is_rekordbox_row_deleted(content):
            continue
        if str(getattr(content, "ArtistName", "") or "").strip():
            continue
        rows.append(content)
    return rows


def _propose(content, isrc_to_artist: dict[str, str]) -> tuple[str, str]:
    """Return (proposed_artist, source)."""
    isrc = str(getattr(content, "ISRC", "") or "").strip().upper()
    if isrc and isrc in isrc_to_artist:
        return isrc_to_artist[isrc], "library_isrc"
    title = str(getattr(content, "Title", "") or "")
    parsed = parse_leading_artist(title)
    if parsed:
        return parsed, "title_parse"
    return "", "unresolved"


def dry_run(database_dir: Path, app_db_path: Path, manifest_path: Path) -> None:
    isrc_to_artist = _isrc_to_artist(app_db_path)
    database = _open_database(database_dir)
    try:
        empties = _empty_artist_rows(database)
        proposals = [
            (str(c.ID), str(getattr(c, "Title", "") or ""), *_propose(c, isrc_to_artist))
            for c in empties
        ]
    finally:
        database.close()

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for content_id, title, artist, source in sorted(proposals, key=lambda p: p[3]):
            writer.writerow(
                {
                    "content_id": content_id,
                    "title": title,
                    "proposed_artist": artist,
                    "source": source,
                }
            )

    from collections import Counter

    counts = Counter(source for *_, source in proposals)
    resolved = sum(1 for *_, a, _ in proposals if a)
    print("=== DRY RUN — no changes written to master.db ===")
    print(f"tracks with empty artist: {len(proposals)}")
    print(f"  resolvable from library ISRC: {counts.get('library_isrc', 0)}")
    print(f"  resolvable from title parse.: {counts.get('title_parse', 0)}")
    print(f"  unresolved (left blank).....: {counts.get('unresolved', 0)}")
    print(f"=> will set artist on {resolved} tracks")
    print(f"\nmanifest written to: {manifest_path}")
    print("Review/edit it (blank a proposed_artist to skip), then --apply <manifest>.")


def apply(database_dir: Path, storage_root: Path, manifest_path: Path) -> None:
    targets: dict[str, str] = {}
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            artist = (row.get("proposed_artist") or "").strip()
            cid = (row.get("content_id") or "").strip()
            if cid and artist:
                targets[cid] = artist
    if not targets:
        print("No rows with a proposed_artist. Aborting.")
        return

    adapter = RekordboxAdapter(database_dir=database_dir, storage_root=storage_root)
    adapter.assert_mutation_ready()
    backup_path = adapter.backup_database()
    print(f"Backup created at: {backup_path}")

    database = _open_database(database_dir)
    updated = 0
    try:
        for content in database.get_content():
            if is_rekordbox_row_deleted(content):
                continue
            artist = targets.get(str(content.ID))
            if not artist:
                continue
            artist_row = ensure_artist(database, artist)
            if artist_row is not None:
                content.ArtistID = artist_row.ID
                updated += 1
        database.commit()
    except Exception:
        if hasattr(database, "rollback"):
            database.rollback()
        database.close()
        raise
    else:
        database.close()

    report = {
        "timestamp": safe_timestamp(),
        "backup_path": str(backup_path),
        "artists_set": updated,
    }
    report_path = manifest_path.parent / f"artist-repair-report-{report['timestamp']}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("=== APPLIED ===")
    print(f"artists set on {updated} tracks")
    print(f"report: {report_path}")
    print(f"backup: {backup_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill empty Rekordbox track artists.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="Write the manifest, mutate nothing (default).")
    group.add_argument("--apply", metavar="MANIFEST", help="Apply artists from a reviewed manifest CSV.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Manifest path for --dry-run output.")
    args = parser.parse_args()

    config = load_config()
    if args.apply:
        apply(config.rekordbox_database_dir, config.storage_root, Path(args.apply))
    else:
        dry_run(config.rekordbox_database_dir, config.app_database_path, Path(args.manifest))


if __name__ == "__main__":
    main()
