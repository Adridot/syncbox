#!/usr/bin/env python3
"""Create the drag-to-Applications base DMG from the built Syncbox.app.

Convenience installer only. It bundles the base application exactly as built
(base sidecar, no streamrip); the optional Deezer component stays separately
distributed per docs/DISTRIBUTION.md. The reproducible, scanner-verified
release artifact remains the ZIP produced by package_base_app.py.

ponytail: hdiutil UDZO is not byte-reproducible (HFS timestamps); upgrade to a
deterministic image builder only if the DMG must be hash-pinned like the ZIP.
"""

from __future__ import annotations

import json
import platform
import subprocess
import tempfile
from pathlib import Path

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
        raise SystemExit("base DMG packaging requires macOS arm64")
    if not (APP / "Contents" / "MacOS" / "syncbox-shell").is_file():
        raise SystemExit(f"missing Tauri application bundle: {APP}")

    version = json.loads((REPO / "ui" / "package.json").read_text())["version"]
    dmg = APP.parent / f"Syncbox-{version}-macos-arm64.dmg"
    dmg.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory() as staging:
        stage = Path(staging)
        # ditto preserves the ad-hoc code signature and extended attributes.
        subprocess.run(["ditto", str(APP), str(stage / APP.name)], check=True)
        (stage / "Applications").symlink_to("/Applications")
        subprocess.run(
            [
                "hdiutil", "create",
                "-volname", "Syncbox",
                "-srcfolder", str(stage),
                "-fs", "HFS+",
                "-format", "UDZO",
                "-ov",
                str(dmg),
            ],
            check=True,
        )

    print(json.dumps({"dmg": dmg.name, "size": dmg.stat().st_size},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
