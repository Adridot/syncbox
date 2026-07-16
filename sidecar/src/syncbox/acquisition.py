"""Optional Deezer acquisition boundary.

The base sidecar never imports streamrip. A separately distributed, pinned
component is installed into app data only after explicit enablement, then
invoked as a short-lived subprocess with a one-shot credential file.
"""

from __future__ import annotations

import hashlib
import json
import logging
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
OPTIONAL_PYTHON_VERSION = "3.13.11"
PILLOW_VERSION = "10.4.0"
PILLOW_WHEEL = "pillow-10.4.0-cp313-cp313-macosx_11_0_arm64.whl"
PILLOW_WHEEL_SHA256 = "6209bb41dc692ddfee4942517c19ee81b86c864b626dbfca272ec0f7cff5d9fb"
COMPONENT_NAME = "syncbox-deezer-component"
COMPONENT_ARCHIVE_ENV = "SYNCBOX_DEEZER_COMPONENT_ARCHIVE"
MAX_COMPONENT_BYTES = 512 * 1024 * 1024
MAX_UNPACKED_BYTES = 1024 * 1024 * 1024
ISRC_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")

log = logging.getLogger(__name__)
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


DEEZER_API_URL = "https://api.deezer.com"


def _deezer_api_get(path: str, params: dict | None = None) -> dict:
    """GET on the public Deezer catalogue API (no credentials involved)."""
    url = DEEZER_API_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "Syncbox"})
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, timeout=15, context=context) as source:
        payload = json.loads(source.read().decode("utf-8"))
    if isinstance(payload, dict) and payload.get("error"):
        message = (payload.get("error") or {}).get("message") or "Deezer API error"
        raise RuntimeError(f"Deezer API: {message}")
    return payload if isinstance(payload, dict) else {}


