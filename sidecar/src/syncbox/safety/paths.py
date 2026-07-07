"""Load-bearing path resolution (SPEC-UNIFIED 3.2/3.3/5.2, SPEC-01 1.4/1.5).

Rekordbox stores a file living under <storage_root>/rekordbox/... in
volume-relative form (/<VolumeName>/..., where VolumeName is the basename of
the storage root) and everything else absolute; deviating from this rule
makes Rekordbox show "file could not be found". Volume-relative and absolute
spellings of the same file must compare equal (and hash-equal) everywhere,
and existence checks must never enumerate a parent directory (macOS TCC
cloud-folder quirk).
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

__all__ = [
    "SYNC_DIR_NAME",
    "canonical_key",
    "path_lookup_keys",
    "paths_equal",
    "stored_form",
    "tcc_exists",
]

# The tool-managed working dir under the storage root (inbox / events /
# backups). Renamed from '_rekordbox_sync' on owner decision 2026-07-07; a
# pre-rename dir is left untouched (nothing migrates, new writes land here).
SYNC_DIR_NAME = "_syncbox"

# ponytail: volume-relative rows are handled POSIX-style only (macOS-first,
# Phase 0 decision). Windows drive-letter storage roots land with the
# SPEC-UNIFIED 6.9 per-OS abstraction before M5.


def _storage_root(storage_root) -> Path:
    return Path(os.path.expanduser(os.fspath(storage_root)))


def _volume_resolve(raw: str, storage_root) -> str:
    """Map a volume-relative row (/<VolumeName>/...) to its absolute path.

    Any input not starting with the storage root's volume name is returned
    unchanged.
    """
    root = _storage_root(storage_root)
    parts = PurePosixPath(raw).parts
    if len(parts) >= 2 and parts[0] == "/" and parts[1] == root.name:
        return str(root.joinpath(*parts[2:]))
    return raw


def stored_form(path, storage_root) -> str:
    """Return the exact form Rekordbox needs stored in master.db.

    Under <storage_root>/rekordbox/... -> volume-relative /<VolumeName>/...;
    everything else -> absolute. Idempotent: a path already in volume-relative
    form maps to itself. Purely lexical apart from expanduser (no filesystem
    access), so it is stable for not-yet-existing staging paths.
    """
    root = _storage_root(storage_root)
    p = Path(os.path.expanduser(_volume_resolve(os.fspath(path), storage_root)))
    if not p.is_absolute():
        p = Path.cwd() / p
    try:
        rel = p.relative_to(root)
    except ValueError:
        return str(p)
    # relative_to guarantees a real segment boundary: 'rekordbox-old' or a
    # nested 'inbox/rekordbox' never slip through a naive prefix check.
    if rel.parts and rel.parts[0] == "rekordbox":
        return "/" + "/".join((root.name, *rel.parts))
    return str(p)


def path_lookup_keys(raw, storage_root) -> tuple[str, ...]:
    """Emit every spelling under which a path may be known (SPEC-01 1.4).

    Forms, in stable order: raw / volume-resolved / expanduser / resolve() /
    volume-relative, deduplicated. Intersecting the key sets of two paths is
    how an absolute staging path matches a volume-relative DB row.
    """
    raw_s = os.fspath(raw)
    volume_resolved = _volume_resolve(raw_s, storage_root)
    expanded = os.path.expanduser(volume_resolved)
    # Non-strict resolve: symlinked spellings converge, missing files allowed.
    resolved = str(Path(expanded).resolve())
    volume_relative = stored_form(expanded, storage_root)
    return tuple(
        dict.fromkeys((raw_s, volume_resolved, expanded, resolved, volume_relative))
    )


def canonical_key(path, storage_root) -> str:
    """One canonical string per file: volume-relative == absolute (3.2).

    Safe as a dict/set key: equal paths yield equal (hence hash-equal) keys.
    """
    # ponytail: lexical only - no resolve() here, so two symlinked spellings
    # of one file get distinct keys (path_lookup_keys carries the resolved
    # form for matching). Add resolve() only if a real collection shows a
    # symlinked storage root.
    return stored_form(path, storage_root)


def paths_equal(a, b, storage_root) -> bool:
    """True when a and b denote the same stored file (either spelling)."""
    return canonical_key(a, storage_root) == canonical_key(b, storage_root)


def resolve_stored_path(raw, storage_root) -> Path:
    """Absolute Path for a master.db-stored path (volume-relative or not)."""
    return Path(os.path.expanduser(_volume_resolve(os.fspath(raw), storage_root)))


def is_protected_path(raw, storage_root) -> bool:
    """True when the stored path lives under <storage_root>/rekordbox/ -
    the protected zone (Collection / Collection manuelle, SPEC-UNIFIED 4)."""
    root = _storage_root(storage_root)
    try:
        rel = resolve_stored_path(raw, storage_root).relative_to(root)
    except ValueError:
        return False
    return bool(rel.parts) and rel.parts[0] == "rekordbox"


def tcc_exists(path) -> bool:
    """Existence check that is safe inside cloud folders (SPEC-01 1.5).

    macOS TCC quirk: listing a Dropbox/iCloud folder from a background
    service fails, while stat'ing an exact path succeeds. This stats the
    exact given path only - never scandir/listdir/glob of the parent - and
    issues a fresh syscall on every call (deliberately no lru_cache or other
    memoization: a file materialized by the cloud client between calls must
    be seen immediately; this is the 'fresh=True' cache bypass of SPEC-01 1.5).
    """
    return Path(os.path.expanduser(os.fspath(path))).exists()
