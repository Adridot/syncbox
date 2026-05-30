"""Single source of truth for the app version.

package.json is the canonical version. Electron reads it (``app.getVersion()``)
and forwards it to the spawned service via ``RBSYNC_APP_VERSION``. In dev (where
the service runs from source without Electron) we fall back to reading
package.json directly by walking up from this file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_FALLBACK = "0.0.0"


def _read_package_json_version() -> str | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "package.json"
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            version = data.get("version")
            return str(version) if version else None
    return None


def app_version() -> str:
    return os.environ.get("RBSYNC_APP_VERSION") or _read_package_json_version() or _FALLBACK
