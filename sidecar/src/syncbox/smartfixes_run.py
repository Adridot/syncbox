"""Smart Fixes runner: dry-run -> confirm -> mutate (SPEC-UNIFIED 5.11).

- dry_run() reads the CACHED snapshot read-only: it never opens master.db
  for write and does not require Rekordbox to be closed;
- execute() replays every non-empty confirmed dry-run payload (B10) through
  the single mutate unit-of-work, with the dry-run's fingerprint as the
  freshness guard: if the DB changed since the preview, it ABORTS with
  StaleSnapshotError before any backup or write;
- execute() requires exact JSON-structural equality with the freshly derived complete
  plan. Missing, reordered, duplicated, enriched, or changed entries are
  refused before any backup. The real-fixture POC remains a release gate.
- ownership does not affect this metadata-only operation.
- an empty direct plan still runs the Rekordbox guard, then returns without
  opening the database or creating a backup.
"""

from syncbox.rb_write import open_rekordbox, set_content_fields
from syncbox.safety import process_guard
from syncbox.safety.mutate import StaleSnapshotError, mutate
from syncbox.smartfixes import plan


def dry_run(cache, storage_root) -> dict:
    rows = cache.get(storage_root)
    return {
        "payload": plan(rows),
        "fingerprint": cache.current_fingerprint,
    }


def execute(
    db_path,
    backups_root,
    cache,
    storage_root,
    dry: dict,
    *,
    retention: int = 20,
    open_db=open_rekordbox,
    app_db_path=None,
) -> dict:
    """Apply the complete confirmed plan after exact server-side revalidation."""
    if dry.get("fingerprint") is None:
        raise ValueError("the dry-run fingerprint is required")
    rows = cache.get(storage_root)
    if cache.current_fingerprint != dry["fingerprint"]:
        raise StaleSnapshotError(
            "master.db changed since the dry-run snapshot; nothing was "
            "written and no backup was created. Run a fresh dry-run and retry."
        )
    expected_payload = plan(rows)
    if dry["payload"] != expected_payload:
        raise ValueError(
            "payload must exactly match the complete current server-side plan"
        )
    if not expected_payload:
        process_guard.assert_mutation_ready(db_path)
        return {"fields_applied": 0, "tracks_touched": 0}

    grouped: dict[str, dict] = {}
    for change in dry["payload"]:
        grouped.setdefault(change["content_id"], {})[change["field"]] = change["after"]

    with mutate(
        db_path,
        backups_root,
        retention=retention,
        expected_fingerprint=dry["fingerprint"],
        open_db=open_db,
        invalidate_cache=cache.invalidate,
        app_db_path=app_db_path,
        backup_reason="smart_fixes",
    ) as db:
        for content_id, changes in grouped.items():
            set_content_fields(db, content_id, changes)

    return {"fields_applied": len(dry["payload"]), "tracks_touched": len(grouped)}
