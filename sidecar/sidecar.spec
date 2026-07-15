# PyInstaller spec — onedir per SPEC-UNIFIED 6.11. Frozen behavior must be
# validated from a fresh build; source comments are not POC evidence.
# _cffi_backend hiddenimport and optimize=0 per SPEC-UNIFIED 6.12 (cffi breaks
# under bytecode optimization). Entrypoint = the composition root run as a
# script (same code path as `python -m syncbox`); pathex resolves the package
# from src/ — the sidecar has no build backend by design.
#
# Build:  .venv/bin/pyinstaller sidecar.spec

from importlib.metadata import distribution
from pathlib import Path

from PyInstaller.building import build_main
from PyInstaller.utils.hooks import copy_metadata


# PyInstaller 6.21 writes base_library.zip in graph-discovery order. Sorting
# the input fixes the measured cross-root ZIP-order drift without changing any
# module payload.
_create_base_library_zip = build_main.create_base_library_zip


def _create_sorted_base_library_zip(filename, modules_toc, code_cache=None):
    return _create_base_library_zip(
        filename, sorted(modules_toc, key=lambda item: item[0]), code_cache
    )


build_main.create_base_library_zip = _create_sorted_base_library_zip


runtime_metadata = []
for distribution_name in (
    "certifi",
    "miniaudio",
    "numpy",
    "pyrekordbox",
    "send2trash",
):
    runtime_metadata += copy_metadata(distribution_name)

# ``copy_metadata`` copies the complete dist-info directory, including pip's
# local ``direct_url.json`` with an absolute build path. Runtime diagnostics
# need only METADATA to resolve the binding version; redistribution notices are
# provided by the reviewed license bundle below.
sqlcipher_info = Path(distribution("sqlcipher3-wheels")._path)
sqlcipher_metadata = sqlcipher_info / "METADATA"
if not sqlcipher_metadata.is_file():
    raise RuntimeError("missing sqlcipher3-wheels METADATA")
runtime_metadata.append((str(sqlcipher_metadata), sqlcipher_info.name))

a = Analysis(
    ["src/syncbox/__main__.py"],
    pathex=["src"],
    binaries=[],
    # appdb loads the migration .sql through importlib.resources: the files go
    # in as datas and the package as a hiddenimport (resolved only at runtime,
    # invisible to static analysis).
    datas=runtime_metadata + [
        ("../release/licenses/base", "licenses"),
        ("src/syncbox/migrations/*.sql", "syncbox/migrations"),
        ("src/syncbox/optional_component.json", "syncbox"),
    ],
    hiddenimports=["_cffi_backend", "syncbox.migrations"],
    hookspath=[],
    runtime_hooks=[],
    # Development/build tooling must not leak into the production archive.
    excludes=["_distutils_hack", "_pytest", "pytest", "setuptools"],
    noarchive=False,
    optimize=0,
)

# Installed-project RECORD is optional. Its console-script hashes encode the
# absolute venv shebang even though those scripts are not distributed. Keep
# METADATA/license data, but omit RECORD from the frozen, installer-managed
# runtime so the resource seal is independent of the source root.
a.datas = [
    entry
    for entry in a.datas
    if not entry[0].endswith(".dist-info/RECORD")
]
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
    target_arch="arm64",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="syncbox-sidecar",
)
