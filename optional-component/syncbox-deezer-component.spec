# PyInstaller onedir for the separately distributed macOS arm64 component.
# It is never copied into the base Syncbox application bundle.

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

datas = copy_metadata("streamrip")
datas += collect_data_files("streamrip", includes=["config.toml"])
datas += copy_metadata("certifi")
datas += [("THIRD_PARTY_NOTICES.txt", ".")]

a = Analysis(
    ["../poc/run_b1_deezer_acquisition.py"],
    pathex=["../poc"],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "_cffi_backend",
        "streamrip.client.client",
        "streamrip.client.deezer",
        "streamrip.client.downloadable",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "PIL",
        "streamrip.client.qobuz",
        "streamrip.client.soundcloud",
        "streamrip.client.tidal",
        "streamrip.rip",
    ],
    noarchive=False,
    optimize=0,
)
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
