"""Bounded JSON subprocess wrapper for exact YouTube/SoundCloud audio."""

import functools
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit

import yt_dlp
from network import BoundaryError, Budget, transport, validate_destination

PROTOCOL_VERSION = 1
MAX_ITEMS = 1000
MAX_MANIFEST = 4 * 1024 * 1024
MAX_AUDIO = 512 * 1024 * 1024
TIMEOUTS = {"check": 30, "metadata": 120, "download": 600}
RUNTIME = Path(__file__).resolve().parent / "vendor"
SUPPORTED = {"mp3", "m4a", "flac", "wav", "aiff", "aif"}
SUPPORTED_CODECS = {
    "mp3": {"mp3"}, "m4a": {"aac", "alac"}, "flac": {"flac"},
    "wav": {"pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le"},
    "aiff": {"pcm_s16be", "pcm_s24be", "pcm_s32be"},
    "aif": {"pcm_s16be", "pcm_s24be", "pcm_s32be"},
}


class ComponentError(ValueError):
    pass


def failure_code(error):
    message = str(error).lower()
    for pattern, code in (
        ("unsupported_network_destination", "unsupported_network_destination"),
        ("private_network_destination", "private_network_destination"),
        ("network_byte_limit", "network_byte_limit"),
        ("network_request_limit", "network_request_limit"),
        ("http error 429", "provider_rate_limited"),
        ("sign in", "provider_authentication_required"),
        ("private", "provider_authentication_required"),
        ("http error 403", "provider_access_denied"),
        ("not available", "provider_item_unavailable"),
        ("timed out", "provider_timeout"),
        ("js challenge", "javascript_runtime_failed"),
        ("requested format", "audio_format_unavailable"),
    ):
        if pattern in message:
            return code
    return "provider_operation_failed"


class QuietLogger:
    def debug(self, message):
        pass

    info = warning = error = debug


