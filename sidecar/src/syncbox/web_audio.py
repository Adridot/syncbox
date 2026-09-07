"""Base-side invocation of the separately installed web-audio component."""

import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import time
from syncbox import acquisition

NAME = "syncbox-web-audio-component"
VERSION = "0.8.0"


def component_root(data_dir):
    return Path(data_dir) / "optional" / "web-audio" / VERSION


def manifest():
    path = Path(__file__).with_name("web_audio_component.json")
    if not path.is_file():
        raise ValueError("web_audio_release_unavailable")
    value = json.loads(path.read_text())
    if value.get("component") != NAME or value.get("component_version") != VERSION or value.get("root") != NAME or value.get("executable") != NAME or value.get("license_inventory_complete") is not True:
        raise ValueError("web_audio_manifest_invalid")
    if not re.fullmatch(r"[a-f0-9]{64}", value.get("sha256", "")) or not 0 < value.get("size", 0) <= 512 * 1024 * 1024:
        raise ValueError("web_audio_manifest_invalid")
    archive = f"{NAME}-{VERSION}-macos-arm64.zip"
    if value.get("archive") != archive or value.get("download_url") != f"https://github.com/Adridot/syncbox/releases/download/v{VERSION}/{archive}":
        raise ValueError("web_audio_manifest_invalid")
    return value


def component_status(data_dir):
    if (platform.system(), platform.machine()) != ("Darwin", "arm64"):
        return {"installed": False, "reason": "unsupported_platform"}
    try:
        expected = manifest()
        marker = json.loads((component_root(data_dir) / "syncbox-component.json").read_text())
        installed = marker.get("sha256") == expected["sha256"] and marker.get("protocol_version") == 1 and (component_root(data_dir) / NAME).is_file()
        return {"installed": installed, "component_version": VERSION, "protocol_version": marker.get("protocol_version")}
    except ValueError as error:
        return {"installed": False, "reason": str(error) if str(error).startswith("web_audio_") else "web_audio_component_missing", "component_version": VERSION}
    except OSError:
        return {"installed": False, "reason": "web_audio_component_missing", "component_version": VERSION}


def install_component(data_dir):
    if (platform.system(), platform.machine()) != ("Darwin", "arm64"):
        raise ValueError("unsupported_platform")
    expected = manifest()
    root = component_root(data_dir)
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="web-audio-install-", dir=root.parent) as directory:
        temporary = Path(directory)
        archive = temporary / "component.zip"
        with archive.open("wb") as output:
            acquisition._copy_component_archive(expected, output, archive_env="SYNCBOX_WEB_AUDIO_COMPONENT_ARCHIVE")
        staged = temporary / "component"
        acquisition._safe_extract(archive, staged, expected)
        result = invoke(staged / NAME, {"operation": "check"})
        if result.get("protocol_version") != 1 or result.get("versions") != expected.get("versions") or result.get("ffmpeg") != expected.get("ffmpeg") or result.get("deno") != expected.get("deno"):
            raise ValueError("web_audio_component_check_failed")
        (staged / "syncbox-component.json").write_text(json.dumps({"sha256": expected["sha256"], "protocol_version": 1}))
        backup = root.with_name(root.name + ".previous")
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
    return component_status(data_dir)


def invoke(executable, request, *, cancelled=lambda: False):
    process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, env={**os.environ, "PATH": "/usr/bin:/bin"})
    deadline = time.monotonic() + (620 if request["operation"] == "download" else 140)
    data = json.dumps(request).encode()
    try:
        while True:
            if cancelled():
                raise ValueError("operation_cancelled")
            if time.monotonic() >= deadline:
                raise ValueError("operation_timeout")
            try:
                output, _ = process.communicate(input=data, timeout=.2)
                break
            except subprocess.TimeoutExpired:
                data = None
        if process.returncode or len(output) > 4 * 1024 * 1024:
            raise ValueError("web_audio_component_failed")
        result = json.loads(output)
        if result.get("result") != "ok":
            error = result.get("error", "web_audio_component_failed")
            raise ValueError(error if isinstance(error, str) and re.fullmatch(r"[a-z_]{1,100}", error) else "web_audio_component_failed")
        return result
    finally:
        if process.poll() is None:
            # The installed supervisor forwards TERM to its complete worker group.
            process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()


def run(data_dir, request, *, cancelled=lambda: False):
    if not component_status(data_dir)["installed"]:
        raise ValueError("web_audio_component_missing")
    result = invoke(component_root(data_dir) / NAME, request, cancelled=cancelled)
    if request["operation"] == "download":
        filename = result.get("output_filename")
        if not isinstance(filename, str) or Path(filename).name != filename or filename in {".", ".."} or "\\" in filename:
            raise ValueError("invalid_audio_output")
        root = Path(request["output_dir"]).resolve(strict=True)
        path = root / filename
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root) or path.suffix.lower() not in {".mp3", ".m4a", ".flac", ".wav", ".aiff", ".aif"}:
            raise ValueError("invalid_audio_output")
        if result.get("effective_item_id") != request["item_id"] or result.get("item_id") != request["item_id"]:
            raise ValueError("source_identity_mismatch")
        result["output_path"] = str(path)
    return result
