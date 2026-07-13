"""Optional Deezer acquisition boundary.

The base sidecar never imports streamrip. The GPL component is installed into
an app-data venv only after explicit enablement, then invoked as a short-lived
subprocess with a one-shot credential file.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from syncbox.safety.paths import SYNC_DIR_NAME

DEEZER_ARL_SECRET = "deezer.arl"
STREAMRIP_VERSION = "2.2.0"
STREAMRIP_COMMIT = "189acda489927719aa8591f6acdd7d67aecf929b"
CERTIFI_VERSION = "2026.6.17"
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


def component_python(data_dir) -> Path:
    root = component_root(data_dir)
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _marker_path(data_dir) -> Path:
    return component_root(data_dir) / "syncbox-component.json"


def component_status(data_dir) -> dict:
    marker = _marker_path(data_dir)
    python = component_python(data_dir)
    if not marker.is_file() or not python.is_file():
        return {
            "installed": False,
            "streamrip_version": STREAMRIP_VERSION,
            "streamrip_commit": STREAMRIP_COMMIT,
            "certifi_version": CERTIFI_VERSION,
            "python": str(python),
        }
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"installed": False, "reason": "component marker is invalid"}
    installed = (
        payload.get("streamrip_version") == STREAMRIP_VERSION
        and payload.get("streamrip_commit") == STREAMRIP_COMMIT
        and payload.get("certifi_version") == CERTIFI_VERSION
    )
    return {**payload, "installed": installed, "python": str(python)}


def _poc_script() -> Path:
    return Path(__file__).resolve().parents[3] / "poc" / "run_b1_deezer_acquisition.py"


def install_component(data_dir, *, runner=subprocess.run) -> dict:
    root = component_root(data_dir)
    python = component_python(data_dir)
    if not python.exists():
        root.parent.mkdir(parents=True, exist_ok=True)
        runner([sys.executable, "-m", "venv", str(root)], check=True)
    runner(
        [
            str(python),
            "-m",
            "pip",
            "install",
            f"certifi=={CERTIFI_VERSION}",
            f"streamrip @ git+https://github.com/nathom/streamrip.git@{STREAMRIP_COMMIT}",
        ],
        check=True,
    )
    check = runner(
        [str(python), str(_poc_script()), "--check"],
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(check.stdout.splitlines()[-1])
    if payload.get("result") != "CHECK_PASSED":
        raise RuntimeError("optional Deezer component check failed")
    marker = {
        "streamrip_version": STREAMRIP_VERSION,
        "streamrip_commit": STREAMRIP_COMMIT,
        "certifi_version": CERTIFI_VERSION,
    }
    _marker_path(data_dir).write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")
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
                    status["python"],
                    str(_poc_script()),
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
