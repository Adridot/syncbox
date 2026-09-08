from pathlib import Path
from PyInstaller.building import build_main
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

# Match the base and Deezer bundles' deterministic standard-library ordering.
_create_base_library_zip = build_main.create_base_library_zip


def _create_sorted_base_library_zip(filename, modules_toc, code_cache=None):
    return _create_base_library_zip(
        filename, sorted(modules_toc, key=lambda item: item[0]), code_cache
    )


build_main.create_base_library_zip = _create_sorted_base_library_zip

root = Path(SPECPATH)
datas = collect_data_files("yt_dlp") + collect_data_files("yt_dlp_ejs")
for name in ("yt-dlp", "yt-dlp-ejs", "certifi"):
    datas += copy_metadata(name)
datas += [(str(root / "licenses"), "licenses")]
datas += [(str(root / "README.md"), "."), (str(root / "native-lock.json"), "build-recipe"),
          (str(root.parent / "scripts/build_web_audio_native.py"), "build-recipe")]
datas += [(str(root / "vendor/licenses"), "vendor/licenses")]
datas += [(str(root / "vendor/build-info.json"), "vendor")]
datas += [(str(p), "vendor/sources") for p in (root / "vendor/sources").iterdir()
          if p.name.endswith((".tar.xz", ".tar.gz", ".patch", ".crate"))]
binaries = [(str(p), "vendor") for p in (root / "vendor").iterdir()
            if p.is_file() and (p.suffix == ".dylib" or p.name in {"ffmpeg", "ffprobe", "deno"})]

a = Analysis(
    [str(root / "runner.py")], pathex=[str(root)], binaries=binaries, datas=datas,
    hiddenimports=collect_submodules("yt_dlp.extractor") + collect_submodules("yt_dlp_ejs"),
    excludes=["pytest", "setuptools", "yt_dlp.networking._curlcffi"],
    noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, exclude_binaries=True, name="syncbox-web-audio-component",
          debug=False, strip=False, upx=False, console=True, target_arch="arm64")
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name="syncbox-web-audio-component")
