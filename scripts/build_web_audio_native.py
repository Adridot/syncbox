"""Build the owner's approved LGPL audio tools for the isolated macOS component."""

import hashlib
import difflib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1] / "web-audio-component"
BUILD = Path("/tmp/syncbox-web-audio-native") / hashlib.sha256(
    (ROOT / "native-lock.json").read_bytes() + Path(__file__).read_bytes()
).hexdigest()[:16]
PREFIX = BUILD / "install"
VENDOR = ROOT / "vendor"


def run(args, cwd=None, env=None):
    subprocess.run(args, cwd=cwd, env=env, check=True)


def main():
    if (platform.system(), platform.machine()) != ("Darwin", "arm64"):
        raise RuntimeError("native build requires macOS arm64")
    pins = json.loads((ROOT / "native-lock.json").read_text())
    sources = VENDOR / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "MACOSX_DEPLOYMENT_TARGET": "14.0"}
    for name, pin in pins.items():
        archive = sources / pin["url"].rsplit("/", 1)[-1]
        if not archive.exists():
            with urllib.request.urlopen(pin["url"], timeout=60) as response:
                with archive.open("wb") as output:
                    shutil.copyfileobj(response, output)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != pin["sha256"]:
            raise RuntimeError(f"{name} source checksum mismatch")
        if name == "deno":
            with zipfile.ZipFile(archive) as bundle:
                (VENDOR / "deno").write_bytes(bundle.read("deno"))
            (VENDOR / "deno").chmod(0o755)
            continue
        source = BUILD / f"{name}-{pin['version']}"
        if not source.exists():
            with tarfile.open(archive) as bundle:
                bundle.extractall(BUILD, filter="data")

    # LAME's optional mpglib decoder is excluded; FFmpeg supplies decoding.
    lame_flags = [f"--prefix={PREFIX}", "--disable-frontend", "--disable-decoder",
                  "--disable-static", "--enable-shared"]
    lame = BUILD / f"lame-{pins['lame']['version']}"
    symbols = lame / "include/libmp3lame.sym"
    original_symbols = symbols.read_text()
    filtered_symbols = "".join(line for line in original_symbols.splitlines(keepends=True)
                               if not line.startswith(("hip_", "lame_decode", "lame_init_old")))
    if filtered_symbols != original_symbols:
        # LAME 3.100 exports decoder symbols even with --disable-decoder.
        # Keep the exact distribution patch alongside the unmodified source archive.
        (sources / "lame-3.100-encoder-only.patch").write_text("".join(difflib.unified_diff(
            original_symbols.splitlines(keepends=True), filtered_symbols.splitlines(keepends=True),
            fromfile="a/include/libmp3lame.sym", tofile="b/include/libmp3lame.sym")))
        symbols.write_text(filtered_symbols)
    if not (PREFIX / "lib/libmp3lame.0.dylib").exists():
        run(["./configure", *lame_flags], cwd=lame, env=env)
        run(["make", "-j4"], cwd=lame, env=env)
        run(["make", "install"], cwd=lame, env=env)

    flags = [
        f"--prefix={PREFIX}", "--disable-autodetect", "--disable-everything",
        "--disable-gpl", "--disable-nonfree", "--disable-network",
        "--disable-doc", "--disable-debug", "--disable-ffplay",
        "--disable-avdevice", "--disable-swscale", "--disable-static",
        "--enable-shared", "--enable-ffmpeg", "--enable-ffprobe",
        "--enable-libmp3lame", f"--extra-cflags=-I{PREFIX / 'include'}",
        f"--extra-ldflags=-L{PREFIX / 'lib'}", "--enable-protocol=file,pipe",
        "--enable-demuxer=mov,matroska,ogg,mp3,flac,wav,aiff,aac,mpegts",
        "--enable-muxer=mp3,mp4,ipod,flac,wav,aiff,null",
        "--enable-decoder=aac,aac_fixed,alac,flac,mp3,mp3float,opus,vorbis,pcm_s16le,pcm_s16be,pcm_s24le,pcm_s24be,pcm_s32le,pcm_s32be,pcm_f32le,pcm_f64le",
        "--enable-encoder=libmp3lame,pcm_s16le",
        "--enable-parser=aac,aac_latm,flac,mpegaudio,opus,vorbis",
        "--enable-bsf=aac_adtstoasc,extract_extradata",
        "--enable-filter=aresample,aformat,anull,atrim,asetpts",
    ]
    ffmpeg = BUILD / f"ffmpeg-{pins['ffmpeg']['version']}"
    if not (PREFIX / "bin/ffmpeg").exists():
        run(["./configure", *flags], cwd=ffmpeg, env=env)
        run(["make", "-j4"], cwd=ffmpeg, env=env)
        run(["make", "install"], cwd=ffmpeg, env=env)

    # Use loader-relative dylibs so the component works without Homebrew/PATH.
    libraries = sorted((PREFIX / "lib").glob("*.dylib"))
    for source in [PREFIX / "bin/ffmpeg", PREFIX / "bin/ffprobe", *libraries]:
        target = VENDOR / source.name
        if source.is_symlink():
            continue
        shutil.copy2(source, target)
        deps = subprocess.check_output(["otool", "-L", str(target)], text=True)
        for line in deps.splitlines()[1:]:
            dep = line.strip().split(" (", 1)[0]
            if dep.startswith(str(PREFIX)):
                basename = Path(dep).name
                # Resolve versioned aliases to the copied physical filename.
                basename = (PREFIX / "lib" / basename).resolve().name
                run(["install_name_tool", "-change", dep, f"@loader_path/{basename}", str(target)])
        if target.suffix == ".dylib":
            run(["install_name_tool", "-id", f"@loader_path/{target.name}", str(target)])
        run(["codesign", "--force", "--sign", "-", str(target)])

    license_dir = VENDOR / "licenses"
    license_dir.mkdir(exist_ok=True)
    shutil.copy2(ffmpeg / "COPYING.LGPLv2.1", license_dir / "FFmpeg-LGPL-2.1.txt")
    shutil.copy2(lame / "COPYING", license_dir / "LAME-LGPL-2.0.txt")
    with urllib.request.urlopen(
        f"https://raw.githubusercontent.com/denoland/deno/v{pins['deno']['version']}/LICENSE.md", timeout=30
    ) as response:
        (license_dir / "Deno-LICENSE.md").write_bytes(response.read())
    metadata = {
        "platform": "macos-arm64", "deployment_target": "14.0",
        "dependencies": pins, "lame_configure": lame_flags, "ffmpeg_configure": flags,
        "compiler": subprocess.check_output(["clang", "--version"], text=True),
        "artifacts": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in VENDOR.iterdir() if p.is_file() and p.name != "build-info.json"},
    }
    (VENDOR / "build-info.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({"result": "NATIVE_BUILD_PASSED", "directory": str(VENDOR)}))


if __name__ == "__main__":
    main()
