"""Mutation guard against a running Rekordbox (SPEC-UNIFIED 3.1 / 5.1).

Writing master.db while rekordbox or rekordboxAgent is open can corrupt the
user's collection sync state, so detection is strict and re-implemented over
psutil rather than relying on pyrekordbox's lax substring helper (which
matches lookalikes such as 'rekordbox_helper'). rekordboxAgent survives
closing the Rekordbox window and is always checked alongside the main app.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psutil

__all__ = ["MutationBlockedError", "assert_mutation_ready", "is_rekordbox_running"]

# Exact Windows process names, compared case-insensitively. Name-based
# matching is exact-set only so 'rekordbox_helper.exe' can never match.
_WINDOWS_PROCESS_NAMES = frozenset({"rekordbox.exe", "rekordboxagent.exe"})


class MutationBlockedError(RuntimeError):
    """A mutation was requested while Rekordbox (or its agent) is running.

    The message is user-facing; per SPEC-UNIFIED 3.1/5.1 it must never leak
    a PID, an '/Applications/' path, or a '--type=' process flag. The stable
    ``message_key`` lets the UI localize it (SPEC-UNIFIED 3.8) while the
    English text serves as fallback.
    """

    message_key = "safety.mutation_blocked"

    def __init__(self) -> None:
        super().__init__(
            "Rekordbox looks like it is still running. Please quit Rekordbox "
            "completely - including its background helper, which can keep "
            "running after the window is closed - and try again."
        )


def _matches_macos_exe(exe_path: str) -> bool:
    # Path-based rule (case-insensitive): anything running out of the
    # rekordbox/rekordboxAgent app bundles, or a bare binary with the exact
    # basename. A matching process *name* alone is not enough on macOS.
    p = exe_path.lower()
    return (
        "/rekordbox.app/" in p
        or "/rekordboxagent.app/" in p
        or p.endswith("/rekordbox")
        or p.endswith("/rekordboxagent")
    )


def is_rekordbox_running() -> bool:
    """Return True if rekordbox or rekordboxAgent is running (strict filter)."""
    on_windows = sys.platform.startswith("win")
    # ponytail: non-Windows platforms reuse the macOS path rule; Linux is out
    # of scope (SPEC-UNIFIED 3.7 targets macOS + Windows). Revisit only if a
    # Linux target ever appears.
    for proc in psutil.process_iter(attrs=["name", "exe"]):
        try:
            info = proc.info
            if on_windows:
                if (info.get("name") or "").lower() in _WINDOWS_PROCESS_NAMES:
                    return True
            elif _matches_macos_exe(info.get("exe") or ""):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # Processes vanish or deny access mid-iteration; skipping one must
            # never abort the scan (a missed lookalike is harmless, an aborted
            # scan would be treated as an error upstream).
            continue
    return False


def assert_mutation_ready(db_path) -> None:
    """Step (a) of the _mutate unit-of-work (SPEC-01 1.2): RB closed, DB exists.

    Raises MutationBlockedError if rekordbox or rekordboxAgent runs (checked
    first: the friendly block message wins over the developer-facing missing
    file error), FileNotFoundError if db_path is missing.
    """
    if is_rekordbox_running():
        raise MutationBlockedError()
    # Exact-path stat (TCC-safe: never lists the parent, same rule as
    # paths.tcc_exists) — but stat, not exists(): a database that exists yet
    # is unreadable (macOS TCC denied the folder) must NOT be misreported as
    # "not found", which would send the user hunting for a missing file
    # instead of granting file access.
    resolved = Path(db_path).expanduser()
    try:
        os.stat(resolved)
    except FileNotFoundError:
        raise FileNotFoundError(f"Rekordbox database not found: {resolved}") from None
    except PermissionError as exc:
        raise PermissionError(
            f"Rekordbox database exists but is not readable (file access "
            f"permission, e.g. macOS folder access): {resolved}"
        ) from exc
