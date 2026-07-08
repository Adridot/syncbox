# PyInstaller spec — onedir per SPEC-UNIFIED 6.11; recipe proven in POC #3
# (poc/03-bundle-size-coldstart: 51 MB, ~0.44 s warm cold-start, GO 2026-07-02).
# _cffi_backend hiddenimport and optimize=0 per SPEC-UNIFIED 6.12 (cffi breaks
# under bytecode optimization). Entrypoint = the composition root run as a
# script (same code path as `python -m syncbox`); pathex resolves the package
# from src/ — the sidecar has no build backend by design.
#
# Build:  .venv/bin/pyinstaller sidecar.spec
# Verify: .venv/bin/python ../shell/harness/test_packaged_sidecar.py

a = Analysis(
    ["src/syncbox/__main__.py"],
    pathex=["src"],
    binaries=[],
    # appdb loads the migration .sql through importlib.resources: the files go
    # in as datas and the package as a hiddenimport (resolved only at runtime,
    # invisible to static analysis).
    datas=[("src/syncbox/migrations/*.sql", "syncbox/migrations")],
    hiddenimports=["_cffi_backend", "syncbox.migrations"],
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
    name="syncbox-sidecar",
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
    name="syncbox-sidecar",
)
