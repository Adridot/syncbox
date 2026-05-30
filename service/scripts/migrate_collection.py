"""Migrate the app's permanent collection into the canonical Rekordbox folder.

Points the app's `permanent` setting at `<storageRoot>/rekordbox/Collection` and
`manual` at `<storageRoot>/rekordbox/Collection manuelle`, physically moves the
app-managed files currently under `_rekordbox_sync/permanent/` into Collection,
and relinks master.db (volume-relative `/<volume>/rekordbox/Collection/…` paths,
uniform with Rekordbox's native entries) so nothing is lost.

Events stay in their own deletable folder (not moved). Tracks living in other
locations (~/Music, ~/Downloads, Google Drive, another machine) are NOT moved —
they are listed in a report for definitive resolution.

Usage (from the ``service`` directory):

    uv run python3 scripts/migrate_collection.py --dry-run    # report only
    uv run python3 scripts/migrate_collection.py --apply      # Rekordbox closed
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_config  # noqa: E402
from app.db import LocalDatabase  # noqa: E402
from app.models import AppSettings  # noqa: E402
from app.rekordbox import (  # noqa: E402
    RekordboxAdapter,
    is_rekordbox_row_deleted,
    move_to_permanent,
    resolve_volume_path,
    safe_timestamp,
    to_volume_relative,
)

REPORT_FIELDS = ["content_id", "title", "artist", "category", "folder_path", "reason"]
DEFAULT_REPORT = Path(".local/collection-migration-report.csv")


def _norm(value: str) -> str:
    value = "".join(
        ch for ch in unicodedata.normalize("NFD", value.lower())
        if unicodedata.category(ch) != "Mn"
    )
    return re.sub(r"[^a-z0-9]", "", value)


def _open_db(database_dir: Path):
    from pyrekordbox import Rekordbox6Database

    return Rekordbox6Database(db_dir=str(database_dir))


def _settings(database: LocalDatabase, config) -> AppSettings:
    defaults = AppSettings(
        spotifyClientId="",
        spotifyRedirectUri=f"http://127.0.0.1:{config.api_port}/api/spotify/callback",
        rekordboxDatabaseDir=str(config.rekordbox_database_dir),
        storageRoot=str(config.storage_root),
        apiPort=config.api_port,
    )
    return database.get_app_settings(defaults)


def classify(real_path: str, storage_root: str) -> tuple[str, str]:
    """Return (category, reason). category: move/canonical/event/report."""
    sr = str(storage_root).rstrip("/")
    perm_src = f"{sr}/_rekordbox_sync/permanent/"
    coll = f"{sr}/rekordbox/Collection/"
    collm = f"{sr}/rekordbox/Collection manuelle/"
    events = f"{sr}/_rekordbox_sync/events/"
    if real_path.startswith(perm_src):
        return "move", "App permanent → Collection"
    if real_path.startswith(coll) or real_path.startswith(collm):
        return "canonical", ""
    if real_path.startswith(events):
        return "event", ""
    if "GoogleDrive" in real_path:
        return "report", "Sur Google Drive (autre cloud)"
    if real_path.startswith("/Users/") and not real_path.startswith("/Users/adriendidot/"):
        return "report", "Sur une autre machine"
    if real_path.startswith("/Users/adriendidot/Downloads"):
        return "report", "Dans ~/Downloads (temporaire)"
    if real_path.startswith("/Users/adriendidot/Music"):
        return "report", "Dans ~/Music (local, hors Dropbox)"
    return "report", "Hors collection canonique"


def scan(database_dir: Path, storage_root: str):
    db = _open_db(database_dir)
    try:
        to_move, report = [], []
        for c in db.get_content():
            if is_rekordbox_row_deleted(c):
                continue
            fp = str(getattr(c, "FolderPath", "") or "")
            real = resolve_volume_path(fp, storage_root)
            cat, reason = classify(real, storage_root)
            title = str(getattr(c, "Title", "") or "")
            artist = str(getattr(c, "ArtistName", "") or "")
            name = Path(real).name
            row = {
                "content_id": str(c.ID), "title": title, "artist": artist,
                "category": cat, "folder_path": fp, "reason": reason,
            }
            if cat == "move":
                to_move.append((str(c.ID), real))
            elif cat == "report":
                report.append(row)
            # title/file mismatch (any category) is also worth reporting
            tn, fn = _norm(title), _norm(Path(name).stem)
            if tn and fn and tn not in fn and fn not in tn and cat in {"canonical", "event"}:
                report.append({**row, "category": "mismatch",
                               "reason": f"Titre ≠ fichier ({name})"})
        return to_move, report
    finally:
        db.close()


def dry_run(config, report_path: Path) -> None:
    storage_root = str(config.storage_root)
    to_move, report = scan(config.rekordbox_database_dir, storage_root)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=REPORT_FIELDS)
        w.writeheader()
        for r in sorted(report, key=lambda x: (x["category"], x["title"].lower())):
            w.writerow(r)
    from collections import Counter
    cats = Counter(r["category"] for r in report)
    print("=== DRY RUN — no changes ===")
    print(f"new permanent = {storage_root}/rekordbox/Collection")
    print(f"new manual    = {storage_root}/rekordbox/Collection manuelle")
    print(f"\nFiles to move (_rekordbox_sync/permanent → Collection): {len(to_move)}")
    for cid, real in to_move[:10]:
        print(f"   {cid}  {Path(real).name}")
    if len(to_move) > 10:
        print(f"   … +{len(to_move) - 10} more")
    print(f"\nTo resolve definitively (NOT moved): {len(report)}")
    for cat, n in cats.most_common():
        print(f"   {cat:10} {n}")
    print(f"\nreport written to: {report_path}")


def apply(config) -> None:
    storage_root = str(config.storage_root)
    adapter = RekordboxAdapter(
        database_dir=config.rekordbox_database_dir, storage_root=config.storage_root
    )
    adapter.assert_mutation_ready()  # Rekordbox closed + db exists
    backup = adapter.backup_database()
    print(f"Backup: {backup}")

    database = LocalDatabase(config.app_database_path)
    new_permanent = Path(storage_root) / "rekordbox" / "Collection"
    new_manual = Path(storage_root) / "rekordbox" / "Collection manuelle"
    settings = _settings(database, config).model_copy(
        update={"permanent_path": str(new_permanent), "manual_collection_path": str(new_manual)}
    )
    database.save_app_settings(settings)
    print(f"Settings updated: permanent={new_permanent}")

    to_move, _ = scan(config.rekordbox_database_dir, storage_root)
    move_ids = {cid for cid, _ in to_move}

    db = _open_db(config.rekordbox_database_dir)
    moved, missing, denied = 0, [], []
    try:
        for c in db.get_content():
            if is_rekordbox_row_deleted(c) or str(c.ID) not in move_ids:
                continue
            source = Path(resolve_volume_path(str(getattr(c, "FolderPath", "") or ""), storage_root))
            if not source.exists():
                missing.append((str(c.ID), str(source)))
                continue
            try:
                target = move_to_permanent(source, new_permanent)  # handles name clashes
            except PermissionError:
                # macOS TCC blocks reading/moving existing files inside the
                # Dropbox CloudStorage folder unless the process has Full Disk
                # Access. Skip + relink nothing for this file.
                denied.append((str(c.ID), str(source)))
                continue
            c.FolderPath = to_volume_relative(target, storage_root)
            c.FileNameL = Path(target).name
            moved += 1
        db.commit()
    except Exception:
        if hasattr(db, "rollback"):
            db.rollback()
        db.close()
        raise
    else:
        db.close()

    if denied:
        print(
            f"\n⚠️  {len(denied)} fichier(s) non déplacés : accès disque refusé (macOS TCC).\n"
            "    Le process ne peut pas lire les fichiers dans le dossier Dropbox.\n"
            "    → Réglages système ▸ Confidentialité et sécurité ▸ Accès complet au disque\n"
            "      ajoute ton Terminal, puis relance: uv run python3 scripts/migrate_collection.py --apply"
        )

    report = {
        "timestamp": safe_timestamp(), "backup": str(backup),
        "moved": moved, "missing": missing, "permission_denied": denied,
        "permanent_path": str(new_permanent), "manual_collection_path": str(new_manual),
    }
    out = Path(".local") / f"collection-migration-report-{report['timestamp']}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("=== APPLIED ===")
    print(f"moved {moved} files into Collection; missing sources: {len(missing)}")
    print(f"report: {out}\nbackup: {backup}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate permanent collection into rekordbox/Collection.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="Report only (default).")
    group.add_argument("--apply", action="store_true", help="Move files + relink (Rekordbox closed).")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()
    config = load_config()
    if args.apply:
        apply(config)
    else:
        dry_run(config, Path(args.report))


if __name__ == "__main__":
    main()
