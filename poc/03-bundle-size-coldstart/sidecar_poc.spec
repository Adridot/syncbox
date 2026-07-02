# PyInstaller spec - onedir per SPEC-UNIFIED 6.11; _cffi_backend hiddenimport and
# optimize=0 per SPEC-UNIFIED 6.12 (cffi breaks under bytecode optimization).

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=["_cffi_backend"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="syncbox-sidecar-poc",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="syncbox-sidecar-poc",
)