def identity(url):
    validate_destination(url)
    parsed = urlsplit(url)
    host = parsed.hostname
    query = parse_qs(parsed.query)
    path = parsed.path.strip("/")
    if host in {"youtu.be", "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
        video = path if host == "youtu.be" else (query.get("v") or [None])[0]
        if path.startswith(("shorts/", "embed/")):
            video = path.split("/")[1]
        playlist = (query.get("list") or [None])[0]
        if video and not re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
            raise ComponentError("invalid_video_id")
        if playlist and not re.fullmatch(r"[A-Za-z0-9_-]{10,150}", playlist):
            raise ComponentError("invalid_playlist_id")
        if video and playlist:
            raise ComponentError("video_or_playlist_choice_required")
        if video:
            return "youtube", "track", video, f"https://www.youtube.com/watch?v={video}"
        if playlist:
            return "youtube", "playlist", playlist, f"https://www.youtube.com/playlist?list={playlist}"
        if host == "music.youtube.com" and re.fullmatch(r"browse/MP[A-Za-z0-9_-]{5,150}", path):
            return "youtube", "album", path.split("/")[1], f"https://music.youtube.com/{path}"
    if host == "api-v2.soundcloud.com" and re.fullmatch(r"tracks/[1-9][0-9]{0,19}", path):
        # Flat set children without a permalink keep their numeric identity.
        return "soundcloud", "track", path.split("/")[1], f"https://api-v2.soundcloud.com/{path}"
    if host in {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com"}:
        parts = path.split("/")
        if len(parts) == 3 and parts[1] == "sets":
            return "soundcloud", "playlist", None, f"https://soundcloud.com/{path}"
        if len(parts) == 2 and parts[1] not in {"tracks", "albums", "sets", "likes", "reposts", "popular-tracks"}:
            return "soundcloud", "track", None, f"https://soundcloud.com/{path}"
    raise ComponentError("unsupported_resource")


def run_tool(args, timeout=60):
    result = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        raise ComponentError("media_processing_failed")
    return result.stdout


def probe(path, *, decode=True):
    value = json.loads(run_tool([
        str(RUNTIME / "ffprobe"), "-v", "error", "-show_entries",
        "stream=codec_name,codec_type,sample_rate,bit_rate,duration:format=duration,format_name,size",
        "-of", "json", str(path),
    ]))
    audio = [s for s in value.get("streams", []) if s.get("codec_type") == "audio"]
    if len(audio) != 1:
        raise ComponentError("invalid_audio_streams")
    duration = float(value.get("format", {}).get("duration") or audio[0].get("duration") or 0)
    if not math.isfinite(duration) or duration <= 0 or path.stat().st_size > MAX_AUDIO:
        raise ComponentError("invalid_audio_duration")
    if decode:
        if audio[0].get("codec_name") not in SUPPORTED_CODECS.get(path.suffix[1:].lower(), set()):
            raise ComponentError("unsupported_output_codec")
        run_tool([str(RUNTIME / "ffmpeg"), "-v", "error", "-xerror", "-i", str(path),
                  "-map", "0:a:0", "-f", "null", "-"], timeout=180)
    return {
        "duration_seconds": duration, "codec": audio[0].get("codec_name"),
        "container": path.suffix[1:], "sample_rate": audio[0].get("sample_rate"),
        "bitrate": audio[0].get("bit_rate"), "file_size_bytes": path.stat().st_size,
    }


def entry(info, provider, position):
    if info is None:
        return {"entry_key": str(position), "position": position, "available": False}
    item_id = str(info.get("id") or "")
    valid_id = bool(re.fullmatch(r"[A-Za-z0-9_-]{11}" if provider == "youtube" else r"[1-9][0-9]*", item_id))
    url = f"https://www.youtube.com/watch?v={item_id}" if provider == "youtube" else info.get("webpage_url") or info.get("url")
    if url:
        validate_destination(url)
    return {
        "entry_key": f"{position}:{item_id}", "position": position,
        "provider": provider, "item_id": item_id or None, "url": url,
        "title": info.get("track") or info.get("title"),
        "artist": info.get("artist"), "duration_seconds": info.get("duration"),
        "available": valid_id and not info.get("is_live") and info.get("live_status") not in {"is_live", "is_upcoming"}
        and info.get("title") not in {"[Private video]", "[Deleted video]"}
        and info.get("availability") not in {"private", "premium_only", "subscriber_only", "needs_auth"},
    }


def operate(request):
    operation = request["operation"]
    if operation == "check":
        for executable in ("ffmpeg", "ffprobe", "deno"):
            if not (RUNTIME / executable).is_file():
                raise ComponentError("runtime_missing")
        return {"protocol_version": PROTOCOL_VERSION,
                "versions": {name: importlib.metadata.version(name) for name in ("yt-dlp", "yt-dlp-ejs")},
                "ffmpeg": run_tool([str(RUNTIME / "ffmpeg"), "-version"]).decode().splitlines()[0],
                "deno": run_tool([str(RUNTIME / "deno"), "--version"]).decode().splitlines()[0]}
    provider, kind, requested_id, url = identity(request["url"])
    if operation == "download" and kind != "track":
        raise ComponentError("single_item_required")
    budget = Budget(MAX_AUDIO if operation == "download" else MAX_MANIFEST * 8)
    handler = transport(budget)

    class ProviderDL(yt_dlp.YoutubeDL):
        @functools.cached_property
        def _request_director(self):
            return self.build_request_director([handler])

    options = {
        "quiet": True, "no_warnings": True, "logger": QuietLogger(),
        "cachedir": False, "proxy": "", "socket_timeout": 15,
        "retries": 0, "fragment_retries": 0, "extractor_retries": 0,
        "noplaylist": kind == "track", "playlistend": MAX_ITEMS + 1,
        "extract_flat": "in_playlist" if operation == "metadata" else False,
        "skip_download": True, "ignoreerrors": False, "lazy_playlist": False,
        "js_runtimes": {"deno": {"path": str(RUNTIME / "deno")}},
        "remote_components": set(), "ffmpeg_location": str(RUNTIME),
        "hls_prefer_native": True, "external_downloader": {"default": "native"},
        "concurrent_fragment_downloads": 1, "max_filesize": MAX_AUDIO,
        "format": "bestaudio/best", "overwrites": False,
    }
    with ProviderDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            raise ComponentError("metadata_unavailable")
        if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
            raise ComponentError("live_stream_unsupported")
        if operation == "metadata":
            entries = list(info.get("entries", [])) if kind != "track" else [info]
            if len(entries) > MAX_ITEMS:
                raise ComponentError("collection_item_limit")
            if kind != "track" and not entries:
                raise ComponentError("collection_empty_or_inaccessible")
            return {"provider": provider, "resource_type": kind, "resource_id": str(info.get("id") or requested_id),
                    "url": url, "title": info.get("title"),
                    "entries": [entry(child, provider, i) for i, child in enumerate(entries, 1)]}

        expected_id = str(request.get("item_id") or requested_id or "")
        if not expected_id or str(info.get("id")) != expected_id:
            raise ComponentError("source_identity_mismatch")
        if requested_id and expected_id != requested_id:
            raise ComponentError("source_identity_mismatch")
        raw_dir = Path(request["output_dir"])
        output_dir = raw_dir.resolve(strict=True)
        if raw_dir.absolute() != output_dir:
            raise ComponentError("workspace_symlink_refused")
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise ComponentError("empty_workspace_required")
        original = [f for f in info.get("formats", []) if f.get("format_id") == "download"]
        if provider == "soundcloud" and original:
            ydl.params["format"] = "download"
        ydl.params["skip_download"] = False
        ydl.params["outtmpl"]["default"] = str(output_dir / "audio.%(ext)s")
        final = ydl.process_ie_result(info, download=True)
        downloads = final.get("requested_downloads") or [final]
        raw_path = Path(downloads[0].get("filepath") or ydl.prepare_filename(downloads[0]))
        if raw_path.is_symlink():
            raise ComponentError("output_outside_workspace")
        path = raw_path.resolve(strict=True)
        if not path.is_relative_to(output_dir) or not path.is_file():
            raise ComponentError("output_outside_workspace")
        source = {"codec": downloads[0].get("acodec") or final.get("acodec"),
                  "bitrate_kbps": downloads[0].get("abr") or final.get("abr"),
                  "sample_rate": downloads[0].get("asr") or final.get("asr")}
        processing = "native"
        suffix = path.suffix[1:].lower()
        input_properties = probe(path, decode=False)
        if input_properties["codec"] not in SUPPORTED_CODECS.get(suffix, set()):
            # AAC can be remuxed to M4A; Opus/Vorbis require a supported encoding.
            remux = input_properties["codec"] in {"aac", "alac"}
            destination = output_dir / ("processed.m4a" if remux else "processed.mp3")
            run_tool([str(RUNTIME / "ffmpeg"), "-nostdin", "-v", "error", "-i", str(path),
                      "-map", "0:a:0", "-vn", "-c:a", "copy" if remux else "libmp3lame",
                      *([] if remux else ["-q:a", "2"]), str(destination)], timeout=180)
            path.unlink()
            path, processing = destination, "remux" if remux else "transcode"
        measured = probe(path)
        expected_duration = info.get("duration")
        if expected_duration and abs(measured["duration_seconds"] - expected_duration) > max(3, expected_duration * .02):
            raise ComponentError("incomplete_audio_output")
        return {"provider": provider, "item_id": expected_id, "effective_item_id": str(final["id"]),
                "output_filename": path.name, "source_properties": source,
                "output_properties": measured, "processing": processing}


def stop_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    # Also terminate grandchildren if the group leader already exited.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        # macOS can return EPERM after the final group member has exited.
        # A live leader must still fail closed if its group cannot be stopped.
        if process.poll() is None:
            raise
    process.wait(timeout=1)


def supervise(request):
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command.append(str(Path(__file__).resolve()))
    process = subprocess.Popen([*command, "--worker"], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
    def cancel(signum, frame):
        stop_group(process)
        raise ComponentError("operation_cancelled")
    previous_handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    for sig in previous_handlers:
        signal.signal(sig, cancel)
    try:
        output, _ = process.communicate(json.dumps(request).encode(), timeout=TIMEOUTS[request["operation"]])
    except subprocess.TimeoutExpired:
        raise ComponentError("operation_timeout") from None
    finally:
        stop_group(process)
        for sig, previous in previous_handlers.items():
            signal.signal(sig, previous)
    if process.returncode or len(output) > MAX_MANIFEST:
        raise ComponentError("component_worker_failed")
    return json.loads(output)


def main():
    try:
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384:
            raise ComponentError("request_too_large")
        request = json.loads(raw)
        if not isinstance(request, dict) or request.get("operation") not in TIMEOUTS:
            raise ComponentError("invalid_operation")
        if set(request) - {"operation", "url", "item_id", "output_dir"}:
            raise ComponentError("unsupported_request_options")
        if "--worker" in sys.argv:
            resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_AUDIO, MAX_AUDIO))
            with tempfile.TemporaryDirectory(prefix="syncbox-web-audio-") as temporary:
                os.environ["DENO_DIR"] = temporary
                value = {"result": "ok", **operate(request)}
        else:
            value = supervise(request)
        encoded = json.dumps(value)
        if len(encoded.encode()) > MAX_MANIFEST:
            raise ComponentError("manifest_size_limit")
        print(encoded)
    except (ComponentError, BoundaryError) as error:
        print(json.dumps({"result": "error", "error": str(error)}))
    except Exception as error:
        # Never expose provider URLs, tokens or upstream exception text.
        print(json.dumps({"result": "error", "error": failure_code(error)}))


if __name__ == "__main__":
    main()
