#!/usr/bin/env python3
"""Run the isolated Deezer component without persisting credentials."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib
import importlib.machinery
import importlib.metadata
import importlib.util
import io
import json
import logging
import os
import platform
import re
import secrets
import shutil
import ssl
import stat
import sys
import tempfile
import types
import urllib.error
import urllib.request
from pathlib import Path

STREAMRIP_VERSION = "2.2.0"
STREAMRIP_COMMIT = "189acda489927719aa8591f6acdd7d67aecf929b"
PILLOW_VERSION = "10.4.0"
PILLOW_WHEEL = "pillow-10.4.0-cp313-cp313-macosx_11_0_arm64.whl"
PILLOW_WHEEL_SHA256 = "6209bb41dc692ddfee4942517c19ee81b86c864b626dbfca272ec0f7cff5d9fb"
ISRC_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")


class PocBlocked(RuntimeError):
    pass


class PocFailed(RuntimeError):
    pass


def _emit(**payload) -> None:
    print(json.dumps(payload, sort_keys=True))


def _normalize_isrc(raw: str) -> str:
    value = re.sub(r"[-\s]", "", raw).upper()
    if not ISRC_PATTERN.fullmatch(value):
        raise PocBlocked("invalid_isrc")
    return value


def _read_one_shot_credential(path: Path) -> str:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as error:
        raise PocBlocked("credential_file_missing") from error
    except OSError as error:
        raise PocBlocked("credential_file_unreadable") from error

    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise PocBlocked("credential_file_not_regular")
        if details.st_uid != os.getuid():
            raise PocBlocked("credential_file_wrong_owner")
        if stat.S_IMODE(details.st_mode) & 0o077:
            raise PocBlocked("credential_file_permissions_too_open")
        if not 64 <= details.st_size <= 512:
            raise PocBlocked("credential_file_size_invalid")
        raw = os.read(descriptor, 513)
    finally:
        os.close(descriptor)

    try:
        value = raw.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise PocBlocked("credential_file_encoding_invalid") from error
    if not 64 <= len(value) <= 512 or not re.fullmatch(r"[0-9a-fA-F]+", value):
        raise PocBlocked("credential_format_invalid")

    path.unlink()
    return value


def _directory_state(root: Path):
    if not root.exists():
        return None
    try:
        paths = [root, *root.rglob("*")]
        return tuple(
            sorted(
                (
                    str(path.relative_to(root)),
                    stat.S_IFMT(path.lstat().st_mode),
                    stat.S_IMODE(path.lstat().st_mode),
                    path.lstat().st_size,
                    path.lstat().st_mtime_ns,
                )
                for path in paths
            )
        )
    except OSError as error:
        raise PocBlocked("global_streamrip_app_dir_unreadable") from error


def _verify_streamrip_distribution() -> dict:
    try:
        distribution = importlib.metadata.distribution("streamrip")
    except importlib.metadata.PackageNotFoundError as error:
        raise PocBlocked("streamrip_not_installed") from error
    if distribution.version != STREAMRIP_VERSION:
        raise PocBlocked("streamrip_version_mismatch")

    try:
        direct_url = json.loads(distribution.read_text("direct_url.json") or "{}")
    except json.JSONDecodeError as error:
        raise PocBlocked("streamrip_direct_url_invalid") from error
    installed_commit = direct_url.get("vcs_info", {}).get("commit_id")
    if installed_commit != STREAMRIP_COMMIT:
        raise PocBlocked("streamrip_commit_mismatch")

    try:
        certifi_version = importlib.metadata.version("certifi")
    except importlib.metadata.PackageNotFoundError as error:
        raise PocBlocked("certifi_not_installed") from error
    try:
        pillow_version = importlib.metadata.version("pillow")
    except importlib.metadata.PackageNotFoundError as error:
        raise PocBlocked("pillow_not_installed") from error
    if pillow_version != PILLOW_VERSION:
        raise PocBlocked("pillow_version_mismatch")
    return {
        "streamrip_version": distribution.version,
        "streamrip_commit": installed_commit,
        "certifi_version": certifi_version,
        "pillow_version": pillow_version,
    }


def _prepare_deezer_client_package() -> types.ModuleType:
    spec = importlib.util.find_spec("streamrip")
    if spec is None or not spec.submodule_search_locations:
        raise PocBlocked("streamrip_package_unavailable")

    class InterfaceOnly:
        pass

    client = types.ModuleType("streamrip.client")
    client.__path__ = [
        str(Path(next(iter(spec.submodule_search_locations))) / "client")
    ]
    client.__package__ = "streamrip.client"
    client.__spec__ = importlib.machinery.ModuleSpec(
        "streamrip.client", loader=None, is_package=True
    )
    client.__spec__.submodule_search_locations = client.__path__
    client.Client = InterfaceOnly
    client.Downloadable = InterfaceOnly
    client.BasicDownloadable = InterfaceOnly
    sys.modules["streamrip.client"] = client
    return client


def _load_component(temp_root: Path, real_home: Path):
    real_app_dir = real_home / "Library" / "Application Support" / "streamrip"
    real_app_dir_before = _directory_state(real_app_dir)

    isolated_home = temp_root / "home"
    os.environ["HOME"] = str(isolated_home)
    os.environ["XDG_CONFIG_HOME"] = str(temp_root / "config")
    os.environ["XDG_CACHE_HOME"] = str(temp_root / "cache")
    logging.disable(logging.CRITICAL)

    versions = _verify_streamrip_distribution()
    client_package = _prepare_deezer_client_package()
    try:
        import certifi
        from PIL import Image
        from mutagen import File as MutagenFile
        from streamrip import Config
        from streamrip import config as streamrip_config
        from streamrip import db as streamrip_db
        from streamrip.media.track import PendingSingle
        from streamrip.utils import ssl_utils

        client_module = importlib.import_module("streamrip.client.client")
        downloadable_module = importlib.import_module(
            "streamrip.client.downloadable"
        )
        client_package.Client = client_module.Client
        client_package.Downloadable = downloadable_module.Downloadable
        client_package.BasicDownloadable = downloadable_module.BasicDownloadable
        artwork_module = importlib.import_module("streamrip.media.artwork")
        artwork_module.BasicDownloadable = downloadable_module.BasicDownloadable
        DeezerClient = importlib.import_module(
            "streamrip.client.deezer"
        ).DeezerClient
    except ImportError as error:
        raise PocBlocked(f"component_import_failed_{type(error).__name__}") from None

    app_dir = Path(streamrip_config.APP_DIR).resolve()
    if not app_dir.is_relative_to(temp_root.resolve()):
        raise PocFailed("streamrip_app_dir_not_isolated")
    if _directory_state(real_app_dir) != real_app_dir_before:
        raise PocFailed("streamrip_modified_global_app_dir")
    context = ssl_utils.create_ssl_context(verify=True)
    if not ssl_utils.HAS_CERTIFI:
        raise PocBlocked("streamrip_certifi_disabled")
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise PocBlocked("streamrip_tls_verification_disabled")

    ca_bundle = certifi.where()
    os.environ["SSL_CERT_FILE"] = ca_bundle
    os.environ["REQUESTS_CA_BUNDLE"] = ca_bundle
    os.environ["CURL_CA_BUNDLE"] = ca_bundle

    return {
        **versions,
        "certifi": certifi,
        "Image": Image,
        "MutagenFile": MutagenFile,
        "Config": Config,
        "streamrip_db": streamrip_db,
        "DeezerClient": DeezerClient,
        "PendingSingle": PendingSingle,
        "artwork_downloadable": artwork_module.BasicDownloadable,
        "basic_downloadable": downloadable_module.BasicDownloadable,
        "real_app_dir": real_app_dir,
        "real_app_dir_before": real_app_dir_before,
    }


def _resolve_isrc(isrc: str, certifi) -> tuple[int, int]:
    request = urllib.request.Request(
        f"https://api.deezer.com/track/isrc:{isrc}",
        headers={"User-Agent": "Syncbox-B1-POC/1"},
    )
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urllib.request.urlopen(request, timeout=20, context=context) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise PocFailed("isrc_lookup_failed") from error
    if not isinstance(payload, dict) or "error" in payload:
        raise PocFailed("isrc_not_resolved")
    try:
        track_id = int(payload["id"])
        duration = int(payload["duration"])
    except (KeyError, TypeError, ValueError) as error:
        raise PocFailed("isrc_response_invalid") from error
    if track_id <= 0 or duration < 90:
        raise PocFailed("isrc_response_not_full_track")
    return track_id, duration


async def _download(component: dict, arl: str, isrc: str, output_dir: Path) -> dict:
    Config = component["Config"]
    streamrip_db = component["streamrip_db"]
    DeezerClient = component["DeezerClient"]
    PendingSingle = component["PendingSingle"]

    config = Config.defaults()
    config.session.deezer.arl = arl
    config.session.deezer.quality = 1
    config.session.deezer.lower_quality_if_not_available = False
    config.session.deezer.use_deezloader = False
    config.session.deezer.deezloader_warnings = False
    config.session.downloads.folder = str(output_dir)
    config.session.downloads.source_subdirectories = False
    config.session.downloads.disc_subdirectories = False
    config.session.downloads.concurrency = False
    config.session.downloads.max_connections = 1
    config.session.downloads.verify_ssl = True
    config.session.filepaths.add_singles_to_folder = False
    config.session.artwork.embed = True
    config.session.artwork.embed_size = "large"
    config.session.artwork.embed_max_width = -1
    config.session.artwork.save_artwork = False
    config.session.database.downloads_enabled = False
    config.session.database.failed_downloads_enabled = False
    config.session.database.downloads_path = str(
        output_dir.parent / "forbidden-downloads.db"
    )
    config.session.database.failed_downloads_path = str(
        output_dir.parent / "forbidden-failed-downloads.db"
    )
    config.session.conversion.enabled = False
    config.session.cli.text_output = False
    config.session.cli.progress_bars = False
    config.session.misc.check_for_updates = False

    track_id, api_duration = _resolve_isrc(isrc, component["certifi"])
    database = streamrip_db.Database(streamrip_db.Dummy(), streamrip_db.Dummy())
    client = DeezerClient(config)
    try:
        await client.login()
        pending = PendingSingle(str(track_id), client, config, database)
        track = await pending.resolve()
        if track is None:
            raise PocFailed("streamrip_resolution_returned_none")
        if _normalize_isrc(track.meta.isrc or "") != isrc:
            raise PocFailed("streamrip_resolved_wrong_isrc")
        if str(track.downloadable.id) != str(track_id):
            raise PocFailed("streamrip_resolved_fallback_track")
        await track.rip()
    except PocFailed:
        raise
    except Exception as error:
        raise PocFailed(f"streamrip_{type(error).__name__}") from None
    finally:
        config.session.deezer.arl = ""
        if hasattr(client, "session"):
            await client.session.close()

    output_path = Path(track.download_path).resolve(strict=True)
    resolved_output_dir = output_dir.resolve(strict=True)
    if not output_path.is_relative_to(resolved_output_dir):
        raise PocFailed("download_path_escaped_output_dir")

    audio = component["MutagenFile"](output_path)
    if audio is None or getattr(audio, "info", None) is None:
        raise PocFailed("downloaded_file_scan_failed")
    measured_duration = float(getattr(audio.info, "length", 0.0))
    duration_tolerance = max(2.0, api_duration * 0.01)
    if (
        measured_duration <= 30
        or abs(measured_duration - api_duration) > duration_tolerance
    ):
        raise PocFailed("downloaded_file_is_not_full_track")

    artwork = _embedded_artwork(component["Image"], audio, output_path.suffix.lower())
    artwork_dir = resolved_output_dir / "__artwork"
    if artwork_dir.is_symlink():
        raise PocFailed("artwork_directory_is_symlink")
    if artwork_dir.exists():
        if not artwork_dir.is_dir():
            raise PocFailed("artwork_directory_is_not_directory")
        shutil.rmtree(artwork_dir)

    return {
        "deezer_track_id": track_id,
        "api_duration_seconds": api_duration,
        "measured_duration_seconds": round(measured_duration, 2),
        "file_size_bytes": output_path.stat().st_size,
        "format": output_path.suffix.lower().lstrip("."),
        "quality": int(track.downloadable.quality),
        "output_filename": output_path.name,
        "output_path_source": "track.download_path",
        **artwork,
    }


def _embedded_artwork(Image, audio, suffix: str) -> dict[str, object]:
    tags = getattr(audio, "tags", None)
    payload = None
    container = None
    if suffix == ".flac":
        pictures = list(getattr(audio, "pictures", ()))
        if pictures:
            payload = pictures[0].data
            container = "FLAC Picture"
    elif suffix == ".mp3" and tags is not None:
        pictures = tags.getall("APIC")
        if pictures:
            payload = pictures[0].data
            container = "ID3 APIC"
    elif suffix == ".m4a" and tags is not None:
        pictures = tags.get("covr", ())
        if pictures:
            payload = bytes(pictures[0])
            container = "MP4 covr"
    if not payload or len(payload) < 512:
        raise PocFailed("downloaded_file_artwork_missing")
    if not payload.startswith(b"\xff\xd8\xff"):
        raise PocFailed("downloaded_file_artwork_not_jpeg")
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.verify()
            dimensions = [image.width, image.height]
            image_format = image.format
    except Exception as error:
        raise PocFailed("downloaded_file_artwork_invalid") from error
    if image_format != "JPEG" or min(dimensions) <= 0:
        raise PocFailed("downloaded_file_artwork_invalid")
    return {
        "artwork_embedded": True,
        "artwork_container": container,
        "artwork_bytes": len(payload),
        "artwork_dimensions": dimensions,
        "artwork_format": image_format,
    }


def _check(component: dict, temp_root: Path) -> dict:
    from Cryptodome.Cipher import AES, Blowfish

    if component["artwork_downloadable"] is not component["basic_downloadable"]:
        raise PocFailed("artwork_downloadable_binding_failed")

    aes = AES.new(b"0123456789abcdef", AES.MODE_ECB)
    aes_payload = b"0123456789abcdef"
    if aes.decrypt(aes.encrypt(aes_payload)) != aes_payload:
        raise PocFailed("aes_self_check_failed")
    blowfish = Blowfish.new(b"0123456789abcdef", Blowfish.MODE_CBC, b"12345678")
    blowfish_payload = b"01234567"
    encrypted = blowfish.encrypt(blowfish_payload)
    blowfish = Blowfish.new(b"0123456789abcdef", Blowfish.MODE_CBC, b"12345678")
    if blowfish.decrypt(encrypted) != blowfish_payload:
        raise PocFailed("blowfish_self_check_failed")

    image_buffer = io.BytesIO()
    component["Image"].new("RGB", (32, 24), "#6536f2").save(
        image_buffer, format="JPEG"
    )
    image_buffer.seek(0)
    with component["Image"].open(image_buffer) as image:
        resized = image.resize((16, 12))
        if image.format != "JPEG" or resized.size != (16, 12):
            raise PocFailed("pillow_jpeg_self_check_failed")

    credential = temp_root / "credential"
    expected = secrets.token_hex(96)
    credential.write_text(expected)
    credential.chmod(0o600)
    actual = _read_one_shot_credential(credential)
    if actual != expected or credential.exists():
        raise PocFailed("one_shot_credential_check_failed")
    expected = actual = ""

    too_open = temp_root / "credential-too-open"
    too_open.write_text(secrets.token_hex(96))
    too_open.chmod(0o644)
    try:
        _read_one_shot_credential(too_open)
    except PocBlocked as error:
        if str(error) != "credential_file_permissions_too_open":
            raise PocFailed("credential_permissions_check_failed") from error
    else:
        raise PocFailed("credential_permissions_check_failed")
    if not too_open.exists():
        raise PocFailed("rejected_credential_was_removed")
    too_open.unlink()

    symlink_target = temp_root / "credential-target"
    symlink_target.write_text(secrets.token_hex(96))
    symlink_target.chmod(0o600)
    symlink = temp_root / "credential-symlink"
    symlink.symlink_to(symlink_target)
    try:
        _read_one_shot_credential(symlink)
    except PocBlocked:
        pass
    else:
        raise PocFailed("credential_symlink_check_failed")
    if not symlink_target.exists():
        raise PocFailed("credential_symlink_target_removed")
    symlink.unlink()
    symlink_target.unlink()

    if list(temp_root.rglob("config.toml")):
        raise PocFailed("streamrip_config_file_written")
    if list(temp_root.rglob("*.db")):
        raise PocFailed("streamrip_database_written")
    return {
        "check": "passed",
        "platform": "macOS-arm64",
        "credential_io": "one_shot_file_removed",
        "global_config_dir": "untouched",
        "tls_verification": "certifi_required",
        "artwork": "pillow_jpeg_ready",
        "cryptography": "aes_blowfish_ready",
        "pillow_wheel": PILLOW_WHEEL,
        "pillow_wheel_sha256": PILLOW_WHEEL_SHA256,
        **{
            key: component[key]
            for key in (
                "streamrip_version",
                "streamrip_commit",
                "certifi_version",
                "pillow_version",
            )
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="run non-network checks")
    parser.add_argument("--isrc", help="representative track ISRC")
    parser.add_argument(
        "--credential-file",
        help="required one-shot credential file; consumed and deleted on success",
    )
    parser.add_argument(
        "--output-dir",
        help="persistent download directory; defaults to a temporary POC folder",
    )
    args = parser.parse_args(argv)

    if platform.system() != "Darwin" or platform.machine() != "arm64":
        _emit(result="BLOCKED", reason="requires_macos_arm64")
        return 2
    if not args.check and not (args.isrc and args.credential_file and args.output_dir):
        _emit(result="BLOCKED", reason="isrc_credential_and_output_required")
        return 2

    real_home = Path.home()
    try:
        with tempfile.TemporaryDirectory(prefix="syncbox-b1-") as raw_temp:
            temp_root = Path(raw_temp)
            component = _load_component(temp_root, real_home)
            if args.check:
                result = _check(component, temp_root)
            else:
                isrc = _normalize_isrc(args.isrc)
                arl = _read_one_shot_credential(Path(args.credential_file))
                try:
                    output_dir = Path(args.output_dir)
                    output_dir.mkdir(parents=True, exist_ok=True)
                    captured = io.StringIO()
                    try:
                        with contextlib.redirect_stdout(
                            captured
                        ), contextlib.redirect_stderr(captured):
                            result = asyncio.run(
                                _download(component, arl, isrc, output_dir)
                            )
                    except BaseException as error:
                        if arl in captured.getvalue():
                            raise PocFailed("credential_exposed_by_component") from None
                        raise error
                    if arl in captured.getvalue():
                        raise PocFailed("credential_exposed_by_component")
                finally:
                    arl = ""

            if _directory_state(component["real_app_dir"]) != component[
                "real_app_dir_before"
            ]:
                raise PocFailed("streamrip_modified_global_app_dir")
            if list(temp_root.rglob("config.toml")):
                raise PocFailed("streamrip_config_file_written")
            if list(temp_root.rglob("*.db")):
                raise PocFailed("streamrip_database_written")
        if Path(raw_temp).exists():
            raise PocFailed("temporary_output_not_removed")
    except PocBlocked as error:
        _emit(result="BLOCKED", reason=str(error))
        return 2
    except PocFailed as error:
        _emit(result="FAILED", reason=str(error))
        return 1
    except Exception as error:
        _emit(result="FAILED", reason=f"unexpected_{type(error).__name__}")
        return 1

    _emit(result="CHECK_PASSED" if args.check else "FULL_TRACK_DOWNLOADED", **result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