def deezer_search(query: str, limit: int = 15) -> list[dict]:
    """Catalogue search for the manual-search panel: title/artist/cover plus
    the 30 s `preview` URL the UI plays before the user picks a result."""
    payload = _deezer_api_get(
        "/search", {"q": query.strip(), "limit": max(1, min(int(limit), 25))}
    )
    results = []
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        album = item.get("album") or {}
        artist = item.get("artist") or {}
        results.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "artist": artist.get("name"),
                "album": album.get("title"),
                "duration": item.get("duration"),
                "preview_url": item.get("preview") or None,
                "cover_url": album.get("cover_medium") or album.get("cover") or None,
            }
        )
    return results


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
        "python_version",
        "pillow_version",
        "pillow_wheel",
        "pillow_wheel_sha256",
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
        "python_version": OPTIONAL_PYTHON_VERSION,
        "pillow_version": PILLOW_VERSION,
        "pillow_wheel": PILLOW_WHEEL,
        "pillow_wheel_sha256": PILLOW_WHEEL_SHA256,
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
            "python_version": OPTIONAL_PYTHON_VERSION,
            "pillow_version": PILLOW_VERSION,
            "component_version": manifest["component_version"],
        }
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return {"installed": False, "reason": "component marker is invalid"}
    installed = all(
        payload.get(key) == manifest[key]
        for key in (
            "component_version",
            "sha256",
            "streamrip_version",
            "streamrip_commit",
            "certifi_version",
            "python_version",
            "pillow_version",
            "pillow_wheel",
            "pillow_wheel_sha256",
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
                raise RuntimeError(
                    "optional component archive expands beyond its limit"
                )
            entries.append((item, relative, mode, kind))

        for _, relative, _, _ in entries:
            if any(parent in symlinks for parent in relative.parents):
                raise RuntimeError(
                    "optional component archive nests content under a symlink"
                )

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
                    raise RuntimeError(
                        "optional component archive symlink escapes its root"
                    )
                target.symlink_to(link)


def _checked_component_payload(completed, manifest: dict) -> dict:
    try:
        payload = json.loads(completed.stdout.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "optional Deezer component check returned invalid output"
        ) from error
    expected = {
        "result": "CHECK_PASSED",
        "streamrip_version": STREAMRIP_VERSION,
        "streamrip_commit": STREAMRIP_COMMIT,
        "certifi_version": CERTIFI_VERSION,
        "pillow_version": PILLOW_VERSION,
        "pillow_wheel": PILLOW_WHEEL,
        "pillow_wheel_sha256": PILLOW_WHEEL_SHA256,
        "artwork": "pillow_jpeg_ready",
        "cryptography": "aes_blowfish_ready",
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise RuntimeError("optional Deezer component check failed")
    return {
        "component_version": manifest["component_version"],
        "sha256": manifest["sha256"],
        "streamrip_version": STREAMRIP_VERSION,
        "streamrip_commit": STREAMRIP_COMMIT,
        "certifi_version": CERTIFI_VERSION,
        "python_version": OPTIONAL_PYTHON_VERSION,
        "pillow_version": PILLOW_VERSION,
        "pillow_wheel": PILLOW_WHEEL,
        "pillow_wheel_sha256": PILLOW_WHEEL_SHA256,
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
        with tempfile.TemporaryDirectory(
            prefix="component-install-", dir=parent
        ) as raw_stage:
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


def event_audio_destination(storage_root, staging_dir) -> Path:
    """Resolve an event-owned audio directory without following managed symlinks."""
    root = Path(storage_root).expanduser().resolve(strict=False)
    raw_events_root = root / SYNC_DIR_NAME / "events"
    events_root = raw_events_root.resolve(strict=False)
    if events_root != raw_events_root:
        raise ValueError(
            f"event storage must not use symbolic links: {raw_events_root}"
        )
    raw_staging = Path(staging_dir).expanduser()
    if raw_staging.is_symlink():
        raise ValueError(f"event staging directory is a symbolic link: {raw_staging}")
    staging = raw_staging.resolve(strict=False)
    try:
        staging.relative_to(events_root)
    except ValueError as exc:
        raise ValueError(
            f"event staging directory escapes managed storage: {staging}"
        ) from exc
    if staging == events_root:
        raise ValueError("event staging directory cannot be the events root")
    raw_destination = staging / "audio"
    if raw_destination.is_symlink():
        raise ValueError(
            f"event audio destination is a symbolic link: {raw_destination}"
        )
    return raw_destination.resolve(strict=False)


def collection_destination(storage_root) -> Path:
    """Resolve the permanent Collection directory without following symlinks."""
    root = Path(storage_root).expanduser().resolve(strict=False)
    raw_destination = root / "rekordbox" / "Collection"
    destination = raw_destination.resolve(strict=False)
    if destination != raw_destination:
        raise ValueError(
            f"Rekordbox Collection must not use symbolic links: {raw_destination}"
        )
    return destination


def publish_download(source, destination_dir) -> Path:
    """Move a completed download into its semantic owner without overwriting."""
    raw_source = Path(source)
    if raw_source.is_symlink():
        raise ValueError(f"download output is a symbolic link: {raw_source}")
    source = raw_source.resolve(strict=True)
    if not source.is_file():
        raise ValueError(f"download output is not a safe regular file: {source}")
    raw_destination_dir = Path(destination_dir)
    if raw_destination_dir.is_symlink():
        raise ValueError(
            f"download destination is a symbolic link: {raw_destination_dir}"
        )
    destination_dir = raw_destination_dir.resolve(strict=False)
    destination_dir.mkdir(parents=True, exist_ok=True)

    destination = destination_dir / source.name
    suffix = 1
    while destination.exists():
        suffix += 1
        destination = destination_dir / f"{source.stem} - {suffix}{source.suffix}"
    return Path(shutil.move(str(source), str(destination))).resolve(strict=True)


def run_deezer_download(
    data_dir,
    arl: str,
    isrc: str | None,
    output_dir,
    *,
    track_id: int | None = None,
    runner=subprocess.run,
) -> dict:
    status = component_status(data_dir)
    if not status.get("installed"):
        raise ValueError("optional Deezer component is not installed")
    # manual pick: download the exact chosen track id (bypasses ISRC
    # resolution, which can land on an unstreamable canonical entry)
    if track_id is not None:
        selector = ["--track-id", str(int(track_id))]
        identity = f"track_id={int(track_id)}"
    else:
        selector = ["--isrc", normalize_isrc(isrc)]
        identity = f"isrc={normalize_isrc(isrc)}"
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
                    *selector,
                    "--credential-file",
                    str(credential),
                    "--output-dir",
                    str(output_dir),
                ],
                check=False,
                text=True,
                capture_output=True,
            )
        finally:
            if fd >= 0:
                os.close(fd)
            credential.unlink(missing_ok=True)
    # check=False: on failure the component still prints its reason JSON and
    # exits non-zero — parse it instead of losing it to CalledProcessError.
    returncode = getattr(completed, "returncode", 0) or 0
    lines = (getattr(completed, "stdout", "") or "").splitlines()
    try:
        payload = json.loads(lines[-1]) if lines else {}
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if returncode != 0 or payload.get("result") != "FULL_TRACK_DOWNLOADED":
        reason = (
            payload.get("reason")
            or payload.get("result")
            or f"component exited with code {returncode} and no result payload"
        )
        stderr_tail = (getattr(completed, "stderr", "") or "").strip()[-2000:]
        log.warning(
            "Deezer acquisition failed: %s exit=%s reason=%s%s",
            identity,
            returncode,
            reason,
            f" stderr_tail={stderr_tail!r}" if stderr_tail else "",
        )
        raise RuntimeError(str(reason))
    filename = payload.get("output_filename")
    if (
        not isinstance(filename, str)
        or not filename
        or filename in {".", ".."}
        or Path(filename).name != filename
        or "/" in filename
        or "\\" in filename
    ):
        raise RuntimeError("Deezer acquisition output filename is invalid")
    output_path = (output_dir / filename).resolve(strict=True)
    if not output_path.is_relative_to(output_dir.resolve()):
        raise RuntimeError("Deezer acquisition output escaped the job directory")
    if not output_path.is_file():
        raise RuntimeError("Deezer acquisition output is not a regular file")
    payload["output_path"] = str(output_path)
    return payload


def remove_component(data_dir) -> None:
    shutil.rmtree(component_root(data_dir), ignore_errors=True)
