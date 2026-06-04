from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


# Stable, absolute default so the database is ALWAYS in the same place. The old
# default was the relative "./.local", which resolved against the current working
# directory — so launching from a different cwd (or an update that changed it)
# pointed at a different, empty database and looked like "all settings reset".
# The packaged app overrides this with RBSYNC_DATA_DIR=<userData>, the same dir.
DEFAULT_DATA_DIR = Path("~/Library/Application Support/syncbox").expanduser()

DEFAULT_REKORDBOX_DIR = Path("/Users/adriendidot/Library/Pioneer/rekordbox")
DEFAULT_STORAGE_ROOT = Path(
    "/Users/adriendidot/Library/CloudStorage/"
    "Dropbox-CloudOptionDJteam/Jockey Tricolore/Musique"
)


@dataclass(frozen=True)
class ServiceConfig:
    data_dir: Path
    api_port: int
    rekordbox_database_dir: Path
    storage_root: Path

    @property
    def app_database_path(self) -> Path:
        return self.data_dir / "syncbox.sqlite3"


def load_config() -> ServiceConfig:
    data_dir = (
        Path(os.environ.get("RBSYNC_DATA_DIR") or DEFAULT_DATA_DIR)
        .expanduser()
        .resolve()
    )
    api_port = int(os.environ.get("RBSYNC_SERVICE_PORT", "8765"))
    rekordbox_dir = Path(
        os.environ.get("RBSYNC_REKORDBOX_DATABASE_DIR", str(DEFAULT_REKORDBOX_DIR))
    ).expanduser()
    storage_root = Path(
        os.environ.get("RBSYNC_STORAGE_ROOT", str(DEFAULT_STORAGE_ROOT))
    ).expanduser()

    return ServiceConfig(
        data_dir=data_dir,
        api_port=api_port,
        rekordbox_database_dir=rekordbox_dir,
        storage_root=storage_root,
    )
