"""Per-OS abstraction: app data dir, OS trash with the consent contract
(SPEC-UNIFIED 6.9, research 08 section 1).

File deletion policy is an owner decision (SPEC-UNIFIED 6.9): try the OS
trash; when the volume has no working trash (cloud folders ~50% per
send2trash#80, exFAT/network drives per #2), the fallback is PERMANENT
deletion gated on explicit prior consent - never an applicative .trash
folder (that would move files, violating 3.3). The DB layer stays fully
reversible either way (backup + soft-delete); only the audio file is at
stake here.
"""

import os
import shutil
import sys
from pathlib import Path

from send2trash import send2trash

# Deliberately independent from the macOS CFBundleIdentifier. Keeping the
# product directory stable preserves the existing database, settings, and
# encrypted OAuth secret store when the application identifier changes.
APP_NAME = "Syncbox"


def app_data_dir() -> Path:
    """OS data dir surviving app updates (SPEC-UNIFIED 3.5/6.9)."""
    if sys.platform.startswith("win"):
        base = Path(os.environ["APPDATA"])
    else:
        base = Path.home() / "Library" / "Application Support"
        # Non-macOS POSIX falls through to the macOS layout. Linux is outside
        # the v1 scope (SPEC-UNIFIED 3.7).
    return base / APP_NAME


def app_db_path() -> Path:
    return app_data_dir() / "syncbox.db"


class PermanentDeleteConsentRequired(RuntimeError):
    """The OS trash failed for this path; deleting it is irreversible.

    Raised BEFORE any unlink. The UI must show the irreversible-delete
    warning (IrreversibleDeleteModal) and re-call with consent granted;
    consent is per-call and never remembered.
    """

    message_key = "safety.permanent_delete_consent"

    def __init__(self, path: Path, cause: BaseException):
        self.path = path
        super().__init__(
            f"The volume holding {path.name!r} has no working trash; deleting "
            "it there is permanent. Explicit consent is required."
        )
        self.__cause__ = cause


def delete_file(path, *, consent_to_permanent_delete: bool = False) -> str:
    """Delete a file or validated directory, trash first.

    Returns 'trashed' or 'deleted_permanently'. Caller contract (5.4): call
    only AFTER the owning DB transaction committed.
    """
    path = Path(path)
    try:
        send2trash(str(path))
        return "trashed"
    except OSError as exc:
        if not consent_to_permanent_delete:
            raise PermanentDeleteConsentRequired(path, exc) from exc
        if path.is_symlink():
            raise ValueError(f"refusing permanent deletion of symbolic link: {path}")
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return "deleted_permanently"
