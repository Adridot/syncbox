"""Pure path / volume helpers + the CollectionPath value object.

No Rekordbox-DB coupling: these operate on plain strings/Path objects and the
FolderPath attribute of content rows, so they are trivially unit-testable.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def safe_timestamp() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y%m%d-%H%M%S")


# --- Rekordbox volume-relative path handling -------------------------------
# Rekordbox stores collection paths relative to a named volume, e.g.
# "/Musique/rekordbox/Collection/x.mp3" where the volume "Musique" maps to the
# storage root (".../Jockey Tricolore/Musique"). Keeping app-managed files in
# this same format makes them uniform with Rekordbox's native entries.


def volume_name(storage_root: Path | str) -> str:
    return Path(str(storage_root)).name


def to_volume_relative(path: Path | str, storage_root: Path | str) -> str:
    """Convert a full path under storage_root to "/<volume>/<rest>"; otherwise
    return it unchanged."""
    full = str(Path(str(path)))
    root = str(Path(str(storage_root)))
    if full == root:
        return "/" + volume_name(storage_root)
    prefix = root.rstrip("/") + "/"
    if full.startswith(prefix):
        return "/" + volume_name(storage_root) + "/" + full[len(prefix):]
    return full


def resolve_volume_path(folder_path: str, storage_root: Path | str) -> str:
    """Resolve a stored "/<volume>/<rest>" path back to the real full path under
    storage_root; otherwise return it unchanged."""
    if not folder_path:
        return folder_path
    marker = "/" + volume_name(storage_root)
    if folder_path == marker:
        return str(Path(str(storage_root)))
    if folder_path.startswith(marker + "/"):
        return str(Path(str(storage_root))) + folder_path[len(marker):]
    return folder_path


@dataclass(frozen=True)
class CollectionPath:
    """A track file location that Rekordbox stores volume-relative
    ("/<volume>/rekordbox/Collection/x.mp3") while the app handles it absolute
    ("/Users/.../Collection/x.mp3").

    Bundles both representations and their equality so apply-time dedup never
    misses across the two forms — the bug class that produced duplicate
    Collection entries before. Delegates to the proven free functions above.
    """

    raw: str
    storage_root: str

    @classmethod
    def of(cls, path: Path | str, storage_root: Path | str) -> "CollectionPath":
        return cls(str(path), str(storage_root))

    @property
    def absolute(self) -> str:
        """The real on-disk path (resolves a volume-relative ``raw``)."""
        return resolve_volume_path(self.raw, self.storage_root)

    @property
    def volume_relative(self) -> str:
        """The Rekordbox-style ``/<volume>/…`` form (for storage in FolderPath)."""
        return to_volume_relative(self.absolute, self.storage_root)

    def lookup_keys(self) -> list[str]:
        """Every equivalent string key for content dedup (both forms)."""
        return path_lookup_keys(self.raw, self.storage_root)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CollectionPath):
            return NotImplemented
        return self.absolute == other.absolute

    def __hash__(self) -> int:
        return hash(self.absolute)


def content_path_lookup(
    contents: Any, storage_root: Path | str | None = None
) -> dict[str, Any]:
    lookup = {}
    for content in contents:
        for key in path_lookup_keys(getattr(content, "FolderPath", ""), storage_root):
            lookup[key] = content
    return lookup


def find_content_by_path(
    lookup: dict[str, Any], path: Path, storage_root: Path | str | None = None
) -> Any | None:
    for key in path_lookup_keys(path, storage_root):
        content = lookup.get(key)
        if content is not None:
            return content
    return None


def path_lookup_keys(
    path: Path | str, storage_root: Path | str | None = None
) -> list[str]:
    """Return every equivalent string form of ``path`` used for content dedup.

    Rekordbox stores ``FolderPath`` volume-relative (``/<volume>/rekordbox/…``)
    while the app handles absolute staging paths (``/Users/…``). To make the two
    dedup against each other, every key set includes BOTH the absolute form
    (under ``storage_root``) and the volume-relative form when ``storage_root``
    is provided.
    """
    if not path:
        return []
    raw = str(path)
    keys: list[str] = []

    def add(value: str) -> None:
        if value and value not in keys:
            keys.append(value)

    candidates = [raw]
    if storage_root is not None:
        # A volume-relative input ("/<volume>/…") must be resolved to its real
        # absolute path first; otherwise Path().resolve() treats it as a
        # filesystem-root path and it never matches a staging file.
        candidates.append(resolve_volume_path(raw, storage_root))

    for candidate in candidates:
        path_object = Path(candidate).expanduser()
        add(str(path_object))
        try:
            add(str(path_object.resolve()))
        except OSError:
            pass
        if storage_root is not None:
            add(to_volume_relative(path_object, storage_root))
    return keys


def path_is_under_roots(path: str, roots: list[Path]) -> bool:
    if not path:
        return False
    try:
        resolved_path = Path(path).expanduser().resolve()
    except OSError:
        resolved_path = Path(path).expanduser()
    for root in roots:
        try:
            resolved_root = root.expanduser().resolve()
        except OSError:
            resolved_root = root.expanduser()
        if resolved_path == resolved_root or resolved_root in resolved_path.parents:
            return True
    return False


def move_to_permanent(source: Path, permanent_root: Path) -> Path:
    permanent_root.mkdir(parents=True, exist_ok=True)
    target = permanent_root / source.name
    if target.exists() and target.resolve() != source.resolve():
        stem = source.stem
        suffix = source.suffix
        counter = 2
        while target.exists():
            target = permanent_root / f"{stem}-{counter}{suffix}"
            counter += 1
    if source.resolve() != target.resolve():
        shutil.move(str(source), str(target))
    return target
