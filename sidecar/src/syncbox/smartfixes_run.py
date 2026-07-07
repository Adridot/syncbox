"""Smart Fixes runner: dry-run -> confirm -> mutate (SPEC-UNIFIED 5.11,
safety properties proven in POC #9).

- dry_run() reads the CACHED snapshot read-only: it never opens master.db
  for write and does not require Rekordbox to be closed;
- execute() replays EXACTLY the confirmed dry-run payload (B10) through the
  single mutate unit-of-work, with the dry-run's fingerprint as the
  freshness guard: if the DB changed since the preview, it ABORTS with
  StaleSnapshotError before any backup or write;
- execute() re-checks the payload SERVER-SIDE against the 5.11 plan: a
  payload entry outside the freshly derived plan is refused before any
  backup. (The protected-track opt-in was removed on owner amendment
  2026-07-07: Smart Fixes are metadata-only, behind an automatic backup;
  the protected guard stays on file-destructive ops like D15.)
"""

from syncbox.rb_write import open_rekordbox, set_content_fields
from syncbox.safety.mutate import StaleSnapshotError, mutate
from syncbox.smartfixes import plan


def dry_run(cache, storage_root) -> dict:
    rows = cache.get(storage_root)
    return {
        "payload": plan(rows),
        "fingerprint": cache.current_fingerprint,
    }


def _change_key(change: dict) -> tuple:
    return (
        str(change["content_id"]),
        change["field"],
        change.get("before"),
        change["after"],
    )


def execute(
    db_path,
    backups_root,
    cache,
    storage_root,
    dry: dict,
    *,
    retention: int = 15,
    open_db=open_rekordbox,
) -> dict:
    """Apply a confirmed dry-run. The payload is applied verbatim - the UI
    confirmation text was built from it (B10: text == executed payload) -
    but only after the server re-derives the plan and confirms every entry
    is in it (a forged or out-of-date entry is refused before any backup)."""
    rows = cache.get(storage_root)
    if dry["fingerprint"] is not None and cache.current_fingerprint != dry["fingerprint"]:
        raise StaleSnapshotError(
            "master.db changed since the dry-run snapshot; nothing was "
            "written and no backup was created. Run a fresh dry-run and retry."
        )
    allowed = {_change_key(change) for change in plan(rows)}
    refused = sorted(
        {
            str(change["content_id"])
            for change in dry["payload"]
            if _change_key(change) not in allowed
        }
    )
    if refused:
        raise ValueError(
            "payload entries are not in the current server-side plan; "
            f"refused content ids: {refused}"
        )

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
