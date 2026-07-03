"""Smart Fixes runner: dry-run -> confirm -> mutate (SPEC-UNIFIED 5.11,
safety properties proven in POC #9).

- dry_run() reads the CACHED snapshot read-only: it never opens master.db
  for write and does not require Rekordbox to be closed;
- execute() replays EXACTLY the confirmed dry-run payload (B10) through the
  single mutate unit-of-work, with the dry-run's fingerprint as the
  freshness guard: if the DB changed since the preview, mutate ABORTS with
  StaleSnapshotError before any backup or write.
"""

from syncbox.rb_write import open_rekordbox, set_content_fields
from syncbox.safety.mutate import mutate
from syncbox.smartfixes import plan


def dry_run(cache, storage_root, *, include_protected_ids=frozenset()) -> dict:
    rows = cache.get(storage_root)
    payload, skipped_protected = plan(
        rows, include_protected_ids=include_protected_ids
    )
    return {
        "payload": payload,
        "skipped_protected": skipped_protected,
        "fingerprint": cache.current_fingerprint,
    }


def execute(
    db_path,
    backups_root,
    cache,
    dry: dict,
    *,
    retention: int = 15,
    open_db=open_rekordbox,
) -> dict:
    """Apply a confirmed dry-run. The payload is applied verbatim - the UI
    confirmation text was built from it (B10: text == executed payload)."""
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
    ) as db:
        for content_id, changes in grouped.items():
            set_content_fields(db, content_id, changes)

    return {"fields_applied": len(dry["payload"]), "tracks_touched": len(grouped)}
