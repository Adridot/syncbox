"""One-shot maintenance tool: prune untagged tracks and event playlists.

Usage (from the ``service`` directory):

    # 1. inspect — writes service/.local/cleanup-manifest.csv, mutates nothing
    uv run python3 scripts/cleanup_rekordbox.py --dry-run

    # 2. (optional) edit the CSV: flip any `action` between delete/keep

    # 3. apply — backs up the DB, then soft-deletes everything still marked
    #    action=delete in the manifest. Rekordbox MUST be closed.
    uv run python3 scripts/cleanup_rekordbox.py --apply service/.local/cleanup-manifest.csv

Soft-delete only: rows are flagged ``rb_local_deleted`` in master.db (reversible
from the backup). Audio files on disk are never touched.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

# Allow ``import app...`` when run as a standalone script from service/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_config  # noqa: E402
from app.maintenance import (  # noqa: E402
    ACTION_DELETE,
    TrackRow,
    classify_untagged,
    summarize,
)
from app.rekordbox import (  # noqa: E402
    RekordboxAdapter,
    _remove_playlist_from_xml,
    is_rekordbox_row_deleted,
    mark_rekordbox_row_deleted,
    safe_timestamp,
)

# Event playlists to delete (validated with the user). Matched case-insensitively
# on the playlist Name. Deleting a playlist does not delete its tracks.
EVENT_PLAYLIST_NAMES = {
    name.casefold()
    for name in [
        "Antoine & Mathilde",
        "Foucault & Marie",
        "François et anne laure",
        "Habérille & Clément",
        "Jules & Océane",
        "Luc & Bénédicte",
        "Ludo & Emma",
        "Su & Louis",
        "Violette & Alexandre",
        "SAX",
        "albert",
    ]
}

MANIFEST_FIELDS = [
    "kind",  # "track" | "playlist"
    "id",  # content id or playlist id
    "artist",
    "title",
    "folder_path",
    "category",  # reason / "event_playlist"
    "action",  # "delete" | "keep"
    "matched_tagged_title",
]

DEFAULT_MANIFEST = Path(".local/cleanup-manifest.csv")


def _deleted(row) -> bool:
    return is_rekordbox_row_deleted(row)


def _open_database(database_dir: Path):
    from pyrekordbox import Rekordbox6Database

    return Rekordbox6Database(db_dir=str(database_dir))


def _load_track_rows(database) -> tuple[list[TrackRow], list[TrackRow]]:
    contents = [c for c in database.get_content() if not _deleted(c)]
    tagged_ids = {
        str(s.ContentID) for s in database.get_my_tag_songs() if not _deleted(s)
    }
    tagged: list[TrackRow] = []
    untagged: list[TrackRow] = []
    for content in contents:
        row = TrackRow(
            content_id=str(content.ID),
            artist=str(getattr(content, "ArtistName", "") or ""),
            title=str(getattr(content, "Title", "") or ""),
            folder_path=str(getattr(content, "FolderPath", "") or ""),
            is_tagged=str(content.ID) in tagged_ids,
        )
        (tagged if row.is_tagged else untagged).append(row)
    return tagged, untagged


def _target_event_playlists(database) -> list:
    return [
        playlist
        for playlist in database.get_playlist()
        if not _deleted(playlist)
        and str(getattr(playlist, "Name", "") or "").strip().casefold()
        in EVENT_PLAYLIST_NAMES
    ]


def dry_run(database_dir: Path, manifest_path: Path) -> None:
    database = _open_database(database_dir)
    try:
        tagged, untagged = _load_track_rows(database)
        decisions = classify_untagged(tagged, untagged)
        playlists = _target_event_playlists(database)
    finally:
        database.close()

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for decision in sorted(decisions, key=lambda d: (d.action, d.reason, d.artist.lower(), d.title.lower())):
            writer.writerow(
                {
                    "kind": "track",
                    "id": decision.content_id,
                    "artist": decision.artist,
                    "title": decision.title,
                    "folder_path": decision.folder_path,
                    "category": decision.reason,
                    "action": decision.action,
                    "matched_tagged_title": decision.matched_tagged_title,
                }
            )
        for playlist in sorted(playlists, key=lambda p: str(getattr(p, "Name", "")).lower()):
            writer.writerow(
                {
                    "kind": "playlist",
                    "id": str(playlist.ID),
                    "artist": "",
                    "title": str(getattr(playlist, "Name", "") or ""),
                    "folder_path": "",
                    "category": "event_playlist",
                    "action": ACTION_DELETE,
                    "matched_tagged_title": "",
                }
            )

    counts = summarize(decisions)
    print("=== DRY RUN — no changes written to master.db ===")
    print(f"tagged tracks (kept)......... {len(tagged)}")
    print(f"untagged tracks.............. {len(untagged)}")
    print(f"  junk....................... {counts.get('junk', 0)}")
    print(f"  dup_of_tagged.............. {counts.get('dup_of_tagged', 0)}")
    print(f"  alt_version................ {counts.get('alt_version', 0)}")
    print(f"  unique_mainstream (kept)... {counts.get('unique_mainstream', 0)}")
    print(f"=> tracks to delete.......... {counts.get(ACTION_DELETE, 0)}")
    print(f"event playlists to delete.... {len(playlists)}: "
          f"{', '.join(str(getattr(p, 'Name', '')) for p in playlists)}")
    print(f"\nmanifest written to: {manifest_path}")
    print("Review/edit it, then re-run with --apply <manifest> (Rekordbox closed).")


def _read_manifest(manifest_path: Path) -> tuple[set[str], set[str]]:
    delete_track_ids: set[str] = set()
    delete_playlist_ids: set[str] = set()
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("action", "").strip().lower() != ACTION_DELETE:
                continue
            kind = row.get("kind", "").strip().lower()
            row_id = row.get("id", "").strip()
            if not row_id:
                continue
            if kind == "track":
                delete_track_ids.add(row_id)
            elif kind == "playlist":
                delete_playlist_ids.add(row_id)
    return delete_track_ids, delete_playlist_ids


def apply(database_dir: Path, storage_root: Path, manifest_path: Path) -> None:
    delete_track_ids, delete_playlist_ids = _read_manifest(manifest_path)
    if not delete_track_ids and not delete_playlist_ids:
        print("Nothing marked action=delete in the manifest. Aborting.")
        return

    adapter = RekordboxAdapter(database_dir=database_dir, storage_root=storage_root)
    adapter.assert_mutation_ready()  # raises if Rekordbox is running / db missing

    backup_path = adapter.backup_database()
    xml_path = database_dir / "masterPlaylists6.xml"
    if xml_path.exists():
        shutil.copy2(xml_path, Path(backup_path) / xml_path.name)
    print(f"Backup created at: {backup_path}")

    database = _open_database(database_dir)
    deleted_tracks = 0
    deleted_playlists = 0
    deleted_song_refs = 0
    removed_playlist_names: list[str] = []
    try:
        song_playlist_rows = [
            s for s in database.get_playlist_songs() if not _deleted(s)
        ]
        refs_by_content: dict[str, list] = {}
        refs_by_playlist: dict[str, list] = {}
        for ref in song_playlist_rows:
            refs_by_content.setdefault(str(ref.ContentID), []).append(ref)
            refs_by_playlist.setdefault(str(ref.PlaylistID), []).append(ref)

        # 1. Delete tracks (+ their playlist references).
        for content in database.get_content():
            if _deleted(content) or str(content.ID) not in delete_track_ids:
                continue
            mark_rekordbox_row_deleted(content)
            deleted_tracks += 1
            for ref in refs_by_content.get(str(content.ID), []):
                if not _deleted(ref):
                    mark_rekordbox_row_deleted(ref)
                    deleted_song_refs += 1

        # 2. Delete event playlists (+ their song references).
        for playlist in database.get_playlist():
            if _deleted(playlist) or str(playlist.ID) not in delete_playlist_ids:
                continue
            for ref in refs_by_playlist.get(str(playlist.ID), []):
                if not _deleted(ref):
                    mark_rekordbox_row_deleted(ref)
                    deleted_song_refs += 1
            mark_rekordbox_row_deleted(playlist)
            deleted_playlists += 1
            removed_playlist_names.append(str(getattr(playlist, "Name", "") or ""))

        database.commit()
    except Exception:
        if hasattr(database, "rollback"):
            database.rollback()
        database.close()
        raise
    else:
        database.close()

    # 3. Remove deleted playlists from the exported XML (best effort).
    for name in removed_playlist_names:
        if name:
            try:
                _remove_playlist_from_xml(database_dir, name)
            except Exception as exc:  # pragma: no cover - XML is non-critical
                print(f"  (warning) could not remove '{name}' from XML: {exc}")

    report = {
        "timestamp": safe_timestamp(),
        "backup_path": str(backup_path),
        "deleted_tracks": deleted_tracks,
        "deleted_playlists": deleted_playlists,
        "deleted_song_refs": deleted_song_refs,
        "removed_playlists": removed_playlist_names,
    }
    report_path = manifest_path.parent / f"cleanup-report-{report['timestamp']}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== APPLIED ===")
    print(f"deleted tracks........... {deleted_tracks}")
    print(f"deleted event playlists.. {deleted_playlists} ({', '.join(removed_playlist_names)})")
    print(f"deleted playlist refs.... {deleted_song_refs}")
    print(f"report................... {report_path}")
    print(f"backup................... {backup_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prune untagged tracks and event playlists from Rekordbox.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="Classify and write the manifest, mutating nothing (default).")
    group.add_argument("--apply", metavar="MANIFEST", help="Apply deletions from a reviewed manifest CSV.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Manifest path for --dry-run output.")
    args = parser.parse_args()

    config = load_config()
    database_dir = config.rekordbox_database_dir

    if args.apply:
        apply(database_dir, config.storage_root, Path(args.apply))
    else:
        dry_run(database_dir, Path(args.manifest))


if __name__ == "__main__":
    main()
