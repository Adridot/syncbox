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
    "classify_ownership",
    "path_lookup_keys",
    "paths_equal",
    "resolve_stored_path",
    "stored_form",
    "tcc_exists",
]

# The Syncbox data directory under the storage root. Only its events and inbox
# subdirectories contain app-managed audio; backups are not audio content.
SYNC_DIR_NAME = "_syncbox"


def _storage_root(storage_root) -> Path:
    root = Path(os.path.expanduser(os.fspath(storage_root)))
    if not root.is_absolute():
        root = Path.cwd() / root
    return root.resolve(strict=False)


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
    form maps to itself. Non-strict canonicalization keeps missing staging
    paths stable while preventing ``..`` or symlink spellings from bypassing
    storage-root boundaries.
    """
    root = _storage_root(storage_root)
    p = resolve_stored_path(path, storage_root)
    try:
        rel = p.relative_to(root)
    except ValueError:
        return str(p)
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
    resolved = str(resolve_stored_path(expanded, storage_root))
    volume_relative = stored_form(resolved, storage_root)
    return tuple(
        dict.fromkeys((raw_s, volume_resolved, expanded, resolved, volume_relative))
    )


def canonical_key(path, storage_root) -> str:
    """One canonical string per file: volume-relative == absolute (3.2).

    Safe as a dict/set key: equal paths yield equal (hence hash-equal) keys.
    """
    return str(resolve_stored_path(path, storage_root))


def paths_equal(a, b, storage_root) -> bool:
    """True when a and b denote the same stored file (either spelling)."""
    return canonical_key(a, storage_root) == canonical_key(b, storage_root)


def resolve_stored_path(raw, storage_root) -> Path:
    """Absolute Path for a master.db-stored path (volume-relative or not)."""
    path = Path(os.path.expanduser(_volume_resolve(os.fspath(raw), storage_root)))
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve(strict=False)


def classify_ownership(raw, storage_root) -> str:
    """Classify audio ownership from its canonical storage location."""
    root = _storage_root(storage_root)
    try:
        rel = resolve_stored_path(raw, storage_root).relative_to(root)
    except ValueError:
        return "external"
    if rel.parts and rel.parts[0] == "rekordbox":
        return "permanent_library"
    if (
        len(rel.parts) >= 2
        and rel.parts[0] == SYNC_DIR_NAME
        and rel.parts[1] in {"events", "inbox"}
    ):
        return "app_managed"
    return "external"


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
