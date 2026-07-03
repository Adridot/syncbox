"""Load-bearing Rekordbox status integers (SPEC-01 1.1).

These integers carry the Rekordbox 6/7 sync semantics and must be
reproduced byte-identically, or the user's Rekordbox sync corrupts:
256 = active content row, 258 = soft-deleted content row. Verified
on-disk against a real RB 7.x master.db in poc/05.

Dependency-free on purpose: every Rekordbox read elsewhere filters
through :func:`is_soft_deleted`.
"""

from collections.abc import Mapping

RB_DATA_STATUS_ACTIVE = 256
RB_DATA_STATUS_SOFT_DELETED = 258

_SOFT_DELETE = {
    "rb_local_deleted": 1,
    "rb_local_synced": 0,
    "rb_data_status": RB_DATA_STATUS_SOFT_DELETED,
    "rb_local_data_status": 0,
}

_REACTIVATE = {
    "rb_data_status": RB_DATA_STATUS_ACTIVE,
    "rb_local_deleted": 0,
}


def soft_delete_values() -> dict:
    """Column values marking a content row soft-deleted (a fresh copy)."""
    return dict(_SOFT_DELETE)


def reactivate_values() -> dict:
    """Column values restoring a soft-deleted content row (a fresh copy)."""
    return dict(_REACTIVATE)


def _read(row, field):
    if isinstance(row, Mapping):
        return row.get(field)
    return getattr(row, field, None)


def is_soft_deleted(row) -> bool:
    """True when the row is soft-deleted; accepts ORM rows and mappings.

    pyrekordbox's own getters do NOT filter soft-deleted rows (poc/05
    caveat 3), so this predicate is the mandatory Syncbox-side filter.
    The value is coerced through int() because pyrekordbox maps some
    integer columns as VARCHAR (poc/05 caveat 5): bool("0") would lie.
    """
    value = _read(row, "rb_local_deleted")
    if value is None:
        return False
    return int(value) != 0
