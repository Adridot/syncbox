"""Optional Deezer acquisition boundary.

The base sidecar never imports streamrip. A separately distributed, pinned
component is installed into app data only after explicit enablement, then
invoked as a short-lived subprocess with a one-shot credential file.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import ssl
import stat
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

import certifi

from syncbox.safety.paths import SYNC_DIR_NAME

DEEZER_ARL_SECRET = "deezer.arl"
STREAMRIP_VERSION = "2.2.0"
STREAMRIP_COMMIT = "189acda489927719aa8591f6acdd7d67aecf929b"
CERTIFI_VERSION = "2026.6.17"
COMPONENT_NAME = "syncbox-deezer-component"
COMPONENT_ARCHIVE_ENV = "SYNCBOX_DEEZER_COMPONENT_ARCHIVE"
MAX_COMPONENT_BYTES = 512 * 1024 * 1024
MAX_UNPACKED_BYTES = 1024 * 1024 * 1024
ISRC_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")
ARL_PATTERN = re.compile(r"^[0-9a-fA-F]{64,512}$")


def validate_arl(value: str) -> str:
    arl = (value or "").strip()
    if not ARL_PATTERN.fullmatch(arl):
        raise ValueError("Deezer ARL must be a 64-512 character hex token")
    return arl


def normalize_isrc(value: str | None) -> str:
    isrc = re.sub(r"[-\s]", "", value or "").upper()
    if not ISRC_PATTERN.fullmatch(isrc):
        raise ValueError("track needs a valid ISRC for Deezer acquisition")
    return isrc


def component_root(data_dir) -> Path:
    return Path(data_dir) / "optional" / "streamrip-deezer" / STREAMRIP_COMMIT


def component_executable(data_dir) -> Path:
    return component_root(data_dir) / COMPONENT_NAME


def _marker_path(data_dir) -> Path:
    return component_root(data_dir) / "syncbox-component.json"


def _component_manifest() -> dict:
    path = Path(__file__).with_name("optional_component.json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise RuntimeError("optional component manifest is unavailable") from error

    required = {
        "schema",
        "component",
        "component_version",
        "platform",
        "architecture",
        "archive",
        "root",
        "executable",
        "size",
        "sha256",
        "download_url",
        "streamrip_version",
        "streamrip_commit",
        "certifi_version",
    }
    if set(payload) != required:
        raise RuntimeError("optional component manifest fields are invalid")
    expected = {
        "schema": 1,
        "component": COMPONENT_NAME,
        "platform": "macos",
        "architecture": "arm64",
        "root": COMPONENT_NAME,
        "executable": COMPONENT_NAME,
        "streamrip_version": STREAMRIP_VERSION,
        "streamrip_commit": STREAMRIP_COMMIT,
        "certifi_version": CERTIFI_VERSION,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise RuntimeError("optional component manifest does not match this build")
    if (
        not isinstance(payload["size"], int)
        or not 0 < payload["size"] <= MAX_COMPONENT_BYTES
    ):
        raise RuntimeError("optional component archive size is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", payload["sha256"]):
        raise RuntimeError("optional component SHA-256 is invalid")
    if payload["archive"] != (
        f"{COMPONENT_NAME}-{payload['component_version']}-macos-arm64.zip"
    ):
        raise RuntimeError("optional component archive name is invalid")
    parsed = urllib.parse.urlparse(payload["download_url"])
    expected_path = (
        f"/Adridot/syncbox/releases/download/v{payload['component_version']}/"
        f"{payload['archive']}"
    )
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.path != expected_path
    ):
        raise RuntimeError("optional component release URL is invalid")
    return payload


def component_status(data_dir) -> dict:
    marker = _marker_path(data_dir)
    executable = component_executable(data_dir)
    try:
        manifest = _component_manifest()
    except RuntimeError:
        return {"installed": False, "reason": "component manifest is invalid"}
    if not marker.is_file() or not executable.is_file():
        return {
            "installed": False,
            "streamrip_version": STREAMRIP_VERSION,
            "streamrip_commit": STREAMRIP_COMMIT,
            "certifi_version": CERTIFI_VERSION,
            "component_version": manifest["component_version"],
        }
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"installed": False, "reason": "component marker is invalid"}
    installed = all(
        payload.get(key) == manifest[key]
        for key in (
            "component_version",
            "sha256",
            "streamrip_version",
            "streamrip_commit",
            "certifi_version",
        )
    )
    return {**payload, "installed": installed}


def _copy_component_archive(manifest: dict, destination) -> None:
    override = os.environ.get(COMPONENT_ARCHIVE_ENV)
    if override:
        source = Path(override).expanduser().open("rb")
    else:
        request = urllib.request.Request(
            manifest["download_url"],
            headers={"User-Agent": f"Syncbox/{manifest['component_version']}"},
        )
        context = ssl.create_default_context(cafile=certifi.where())
        source = urllib.request.urlopen(request, timeout=60, context=context)

    digest = hashlib.sha256()
    total = 0
    with source:
        while chunk := source.read(1024 * 1024):
            total += len(chunk)
            if total > manifest["size"]:
                raise RuntimeError("optional component archive is larger than expected")
            digest.update(chunk)
            destination.write(chunk)
    if total != manifest["size"] or digest.hexdigest() != manifest["sha256"]:
        raise RuntimeError("optional component archive integrity check failed")


def _safe_extract(archive_path: Path, destination: Path, manifest: dict) -> None:
    destination.mkdir()
    resolved_destination = destination.resolve()
    seen = set()
    entries = []
    symlinks = set()
    unpacked = 0
    with zipfile.ZipFile(archive_path) as archive:
        for item in archive.infolist():
            if "\\" in item.filename or "\x00" in item.filename:
                raise RuntimeError("optional component archive path is invalid")
            archived = PurePosixPath(item.filename)
            if archived.is_absolute() or ".." in archived.parts or not archived.parts:
                raise RuntimeError("optional component archive path is invalid")
            if archived.parts[0] != manifest["root"]:
                raise RuntimeError("optional component archive root is invalid")
            if len(archived.parts) == 1:
                if not item.is_dir():
                    raise RuntimeError("optional component archive root is invalid")
                continue
            relative = Path(*archived.parts[1:])
            if relative in seen:
                raise RuntimeError("optional component archive has duplicate paths")
            seen.add(relative)
            mode = item.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if item.is_dir():
                kind = "directory"
            elif file_type == stat.S_IFLNK:
                kind = "symlink"
                symlinks.add(relative)
            elif file_type in (0, stat.S_IFREG):
                kind = "file"
            else:
                raise RuntimeError("optional component archive contains a special file")
            unpacked += 0 if item.is_dir() else item.file_size
            if unpacked > MAX_UNPACKED_BYTES:
                raise RuntimeError("optional component archive expands beyond its limit")
            entries.append((item, relative, mode, kind))

        for _, relative, _, _ in entries:
            if any(parent in symlinks for parent in relative.parents):
                raise RuntimeError("optional component archive nests content under a symlink")

        for item, relative, mode, kind in sorted(
            entries, key=lambda entry: entry[3] == "symlink"
        ):
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.parent.resolve().is_relative_to(resolved_destination):
                raise RuntimeError("optional component archive path escapes its root")
            if kind == "directory":
                target.mkdir(exist_ok=True)
            elif kind == "file":
                with archive.open(item) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                target.chmod(stat.S_IMODE(mode) or 0o644)
            else:
                link = archive.read(item).decode("utf-8")
                link_path = PurePosixPath(link)
                if link_path.is_absolute() or not (
                    target.parent / Path(*link_path.parts)
                ).resolve().is_relative_to(resolved_destination):
                    raise RuntimeError("optional component archive symlink escapes its root")
                target.symlink_to(link)


def _checked_component_payload(completed, manifest: dict) -> dict:
    try:
        payload = json.loads(completed.stdout.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise RuntimeError("optional Deezer component check returned invalid output") from error
    expected = {
        "result": "CHECK_PASSED",
        "streamrip_version": STREAMRIP_VERSION,
        "streamrip_commit": STREAMRIP_COMMIT,
        "certifi_version": CERTIFI_VERSION,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise RuntimeError("optional Deezer component check failed")
    return {
        "component_version": manifest["component_version"],
        "sha256": manifest["sha256"],
        "streamrip_version": STREAMRIP_VERSION,
        "streamrip_commit": STREAMRIP_COMMIT,
        "certifi_version": CERTIFI_VERSION,
    }


def install_component(data_dir, *, runner=subprocess.run) -> dict:
    manifest = _component_manifest()
    root = component_root(data_dir)
    parent = root.parent
    parent.mkdir(parents=True, exist_ok=True)
    archive_path = None
    backup = root.with_name(f"{root.name}.previous")
    try:
        with tempfile.NamedTemporaryFile(
            prefix="component-", suffix=".zip", dir=parent, delete=False
        ) as archive:
            archive_path = Path(archive.name)
            _copy_component_archive(manifest, archive)
        with tempfile.TemporaryDirectory(prefix="component-install-", dir=parent) as raw_stage:
            staged = Path(raw_stage) / "component"
            _safe_extract(archive_path, staged, manifest)
            executable = staged / manifest["executable"]
            if not executable.is_file() or not os.access(executable, os.X_OK):
                raise RuntimeError("optional component executable is missing")
            check = runner(
                [str(executable), "--check"],
                check=True,
                text=True,
                capture_output=True,
            )
            marker = _checked_component_payload(check, manifest)
            marker_path = staged / "syncbox-component.json"
            marker_path.write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")
            marker_path.chmod(0o600)

            shutil.rmtree(backup, ignore_errors=True)
            if root.exists():
                root.rename(backup)
            try:
                staged.rename(root)
            except BaseException:
                if backup.exists() and not root.exists():
                    backup.rename(root)
                raise
            shutil.rmtree(backup, ignore_errors=True)
    finally:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)
    return component_status(data_dir)


def acquisition_output_dir(storage_root, job_id: int) -> Path:
    return Path(storage_root) / SYNC_DIR_NAME / "acquisition" / f"job-{job_id}"


def run_deezer_download(data_dir, arl: str, isrc: str, output_dir, *, runner=subprocess.run) -> dict:
    status = component_status(data_dir)
    if not status.get("installed"):
        raise ValueError("optional Deezer component is not installed")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="syncbox-arl-") as raw_temp:
        credential = Path(raw_temp) / "arl"
        fd = os.open(
            credential,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            with os.fdopen(fd, "w") as handle:
                fd = -1
                handle.write(arl)
                handle.flush()
                os.fsync(handle.fileno())
            completed = runner(
                [
                    str(component_executable(data_dir)),
                    "--isrc",
                    normalize_isrc(isrc),
                    "--credential-file",
                    str(credential),
                    "--output-dir",
                    str(output_dir),
                ],
                check=True,
                text=True,
                capture_output=True,
            )
        finally:
            if fd >= 0:
                os.close(fd)
            credential.unlink(missing_ok=True)
    payload = json.loads(completed.stdout.splitlines()[-1])
    if payload.get("result") != "FULL_TRACK_DOWNLOADED":
        raise RuntimeError(payload.get("reason") or "Deezer acquisition failed")
    output_path = Path(payload["output_path"]).resolve(strict=True)
    if not output_path.is_relative_to(output_dir.resolve()):
        raise RuntimeError("Deezer acquisition output escaped the job directory")
    return payload


def remove_component(data_dir) -> None:
    shutil.rmtree(component_root(data_dir), ignore_errors=True)
