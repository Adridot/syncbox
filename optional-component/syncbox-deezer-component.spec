# PyInstaller onedir for the separately distributed macOS arm64 component.
# It is never copied into the base Syncbox application bundle.

from importlib.metadata import distribution
from pathlib import Path

from PyInstaller.building import build_main
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

_create_base_library_zip = build_main.create_base_library_zip


def _create_sorted_base_library_zip(filename, modules_toc, code_cache=None):
    return _create_base_library_zip(
        filename, sorted(modules_toc, key=lambda item: item[0]), code_cache
    )


build_main.create_base_library_zip = _create_sorted_base_library_zip

streamrip = distribution("streamrip")
streamrip_info = Path(streamrip._path)
datas = []
for relative in ("METADATA", "direct_url.json", "licenses/LICENSE"):
    source = streamrip_info / relative
    if not source.is_file():
        raise RuntimeError(f"missing required streamrip metadata: {relative}")
    datas.append((str(source), str(Path(streamrip_info.name) / Path(relative).parent)))
datas += collect_data_files("streamrip", includes=["config.toml"])
datas += copy_metadata("certifi")
datas += [("../release/licenses/optional", "licenses")]

a = Analysis(
    ["../scripts/run_b1_deezer_acquisition.py"],
    pathex=["../scripts"],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "_cffi_backend",
        "streamrip.client.client",
        "streamrip.client.deezer",
        "streamrip.client.downloadable",
    ],
    hookspath=["hooks"],
    runtime_hooks=[],
    excludes=[
        "_distutils_hack",
        "cffi",
        "packaging",
        "PIL.ImageCms",
        "PIL.ImageFont",
        "PIL.ImageMath",
        "PIL._imagingcms",
        "PIL._imagingft",
        "PIL._imagingmath",
        "pycparser",
        "setuptools",
        "streamrip.client.qobuz",
        "streamrip.client.soundcloud",
        "streamrip.client.tidal",
        "streamrip.rip",
    ],
    noarchive=False,
    optimize=0,
)

required_streamrip_metadata = {
    "streamrip-2.2.0.dist-info/METADATA",
    "streamrip-2.2.0.dist-info/direct_url.json",
    "streamrip-2.2.0.dist-info/licenses/LICENSE",
}
a.datas = [
    entry
    for entry in a.datas
    if not entry[0].startswith("streamrip-2.2.0.dist-info/")
    or entry[0] in required_streamrip_metadata
]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="syncbox-deezer-component",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    target_arch="arm64",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="syncbox-deezer-component",
)
