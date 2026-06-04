"""Test isolation: point every config path at throwaway temp dirs.

`app.main` binds a module-level ``LocalDatabase(config.app_database_path)`` at
import time, and ``load_config()`` reads these env vars. Forcing them to temp
dirs *before any app module is imported* guarantees a test (e.g. an endpoint
test that imports ``app.main``) can never read or write the real user data at
``~/Library/Application Support/syncbox`` or the real Rekordbox master.db.

Tests that need to exercise the default (e.g. test_default_data_dir) use
``monkeypatch.delenv`` to drop the override for their own scope.
"""

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="syncbox-tests-"))
for _sub, _var in (
    ("data", "RBSYNC_DATA_DIR"),
    ("rekordbox", "RBSYNC_REKORDBOX_DATABASE_DIR"),
    ("storage", "RBSYNC_STORAGE_ROOT"),
):
    _dir = _TMP / _sub
    _dir.mkdir(parents=True, exist_ok=True)
    os.environ[_var] = str(_dir)
