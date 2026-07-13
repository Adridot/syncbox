"""Validate fresh macOS arm64 base and optional-component artifacts.

This script is read-only. It checks the packaged runtime, architecture,
deployment target, ad-hoc signature, base-bundle exclusions, version, and
ZIP symlink preservation. Temporary component installation data is removed
before exit; the script prints one JSON result and creates no evidence files.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import plistlib
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

from packaging.markers import Marker
from packaging.utils import canonicalize_name

REPO = Path(__file__).resolve().parents[1]
MACHO_MAGICS = {
    b"\xcf\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
}
BASE_FORBIDDEN = (
    b"deemix",
    b"streamrip-2.2.0.dist-info",
    b"streamrip/client/deezer.py",
    b"site-packages/streamrip",
    b"config.toml",
    b"pony" + b"tail:",
    b"/tmp/syncbox-premium-arl",
    str(Path.home()).encode().lower(),
)
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{32,}\b"),
)
ARL_SHAPED = re.compile(
    rb"(?<![0-9a-f])[0-9a-f]{96,512}(?![0-9a-f])", re.IGNORECASE
)
ARL_ASSIGNMENT = re.compile(
    rb"(?i)(?:['\"]?(?:deezer[._-]?)?arl['\"]?|DEEZER_ARL)"
    rb"\s*(?::|=|=>)\s*['\"]?[0-9a-f]{64,512}"
)
TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".json",
    ".lock",
    ".md",
    ".py",
    ".rs",
    ".sql",
    ".toml",
    ".ts",
    ".txt",
    ".vue",
    ".yaml",
    ".yml",
}
EXPECTED_GPL_RUNTIME = {"mutagen"}


def run(*command, check=True):
    return subprocess.run(command, capture_output=True, text=True, check=check)


def mach_o_files(app: Path):
    for path in app.rglob("*"):
        if path.is_file() and not path.is_symlink():
            try:
                if path.read_bytes()[:4] in MACHO_MAGICS:
                    yield path
            except OSError:
                continue


def minimum_version(path: Path) -> tuple[int, ...]:
    output = run("xcrun", "vtool", "-show-build", str(path)).stdout
    match = re.search(r"\bminos\s+([0-9.]+)", output)
    if not match:
        raise AssertionError(f"no macOS deployment target: {path}")
    return tuple(int(part) for part in match.group(1).split("."))


def validate_archive(app: Path, archive: Path) -> int:
    expected_root = app.name
    source_nodes = {
        f"{expected_root}/{path.relative_to(app)}": path
        for path in app.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    with zipfile.ZipFile(archive) as bundle:
        nodes = {item.filename: item for item in bundle.infolist() if not item.is_dir()}
        assert set(nodes) == set(source_nodes), "ZIP content does not match the app tree"
        archived_links = {
            name
            for name, item in nodes.items()
            if stat.S_IFMT(item.external_attr >> 16) == stat.S_IFLNK
        }
        for name, path in source_nodes.items():
            expected = os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
            assert bundle.read(name) == expected, f"ZIP payload mismatch: {name}"
            archived_mode = stat.S_IMODE(nodes[name].external_attr >> 16)
            assert archived_mode == stat.S_IMODE(path.lstat().st_mode), (
                f"ZIP mode mismatch: {name}"
            )
    source_links = {name for name, path in source_nodes.items() if path.is_symlink()}
    assert archived_links == source_links
    return len(source_links)


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root)).encode()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        if path.is_symlink():
            digest.update(b"L" + os.readlink(path).encode())
        elif path.is_file():
            digest.update(b"F" + path.read_bytes())
    return digest.hexdigest()


def runtime_license_inventory() -> dict[str, dict[str, str]]:
    lock = tomllib.loads((REPO / "sidecar/uv.lock").read_text())
    packages = {
        canonicalize_name(package["name"]): package for package in lock["package"]
    }
    pending = [
        canonicalize_name(dep["name"])
        for dep in packages["syncbox"]["dependencies"]
    ]
    runtime = set()
    while pending:
        name = pending.pop()
        if name in runtime:
            continue
        runtime.add(name)
        for dependency in packages[name].get("dependencies", []):
            if dependency.get("marker") and not Marker(dependency["marker"]).evaluate():
                continue
            pending.append(canonicalize_name(dependency["name"]))

    installed = {
        canonicalize_name(dist.metadata["Name"]): dist
        for dist in importlib.metadata.distributions()
    }
    inventory = {}
    for name in sorted(runtime):
        dist = installed.get(name)
        assert dist is not None, f"locked runtime distribution is not installed: {name}"
        expected_version = packages[name]["version"]
        assert dist.version == expected_version, (
            f"runtime version drift for {name}: {dist.version} != {expected_version}"
        )
        license_name = (
            dist.metadata.get("License-Expression")
            or dist.metadata.get("License")
            or "UNKNOWN"
        ).splitlines()[0]
        assert license_name != "UNKNOWN", f"runtime license is unknown: {name}"
        inventory[name] = {"version": dist.version, "license": license_name}
    return inventory


def validate_source_secrets() -> int:
    skipped = {
        ".git",
        ".idea",
        ".venv",
        "build",
        "dist",
        "node_modules",
        "target",
        "testdata",
    }
    checked = 0
    for path in REPO.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in skipped for part in path.relative_to(REPO).parts):
            continue
        raw = path.read_bytes()
        for pattern in SECRET_PATTERNS:
            assert not pattern.search(raw), f"secret-shaped value in source file {path}"
        assert not ARL_SHAPED.search(raw), f"ARL-shaped value in source file {path}"
        assert not ARL_ASSIGNMENT.search(raw), f"ARL value in source file {path}"
        checked += 1
    return checked


def validate_optional_component(archive: Path, manifest_path: Path) -> dict:
    archive = archive.resolve(strict=True)
    manifest_path = manifest_path.resolve(strict=True)
    manifest = json.loads(manifest_path.read_text())
    assert archive.name == manifest["archive"]
    assert archive.stat().st_size == manifest["size"]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["sha256"]
    assert manifest["platform"] == "macos" and manifest["architecture"] == "arm64"

    sys.path.insert(0, str(REPO / "sidecar/src"))
    from syncbox import acquisition

    previous = os.environ.get(acquisition.COMPONENT_ARCHIVE_ENV)
    os.environ[acquisition.COMPONENT_ARCHIVE_ENV] = str(archive)
    try:
        with tempfile.TemporaryDirectory(prefix="syncbox-component-scan-") as raw_data:
            status = acquisition.install_component(raw_data)
            assert status["installed"] is True
            root = acquisition.component_root(raw_data)
            executable = acquisition.component_executable(raw_data)
            check = json.loads(run(str(executable), "--check").stdout)
            assert check["result"] == "CHECK_PASSED"
            assert check["streamrip_commit"] == manifest["streamrip_commit"]
            assert check["streamrip_version"] == manifest["streamrip_version"]
            assert check["certifi_version"] == manifest["certifi_version"]

            help_text = run(str(executable), "--help").stdout.lower()
            assert "soundcloud" not in help_text and "ffmpeg" not in help_text
            assert not any("ffmpeg" in path.name.lower() for path in root.rglob("*"))
            assert (root / "_internal/THIRD_PARTY_NOTICES.txt").is_file()
            assert (
                root
                / f"_internal/streamrip-{manifest['streamrip_version']}.dist-info/licenses/LICENSE"
            ).is_file()

            native = list(mach_o_files(root))
            assert native, "optional component has no Mach-O files"
            targets = []
            for path in native:
                description = run("file", str(path)).stdout
                assert "arm64" in description and "x86_64" not in description, description
                targets.append(minimum_version(path))
            effective_minimum = max(targets)
            assert effective_minimum <= (14, 0), effective_minimum

            for path in root.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    raw = path.read_bytes()
                    assert str(Path.home()).encode() not in raw, (
                        f"local builder path in optional component: {path}"
                    )
                    for pattern in SECRET_PATTERNS:
                        assert not pattern.search(raw), f"secret-shaped value in {path}"
                    if path.suffix.lower() in TEXT_SUFFIXES:
                        assert not ARL_SHAPED.search(raw), f"ARL-shaped value in {path}"
                        assert not ARL_ASSIGNMENT.search(raw), f"ARL value in {path}"

            modules = run(
                str(Path(os.environ.get("PYI_ARCHIVE_VIEWER", "pyi-archive_viewer"))),
                "-r",
                "-b",
                str(executable),
            ).stdout.lower()
            assert "streamrip.client.deezer" in modules
            assert "cryptodome.cipher.blowfish" in modules
            for forbidden in (
                "streamrip.client.qobuz",
                "streamrip.client.soundcloud",
                "streamrip.client.tidal",
                "streamrip.rip.cli",
                "streamrip.rip.main",
            ):
                assert forbidden not in modules, forbidden
            return {
                "archive": archive.name,
                "archive_bytes": archive.stat().st_size,
                "archive_sha256": manifest["sha256"],
                "installed_check": check,
                "mach_o_files": len(native),
                "effective_minimum_macos": ".".join(map(str, effective_minimum)),
                "streamrip_license_present": True,
                "ffmpeg_binary": False,
                "soundcloud_interface": False,
                "provider_client_modules": ["deezer"],
            }
    finally:
        if previous is None:
            os.environ.pop(acquisition.COMPONENT_ARCHIVE_ENV, None)
        else:
            os.environ[acquisition.COMPONENT_ARCHIVE_ENV] = previous


def validate(
    app: Path,
    archive: Path | None,
    component_archive: Path | None,
    component_manifest: Path,
) -> dict:
    app = app.resolve(strict=True)
    assert app.suffix == ".app"
    info_path = app / "Contents/Info.plist"
    shell = app / "Contents/MacOS/syncbox-shell"
    sidecar = app / "Contents/Resources/sidecar/syncbox-sidecar"
    migrations = app / "Contents/Resources/sidecar/_internal/syncbox/migrations"
    ca_file = app / "Contents/Resources/sidecar/_internal/certifi/cacert.pem"
    embedded_manifest = (
        app / "Contents/Resources/sidecar/_internal/syncbox/optional_component.json"
    )
    for required in (info_path, shell, sidecar, migrations, ca_file, embedded_manifest):
        assert required.exists(), f"missing packaged resource: {required}"
    assert embedded_manifest.read_bytes() == component_manifest.resolve(strict=True).read_bytes()
    component_name = json.loads(embedded_manifest.read_text())["component"]
    assert not any(path.name == component_name for path in app.rglob("*"))

    canonical = json.loads((REPO / "ui/package.json").read_text())["version"]
    with info_path.open("rb") as handle:
        info = plistlib.load(handle)
    assert info["CFBundleShortVersionString"] == canonical
    assert info["CFBundleVersion"] == canonical
    assert info["LSMinimumSystemVersion"] == "14.0"

    native = list(mach_o_files(app))
    assert native, "no Mach-O files found"
    deployment_targets = []
    for path in native:
        description = run("file", str(path)).stdout
        assert "arm64" in description and "x86_64" not in description, description
        deployment_targets.append(minimum_version(path))
    effective_minimum = max(deployment_targets)
    assert effective_minimum <= (14, 0), effective_minimum

    runtime = json.loads(run(str(sidecar), "--packaging-check").stdout)
    assert runtime["ok"] is True and runtime["architecture"] == "arm64"
    assert runtime["streamrip_importable"] is False

    verification = run("codesign", "--verify", "--deep", "--strict", str(app))
    assert verification.returncode == 0
    signature = run("codesign", "-dv", "--verbose=4", str(app), check=False).stderr
    assert "Signature=adhoc" in signature
    assert "Authority=" not in signature
    assert "TeamIdentifier=not set" in signature

    for path in app.rglob("*"):
        if path.is_file() and not path.is_symlink():
            raw = path.read_bytes()
            data = raw.lower()
            for marker in BASE_FORBIDDEN:
                assert marker not in data, f"forbidden marker {marker!r} in {path}"
            for pattern in SECRET_PATTERNS:
                assert not pattern.search(raw), f"secret-shaped value in {path}"
            if path.suffix.lower() in TEXT_SUFFIXES:
                assert not ARL_SHAPED.search(raw), f"ARL-shaped value in {path}"
                assert not ARL_ASSIGNMENT.search(raw), f"ARL value in {path}"

    archive_modules = run(
        str(Path(os.environ.get("PYI_ARCHIVE_VIEWER", "pyi-archive_viewer"))),
        "-r",
        "-b",
        str(sidecar),
    ).stdout.lower()
    assert "streamrip" not in archive_modules
    assert "deemix" not in archive_modules

    licenses = runtime_license_inventory()
    forbidden_packages = {
        name for name in licenses if any(term in name for term in ("streamrip", "deemix", "deezer"))
    }
    assert not forbidden_packages, sorted(forbidden_packages)
    gpl_packages = {
        name for name, metadata in licenses.items() if "gpl" in metadata["license"].lower()
    }
    assert gpl_packages == EXPECTED_GPL_RUNTIME, sorted(gpl_packages)

    symlinks = validate_archive(app, archive.resolve(strict=True)) if archive else None
    component = (
        validate_optional_component(component_archive, component_manifest)
        if component_archive
        else None
    )
    source_secret_files = validate_source_secrets()
    return {
        "ok": True,
        "version": canonical,
        "architecture": "arm64",
        "declared_minimum_macos": info["LSMinimumSystemVersion"],
        "effective_minimum_macos": ".".join(map(str, effective_minimum)),
        "mach_o_files": len(native),
        "runtime_packages": runtime["packages"],
        "app_bytes": sum(
            path.stat().st_size
            for path in app.rglob("*")
            if path.is_file() and not path.is_symlink()
        ),
        "archive_bytes": archive.stat().st_size if archive else None,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest() if archive else None,
        "archive_content_match": archive is not None,
        "archive_symlinks": symlinks,
        "app_tree_sha256": tree_hash(app),
        "developer_id": False,
        "gpl_runtime_packages": sorted(gpl_packages),
        "runtime_licenses": licenses,
        "notarized": False,
        "streamrip_component_in_base": False,
        "streamrip_importable_in_base": runtime["streamrip_importable"],
        "optional_component": component,
        "source_secret_files_scanned": source_secret_files,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("app", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--component-archive", type=Path)
    parser.add_argument(
        "--component-manifest",
        type=Path,
        default=REPO / "sidecar/src/syncbox/optional_component.json",
    )
    args = parser.parse_args()
    result = validate(
        args.app,
        args.archive,
        args.component_archive,
        args.component_manifest,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
