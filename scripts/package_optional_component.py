#!/usr/bin/env python3
"""Create the versioned optional-component ZIP and pinned base manifest."""

from __future__ import annotations

import hashlib
import json
import platform
import runpy
import tomllib
from pathlib import Path

from reproducible_archive import write_tree_archive

REPO = Path(__file__).resolve().parents[1]
PROJECT = REPO / "optional-component"
COMPONENT = "syncbox-deezer-component"
BUNDLE = PROJECT / "dist" / COMPONENT
MANIFEST = REPO / "sidecar" / "src" / "syncbox" / "optional_component.json"
RELEASE_REPOSITORY = "https://github.com/Adridot/syncbox"


def main() -> int:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("optional component packaging requires macOS arm64")
    if not (BUNDLE / COMPONENT).is_file():
        raise SystemExit(f"missing PyInstaller onedir: {BUNDLE}")

    project = tomllib.loads((PROJECT / "pyproject.toml").read_text())
    version = project["project"]["version"]
    canonical = json.loads((REPO / "ui" / "package.json").read_text())["version"]
    if version != canonical:
        raise SystemExit(f"component version {version} != application {canonical}")

    runner = runpy.run_path(
        str(REPO / "scripts" / "run_b1_deezer_acquisition.py"),
        run_name="syncbox_component_metadata",
    )
    archive = PROJECT / "dist" / f"{COMPONENT}-{version}-macos-arm64.zip"
    write_tree_archive(archive, BUNDLE, COMPONENT)

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    payload = {
        "schema": 1,
        "component": COMPONENT,
        "component_version": version,
        "platform": "macos",
        "architecture": "arm64",
        "archive": archive.name,
        "root": COMPONENT,
        "executable": COMPONENT,
        "size": archive.stat().st_size,
        "sha256": digest,
        "download_url": (
            f"{RELEASE_REPOSITORY}/releases/download/v{version}/{archive.name}"
        ),
        "streamrip_version": runner["STREAMRIP_VERSION"],
        "streamrip_commit": runner["STREAMRIP_COMMIT"],
        "certifi_version": "2026.6.17",
        "python_version": "3.13.11",
        "pillow_version": runner["PILLOW_VERSION"],
        "pillow_wheel": runner["PILLOW_WHEEL"],
        "pillow_wheel_sha256": runner["PILLOW_WHEEL_SHA256"],
    }
    temporary = MANIFEST.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(MANIFEST)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
