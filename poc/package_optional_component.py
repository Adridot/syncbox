#!/usr/bin/env python3
"""Create the versioned optional-component ZIP and pinned base manifest."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import runpy
import stat
import tomllib
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROJECT = REPO / "optional-component"
COMPONENT = "syncbox-deezer-component"
BUNDLE = PROJECT / "dist" / COMPONENT
MANIFEST = REPO / "sidecar" / "src" / "syncbox" / "optional_component.json"
RELEASE_REPOSITORY = "https://github.com/Adridot/syncbox"


def _write_node(bundle: zipfile.ZipFile, path: Path) -> None:
    relative = f"{COMPONENT}/{path.relative_to(BUNDLE).as_posix()}"
    details = path.lstat()
    info = zipfile.ZipInfo(relative, (1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    if path.is_symlink():
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        payload = os.readlink(path).encode()
    else:
        info.external_attr = (stat.S_IFREG | stat.S_IMODE(details.st_mode)) << 16
        payload = path.read_bytes()
    info.compress_type = zipfile.ZIP_DEFLATED
    bundle.writestr(info, payload, compresslevel=9)


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
        str(REPO / "poc" / "run_b1_deezer_acquisition.py"),
        run_name="syncbox_component_metadata",
    )
    archive = PROJECT / "dist" / f"{COMPONENT}-{version}-macos-arm64.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", allowZip64=True) as bundle:
        for path in sorted(BUNDLE.rglob("*")):
            if path.is_file() or path.is_symlink():
                _write_node(bundle, path)

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
    }
    temporary = MANIFEST.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, MANIFEST)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
