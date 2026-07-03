"""Smart Fixes runner: dry-run -> confirm -> mutate (SPEC-UNIFIED 5.11,
safety properties proven in POC #9).

- dry_run() reads the CACHED snapshot read-only: it never opens master.db
  for write and does not require Rekordbox to be closed;
- execute() replays EXACTLY the confirmed dry-run payload (B10) through the
  single mutate unit-of-work, with the dry-run's fingerprint as the
  freshness guard: if the DB changed since the preview, it ABORTS with
  StaleSnapshotError before any backup or write;
- execute() re-checks the payload SERVER-SIDE against the 5.11 plan: a
  protected track is only writable when its id is in the per-call
  include_protected_ids opt-in (never remembered), symmetric with the D15
  protected guard on untagged delete. A payload entry outside the plan is
  refused before any backup.
"""

from syncbox.rb_write import open_rekordbox, set_content_fields
from syncbox.safety.mutate import StaleSnapshotError, mutate
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
    include_protected_ids=frozenset(),
    retention: int = 15,
    open_db=open_rekordbox,
) -> dict:
    """Apply a confirmed dry-run. The payload is applied verbatim - the UI
    confirmation text was built from it (B10: text == executed payload) -
    but only after the server re-derives the plan and confirms every entry
    is in it (5.11: protected tracks are never mutated without the named
    per-call opt-in, whatever the client sends)."""
    rows = cache.get(storage_root)
    if dry["fingerprint"] is not None and cache.current_fingerprint != dry["fingerprint"]:
        raise StaleSnapshotError(
            "master.db changed since the dry-run snapshot; nothing was "
            "written and no backup was created. Run a fresh dry-run and retry."
        )
    planned, _skipped = plan(rows, include_protected_ids=include_protected_ids)
    allowed = {_change_key(change) for change in planned}
    refused = sorted(
        {
            str(change["content_id"])
            for change in dry["payload"]
            if _change_key(change) not in allowed
        }
    )
    if refused:
        raise ValueError(
            "payload entries are not in the current server-side plan (5.11: "
            "a protected track requires the per-call include_protected_ids "
            f"opt-in); refused content ids: {refused}"
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
