"""Health diagnostics ("Doctor") aggregating the app's preconditions.

Each check returns ok / warn / error with a human detail and an optional hint.
The report status is the worst individual status.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .acquisition import get_deemix_status
from .db import LocalDatabase
from .logging_setup import get_logger
from .models import DiagnosticCheck, DiagnosticsReport

logger = get_logger("diagnostics")

LOW_DISK_WARN_GB = 5.0


def _worst(statuses: list[str]) -> str:
    if "error" in statuses:
        return "error"
    if "warn" in statuses:
        return "warn"
    return "ok"


def _check_path(label: str, key: str, raw: str | None) -> DiagnosticCheck:
    if not raw:
        return DiagnosticCheck(
            key=key, label=label, status="warn", detail="Not configured.",
            hint="Set this folder in Settings.",
        )
    path = Path(raw).expanduser()
    try:
        exists = path.exists()
        is_dir = path.is_dir() if exists else False
    except OSError as exc:
        return DiagnosticCheck(
            key=key, label=label, status="error", detail=f"Cannot access: {exc}",
        )
    if not exists:
        return DiagnosticCheck(
            key=key, label=label, status="error", detail=f"Missing: {raw}",
            hint="Create the folder or fix the path in Settings.",
        )
    if not is_dir:
        return DiagnosticCheck(
            key=key, label=label, status="error", detail=f"Not a directory: {raw}",
        )
    return DiagnosticCheck(key=key, label=label, status="ok", detail=str(path))


async def run_diagnostics(database: LocalDatabase, adapter: Any) -> DiagnosticsReport:
    checks: list[DiagnosticCheck] = []

    # --- Rekordbox database ----------------------------------------------
    try:
        stats = adapter.collection_stats()
    except Exception as exc:  # pragma: no cover - defensive
        stats = {"available": False, "reason": str(exc)}
    if stats.get("available"):
        checks.append(
            DiagnosticCheck(
                key="rekordbox_db", label="Rekordbox database", status="ok",
                detail=f"{stats.get('total', 0)} tracks readable.",
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                key="rekordbox_db", label="Rekordbox database", status="error",
                detail=str(stats.get("reason") or "Collection unavailable."),
                hint="Open Rekordbox once so the key is cached, then retry.",
            )
        )

    # --- Rekordbox running (blocks mutations) ----------------------------
    try:
        status = adapter.status()
        running = bool(getattr(status, "rekordbox_running", False))
    except Exception:
        running = False
    checks.append(
        DiagnosticCheck(
            key="rekordbox_running", label="Mutations",
            status="warn" if running else "ok",
            detail="Rekordbox is running — writes are blocked." if running
            else "Rekordbox is closed — writes allowed.",
            hint="Quit Rekordbox before applying changes." if running else None,
        )
    )

    # --- Storage paths ----------------------------------------------------
    try:
        layout = adapter.storage_layout()
        checks.append(_check_path("Storage root", "storage_root", layout.root))
        checks.append(_check_path("Permanent collection", "permanent", layout.permanent))
        checks.append(_check_path("Events folder", "events", layout.events))
        storage_root = layout.root
    except Exception as exc:
        checks.append(
            DiagnosticCheck(
                key="storage_root", label="Storage root", status="error",
                detail=str(exc),
            )
        )
        storage_root = None

    # --- Disk space -------------------------------------------------------
    if storage_root:
        try:
            usage = shutil.disk_usage(storage_root)
            free_gb = usage.free / (1024 ** 3)
            checks.append(
                DiagnosticCheck(
                    key="disk_space", label="Disk space",
                    status="warn" if free_gb < LOW_DISK_WARN_GB else "ok",
                    detail=f"{free_gb:.1f} GB free.",
                    hint="Low space may break downloads." if free_gb < LOW_DISK_WARN_GB else None,
                )
            )
        except OSError as exc:
            checks.append(
                DiagnosticCheck(
                    key="disk_space", label="Disk space", status="warn",
                    detail=f"Could not read free space: {exc}",
                )
            )

    # --- Deemix -----------------------------------------------------------
    try:
        deemix = await get_deemix_status()
        if deemix.available and deemix.authenticated:
            deemix_check = DiagnosticCheck(
                key="deemix", label="Deemix", status="ok", detail="Available and authenticated.",
            )
        elif deemix.available:
            deemix_check = DiagnosticCheck(
                key="deemix", label="Deemix", status="warn",
                detail=deemix.detail or "Available but not authenticated.",
                hint="Sign in to Deezer in Deemix.",
            )
        else:
            deemix_check = DiagnosticCheck(
                key="deemix", label="Deemix", status="warn",
                detail=deemix.detail or "Offline.",
                hint="Start Deemix to enable downloads.",
            )
    except Exception as exc:
        deemix_check = DiagnosticCheck(
            key="deemix", label="Deemix", status="warn", detail=str(exc),
        )
    checks.append(deemix_check)

    # --- Spotify auth -----------------------------------------------------
    refresh_token = database.get_setting("spotify_refresh_token")
    client_id = database.get_setting("spotify_client_id")
    if refresh_token:
        spotify_check = DiagnosticCheck(
            key="spotify", label="Spotify", status="ok", detail="Connected.",
        )
    elif client_id:
        spotify_check = DiagnosticCheck(
            key="spotify", label="Spotify", status="warn",
            detail="Client configured but not authorized.",
            hint="Authorize Spotify in Settings.",
        )
    else:
        spotify_check = DiagnosticCheck(
            key="spotify", label="Spotify", status="warn",
            detail="Not configured.", hint="Add a Spotify client and connect in Settings.",
        )
    checks.append(spotify_check)

    # --- Backups ----------------------------------------------------------
    try:
        backups = adapter.list_backups()
        checks.append(
            DiagnosticCheck(
                key="backups", label="Backups", status="ok",
                detail=f"{len(backups)} Rekordbox backup(s) available.",
            )
        )
    except Exception as exc:
        checks.append(
            DiagnosticCheck(
                key="backups", label="Backups", status="warn", detail=str(exc),
            )
        )

    overall = _worst([check.status for check in checks])
    return DiagnosticsReport(
        status=overall,
        generatedAt=datetime.now(timezone.utc).isoformat(),
        checks=checks,
    )
