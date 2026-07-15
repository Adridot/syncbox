#!/usr/bin/env python3
"""Create the deterministic versioned base application ZIP."""

from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path

from reproducible_archive import write_tree_archive

REPO = Path(__file__).resolve().parents[1]
APP = (
    REPO
    / "shell"
    / "src-tauri"
    / "target"
    / "aarch64-apple-darwin"
    / "release"
    / "bundle"
    / "macos"
    / "Syncbox.app"
)


def main() -> int:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("base application packaging requires macOS arm64")
    if not (APP / "Contents" / "MacOS" / "syncbox-shell").is_file():
        raise SystemExit(f"missing Tauri application bundle: {APP}")

    version = json.loads((REPO / "ui" / "package.json").read_text())["version"]
    archive = APP.parent / f"Syncbox-{version}-macos-arm64.zip"
    write_tree_archive(archive, APP, APP.name)
    payload = {
        "archive": archive.name,
        "size": archive.stat().st_size,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
