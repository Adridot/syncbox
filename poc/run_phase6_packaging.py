"""Validate fresh macOS arm64 base and optional-component artifacts.

This script is read-only. It checks the packaged runtime, architecture,
deployment target, ad-hoc signature, base-bundle exclusions, version, and
ZIP symlink preservation. Temporary component installation data is removed
before exit; the script prints one JSON result and creates no evidence files.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import plistlib
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from packaging.licenses import InvalidLicenseExpression, canonicalize_license_expression
from packaging.markers import Marker
from packaging.utils import canonicalize_name

if sys.flags.optimize:
    raise RuntimeError("release scanner must run without Python optimization")

REPO = Path(__file__).resolve().parents[1]
MACHO_MAGICS = {
    b"\xcf\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
}
BASE_FORBIDDEN = (
    b"deemix",
    b"streamrip-2.2.0.dist-info",
    b"streamrip/client/deezer.py",
    b"site-packages/streamrip",
    b"config.toml",
    b"pony" + b"tail:",
    b"/tmp/syncbox-premium-arl",
    # The build workspace path marks OUR environment. Probing Path.home()
    # instead false-positives on GitHub-hosted runners: upstream PyPI wheels
    # built on GH Actions (e.g. cffi) embed the runner's home as debug
    # paths — exactly the CI builder's own home. (The literal prefix is
    # deliberately not written here: the source scan probes Path.home().)
    # Rust already remaps the home (build_macos_release.py).
    str(REPO).encode().lower(),
)
BASE_FORBIDDEN_NATIVE = (
    "libgcc",
    "libgfortran",
    "libquadmath",
    "libscipy_openblas",
    "libopenblas",
)
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{32,}\b"),
)
ARL_SHAPED = re.compile(
    rb"(?<![0-9a-f])[0-9a-f]{96,512}(?![0-9a-f])", re.IGNORECASE
)
ARL_ASSIGNMENT = re.compile(
    rb"(?i)(?:['\"]?(?:deezer[._-]?)?arl['\"]?|DEEZER_ARL)"
    rb"\s*(?::|=|=>)\s*['\"]?[0-9a-f]{64,512}"
)
PERSONAL_HOME_PATH = re.compile(
    rb"/Users/(?!build(?:/|$)|<user>(?:/|$))[A-Za-z0-9._-]+/"
)
TEXT_SUFFIXES = {
    ".bash",
    ".cfg",
    ".cjs",
    ".conf",
    ".css",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".jsx",
    ".json",
    ".key",
    ".lock",
    ".md",
    ".mjs",
    ".pem",
    ".plist",
    ".properties",
    ".py",
    ".rs",
    ".sh",
    ".sql",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
    ".zsh",
}
EXPECTED_REVIEWED_LICENSES = {
    "base": {
        ("bidict", "MPL-2.0"),
        ("certifi", "MPL-2.0"),
        ("cssparser", "MPL-2.0"),
        ("cssparser-macros", "MPL-2.0"),
        ("dtoa-short", "MPL-2.0"),
        ("mutagen", "GPL-2.0-or-later"),
        ("option-ext", "MPL-2.0"),
        ("pyinstaller-bootloader", "GPL-2.0-or-later WITH Bootloader-exception"),
        ("selectors", "MPL-2.0"),
    },
    "optional": {
        ("certifi", "MPL-2.0"),
        ("deezer-py", "GPL-3.0-or-later"),
        ("mutagen", "GPL-2.0-or-later"),
        ("pyinstaller-bootloader", "GPL-2.0-or-later WITH Bootloader-exception"),
        ("streamrip", "GPL-3.0-only"),
    },
}
PERMISSIVE_LICENSES = {
    "0BSD",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "CC0-1.0",
    "HPND",
    "IJG",
    "ISC",
    "MIT",
    "MIT-0",
    "OFL-1.1",
    "PSF-2.0",
    "Unicode-3.0",
    "Unlicense",
    "Zlib",
    "bzip2-1.0.6",
    "libtiff",
    "MIT-open-group",
    "X11",
}
CUSTOM_LICENSE_EXCEPTIONS = {
    "base": {
        ("cpython", "LicenseRef-CPython-Composite"),
        (
            "python-build-standalone-cpython",
            "LicenseRef-CPython-and-Statically-Linked-Components",
        ),
        ("sqlite", "LicenseRef-SQLite-Public-Domain"),
    },
    "optional": {
        ("cpython", "LicenseRef-CPython-Composite"),
        (
            "libtiff",
            "libtiff AND LicenseRef-libtiff-LZW",
        ),
        ("xz liblzma", "LicenseRef-XZ-Utils-Public-Domain"),
        ("pycryptodomex", "BSD-2-Clause AND LicenseRef-Public-Domain"),
        (
            "python-build-standalone-cpython",
            "LicenseRef-CPython-and-Statically-Linked-Components",
        ),
        ("sqlite", "LicenseRef-SQLite-Public-Domain"),
    },
}
EXPECTED_OPTIONAL_CRYPTODOME_BINARIES = {
    "Cryptodome/Cipher/_raw_aes.abi3.so",
    "Cryptodome/Cipher/_raw_blowfish.abi3.so",
    "Cryptodome/Cipher/_raw_cbc.abi3.so",
    "Cryptodome/Cipher/_raw_ecb.abi3.so",
    "Cryptodome/Util/_cpuid_c.abi3.so",
}
PROJECT_NATIVE_ARTIFACTS = {
    "base": {"Contents/MacOS/syncbox-shell"},
    "optional": set(),
}
NATIVE_ARTIFACT_LICENSE_OWNERS = {
    "base": {
        "Contents/Resources/sidecar/syncbox-sidecar": ("pyinstaller-bootloader",),
        "Contents/Resources/sidecar/_internal/libpython3.14.dylib": (
            "python-build-standalone-cpython",
        ),
        "Contents/Resources/sidecar/_internal/_miniaudio.abi3.so": ("miniaudio",),
        "Contents/Resources/sidecar/_internal/_cffi_backend.cpython-314-darwin.so": (
            "cffi",
        ),
        "Contents/Resources/sidecar/_internal/sqlcipher3/_sqlite3.cpython-314-darwin.so": (
            "sqlcipher3-wheels",
            "SQLCipher Community Edition",
        ),
        "Contents/Resources/sidecar/_internal/psutil/_psutil_osx.abi3.so": (
            "psutil",
        ),
        "Contents/Resources/sidecar/_internal/rapidfuzz/process_cpp_impl.cpython-314-darwin.so": (
            "rapidfuzz",
        ),
        "Contents/Resources/sidecar/_internal/rapidfuzz/fuzz_cpp.cpython-314-darwin.so": (
            "rapidfuzz",
        ),
        "Contents/Resources/sidecar/_internal/rapidfuzz/utils_cpp.cpython-314-darwin.so": (
            "rapidfuzz",
        ),
        "Contents/Resources/sidecar/_internal/rapidfuzz/distance/_initialize_cpp.cpython-314-darwin.so": (
            "rapidfuzz",
        ),
        "Contents/Resources/sidecar/_internal/rapidfuzz/distance/metrics_cpp.cpython-314-darwin.so": (
            "rapidfuzz",
        ),
        **{
            f"Contents/Resources/sidecar/_internal/{path}": (
                "numpy",
                "NumPy macOS Accelerate wheel native extensions",
            )
            for path in (
                "numpy/linalg/_umath_linalg.cpython-314-darwin.so",
                "numpy/_core/_multiarray_tests.cpython-314-darwin.so",
                "numpy/_core/_multiarray_umath.cpython-314-darwin.so",
                "numpy/fft/_pocketfft_umath.cpython-314-darwin.so",
                "numpy/random/bit_generator.cpython-314-darwin.so",
                "numpy/random/_mt19937.cpython-314-darwin.so",
                "numpy/random/_philox.cpython-314-darwin.so",
                "numpy/random/_bounded_integers.cpython-314-darwin.so",
                "numpy/random/_pcg64.cpython-314-darwin.so",
                "numpy/random/_sfc64.cpython-314-darwin.so",
                "numpy/random/_common.cpython-314-darwin.so",
                "numpy/random/mtrand.cpython-314-darwin.so",
                "numpy/random/_generator.cpython-314-darwin.so",
            )
        },
        **{
            f"Contents/Resources/sidecar/_internal/sqlalchemy/cyextension/{name}.cpython-314-darwin.so": (
                "sqlalchemy",
            )
            for name in ("util", "processors", "collections", "resultproxy", "immutabledict")
        },
    },
    "optional": {
        "syncbox-deezer-component": ("pyinstaller-bootloader",),
        "_internal/ada92cb5d92a588d1b93__mypyc.cpython-313-darwin.so": (
            "charset-normalizer",
        ),
        "_internal/libpython3.13.dylib": ("python-build-standalone-cpython",),
        "_internal/_cffi_backend.cpython-313-darwin.so": ("cffi",),
        "_internal/aiohttp/_http_writer.cpython-313-darwin.so": (
            "aiohttp",
            "llhttp",
        ),
        "_internal/aiohttp/_http_parser.cpython-313-darwin.so": (
            "aiohttp",
            "llhttp",
        ),
        "_internal/aiohttp/_websocket/mask.cpython-313-darwin.so": ("aiohttp",),
        "_internal/aiohttp/_websocket/reader_c.cpython-313-darwin.so": ("aiohttp",),
        "_internal/pycares/_cares.abi3.so": ("pycares", "c-ares"),
        "_internal/propcache/_helpers_c.cpython-313-darwin.so": ("propcache",),
        "_internal/frozenlist/_frozenlist.cpython-313-darwin.so": ("frozenlist",),
        "_internal/charset_normalizer/cd.cpython-313-darwin.so": (
            "charset-normalizer",
        ),
        "_internal/charset_normalizer/md.cpython-313-darwin.so": (
            "charset-normalizer",
        ),
        "_internal/PIL/_imaging.cpython-313-darwin.so": (
            "pillow",
            "Pillow macOS arm64 wheel native libraries",
        ),
        "_internal/multidict/_multidict.cpython-313-darwin.so": ("multidict",),
        "_internal/yarl/_quoting_c.cpython-313-darwin.so": ("yarl",),
        **{
            f"_internal/Cryptodome/{path}": ("pycryptodomex",)
            for path in (
                "Util/_cpuid_c.abi3.so",
                "Cipher/_raw_cbc.abi3.so",
                "Cipher/_raw_aes.abi3.so",
                "Cipher/_raw_ecb.abi3.so",
                "Cipher/_raw_blowfish.abi3.so",
            )
        },
        **{
            f"_internal/PIL/.dylibs/{filename}": (
                "pillow",
                component,
            )
            for filename, component in (
                ("libxcb.1.1.0.dylib", "libxcb"),
                ("libjpeg.62.4.0.dylib", "libjpeg-turbo"),
                ("libXau.6.0.0.dylib", "libXau"),
                ("libz.1.3.1.dylib", "zlib"),
                ("libopenjp2.2.5.2.dylib", "OpenJPEG"),
                ("liblzma.5.dylib", "XZ liblzma"),
                ("libtiff.6.dylib", "libtiff"),
            )
        },
    },
}
EXPECTED_STREAMRIP_METADATA = {
    "METADATA",
    "direct_url.json",
    "licenses/LICENSE",
}
APP_IDENTIFIER = "io.github.adridot.syncbox"
LEGACY_APP_IDENTIFIER = b"dev.syncbox.app"
PROJECT_ASSET_SPECS = (
    (
        "shell/src-tauri/icons/icon.icns",
        "Contents/Resources/icon.icns",
        "bundle-file",
    ),
    (
        "shell/src-tauri/icons/128x128@2x.png",
        "Contents/MacOS/syncbox-shell",
        "embedded-exact-bytes",
    ),
    (
        "ui/src/assets/logo.png",
        "Contents/MacOS/syncbox-shell",
        "embedded-exact-bytes",
    ),
)


def run(*command, check=True):
    return subprocess.run(command, capture_output=True, text=True, check=check)


def mach_o_files(app: Path):
    for path in app.rglob("*"):
        if path.is_file() and not path.is_symlink():
            try:
                if path.read_bytes()[:4] in MACHO_MAGICS:
                    yield path
            except OSError:
                continue


def minimum_version(path: Path) -> tuple[int, ...]:
    output = run("xcrun", "vtool", "-show-build", str(path)).stdout
    match = re.search(r"\bminos\s+([0-9.]+)", output)
    if not match:
        raise AssertionError(f"no macOS deployment target: {path}")
    return tuple(int(part) for part in match.group(1).split("."))


def validate_arm64(path: Path) -> None:
    architectures = run("lipo", "-archs", str(path)).stdout.split()
    assert architectures == ["arm64"], f"unexpected architectures in {path}: {architectures}"


def validate_adhoc_signature(path: Path, *, deep: bool = False) -> None:
    verify = ["codesign", "--verify"]
    if deep:
        verify.append("--deep")
    verify.extend(("--strict", "--all-architectures", str(path)))
    run(*verify)
    display = run(
        "codesign",
        "--display",
        "--verbose=4",
        "--all-architectures",
        str(path),
    )
    details = (display.stdout + display.stderr).splitlines()
    assert "Signature=adhoc" in details, f"non-ad-hoc signature: {path}"
    assert "TeamIdentifier=not set" in details, f"code-signing team present: {path}"
    assert not any(line.startswith("Authority=") for line in details), (
        f"certificate authority present in ad-hoc artifact: {path}"
    )


def release_zip_datetime() -> tuple[int, int, int, int, int, int]:
    metadata = json.loads((REPO / "release-build.json").read_text())
    epoch = metadata["source_date_epoch"]
    value = datetime.fromtimestamp(epoch, timezone.utc)
    return (value.year, value.month, value.day, value.hour, value.minute, value.second)


def validate_zip_metadata(archive: Path, expected_root: str) -> int:
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        names = [item.filename for item in infos]
        assert names and names[0] == f"{expected_root}/"
        assert names == sorted(names, key=lambda name: name.rstrip("/")), (
            "ZIP entries are not deterministically ordered"
        )
        assert len(names) == len(set(names)), "ZIP contains duplicate entries"
        assert bundle.comment == b"", "ZIP archive comment is not empty"
        for item in infos:
            assert item.date_time == release_zip_datetime(), (
                f"ZIP timestamp drift: {item.filename}"
            )
            assert item.extra == b"" and item.comment == b"", (
                f"ZIP metadata field is not empty: {item.filename}"
            )
            kind = stat.S_IFMT(item.external_attr >> 16)
            mode = stat.S_IMODE(item.external_attr >> 16)
            if item.is_dir():
                assert kind == stat.S_IFDIR and mode == 0o755, item.filename
            elif kind == stat.S_IFLNK:
                assert mode == 0o777, item.filename
            else:
                assert kind == stat.S_IFREG and mode in {0o644, 0o755}, item.filename
    return len(infos)


def validate_archive(app: Path, archive: Path) -> int:
    expected_root = app.name
    source_nodes = {f"{expected_root}/": app}
    for path in app.rglob("*"):
        relative = path.relative_to(app).as_posix()
        is_dir = stat.S_ISDIR(path.lstat().st_mode)
        name = f"{expected_root}/{relative}{'/' if is_dir else ''}"
        source_nodes[name] = path

    validate_zip_metadata(archive, expected_root)
    with zipfile.ZipFile(archive) as bundle:
        nodes = {item.filename: item for item in bundle.infolist()}
        assert set(nodes) == set(source_nodes), "ZIP content does not match the app tree"
        archived_links = {
            name
            for name, item in nodes.items()
            if stat.S_IFMT(item.external_attr >> 16) == stat.S_IFLNK
        }
        for name, path in source_nodes.items():
            if stat.S_ISDIR(path.lstat().st_mode):
                expected = b""
            elif path.is_symlink():
                expected = os.readlink(path).encode()
            else:
                expected = path.read_bytes()
            assert bundle.read(name) == expected, f"ZIP payload mismatch: {name}"
            archived_mode = stat.S_IMODE(nodes[name].external_attr >> 16)
            if stat.S_ISDIR(path.lstat().st_mode):
                expected_mode = 0o755
            elif path.is_symlink():
                expected_mode = 0o777
            else:
                expected_mode = 0o755 if path.lstat().st_mode & 0o111 else 0o644
            assert archived_mode == expected_mode, f"ZIP mode mismatch: {name}"
    source_links = {
        name for name, path in source_nodes.items() if path.is_symlink()
    }
    assert archived_links == source_links
    return len(source_links)


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root)).encode()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        if path.is_symlink():
            digest.update(b"L" + os.readlink(path).encode())
        elif path.is_file():
            digest.update(b"F" + path.read_bytes())
    return digest.hexdigest()


def expected_project_assets(target: str) -> list[dict[str, str]]:
    if target == "optional":
        return []
    return [
        {
            "artifact_path": artifact_path,
            "embedding": embedding,
            "license": "MIT",
            "provenance": "owner-confirmed original Syncbox project asset",
            "sha256": hashlib.sha256((REPO / source_path).read_bytes()).hexdigest(),
            "source": (
                "https://github.com/Adridot/syncbox/blob/v0.2.2/" + source_path
            ),
            "source_path": source_path,
        }
        for source_path, artifact_path, embedding in PROJECT_ASSET_SPECS
    ]


def validate_project_assets(app: Path, assets: list[dict[str, str]]) -> None:
    for asset in assets:
        source = REPO / asset["source_path"]
        payload = source.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == asset["sha256"]
        packaged = app / asset["artifact_path"]
        if asset["embedding"] == "bundle-file":
            assert packaged.read_bytes() == payload, packaged
        else:
            assert packaged.read_bytes().count(payload) == 1, packaged


def license_ids(expression: str) -> set[str]:
    return {
        token
        for token in expression.replace("(", " ( ").replace(")", " ) ").split()
        if token not in {"AND", "OR", "WITH", "(", ")"}
    }


def bundled_items(entry: dict):
    yield entry
    for field in ("statically_linked_components", "bundled_components"):
        for component in entry.get(field, []):
            yield from bundled_items(component)


def validate_native_license_coverage(
    root: Path, target: str, native: list[Path], inventory: dict
) -> dict[str, int]:
    mapping = NATIVE_ARTIFACT_LICENSE_OWNERS[target]
    project_paths = PROJECT_NATIVE_ARTIFACTS[target]
    assert not project_paths.intersection(mapping)
    for relative in (*project_paths, *mapping):
        path = Path(relative)
        assert not path.is_absolute() and ".." not in path.parts

    actual = {path.relative_to(root).as_posix() for path in native}
    expected = project_paths | set(mapping)
    assert actual == expected, (
        f"{target} native artifact/license mapping differs; "
        f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
    )

    inventory_names = {
        canonicalize_name(item["name"])
        for entry in inventory["entries"]
        for item in bundled_items(entry)
    }
    for relative, owners in mapping.items():
        assert owners, f"native artifact has no license owner: {relative}"
        missing = {
            owner
            for owner in owners
            if canonicalize_name(owner) not in inventory_names
        }
        assert not missing, f"unknown native license owners for {relative}: {sorted(missing)}"
    return {
        "inventory_mapped": len(mapping),
        "project_owned": len(project_paths),
    }


def source_tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        assert not path.is_symlink(), f"local dependency contains a symlink: {path}"
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix().encode()
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update((path.stat().st_mode & 0o777).to_bytes(2, "big"))
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def validate_license_policy(target: str, entries: list[dict]) -> set[tuple[str, str]]:
    reviewed = set()
    for entry in entries:
        items = tuple(bundled_items(entry))
        for item in items:
            expression = item["license"]
            try:
                canonical = str(canonicalize_license_expression(expression))
            except InvalidLicenseExpression as error:
                raise AssertionError(
                    f"invalid SPDX license expression for {item['name']}: "
                    f"{expression!r}"
                ) from error
            assert canonical == expression, (
                f"non-canonical SPDX license expression for {item['name']}: "
                f"{expression!r} != {canonical!r}"
            )
        if entry.get("distributed") is False:
            continue
        for item in items:
            if item.get("distributed") is False:
                continue
            pair = (canonicalize_name(item["name"]), item["license"])
            if pair in CUSTOM_LICENSE_EXCEPTIONS[target]:
                continue
            if license_ids(item["license"]) <= PERMISSIVE_LICENSES:
                continue
            assert pair in EXPECTED_REVIEWED_LICENSES[target], (
                f"unaccepted license in {target}: {pair}"
            )
            reviewed.add(pair)
    return reviewed


def validate_license_bundle(root: Path, target: str) -> dict:
    expected = REPO / "release/licenses" / target
    expected_files = {
        path.relative_to(expected): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in expected.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    actual_files = {
        path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    assert actual_files == expected_files, f"{target} license bundle drift"
    assert (root / "LICENSE").read_bytes() == (REPO / "LICENSE").read_bytes()
    assert (root / "THIRD_PARTY_NOTICES.txt").is_file()

    inventory = json.loads((root / "dependency-inventory.json").read_text())
    canonical = json.loads((REPO / "ui/package.json").read_text())["version"]
    assert inventory["schema"] == 1
    assert inventory["artifact"] == target
    assert inventory["artifact_version"] == canonical
    assert inventory["project"]["license"] == "MIT"
    assert inventory["project"]["assets"] == expected_project_assets(target)
    assert inventory["project"]["license_sha256"] == hashlib.sha256(
        (root / "LICENSE").read_bytes()
    ).hexdigest()
    expected_inputs = {
        "cargo_lock_sha256": hashlib.sha256(
            (REPO / "shell/src-tauri/Cargo.lock").read_bytes()
        ).hexdigest()
        if target == "base"
        else None,
        "pnpm_lock_sha256": hashlib.sha256(
            (REPO / "pnpm-lock.yaml").read_bytes()
        ).hexdigest()
        if target == "base"
        else None,
        "python_lock_sha256": hashlib.sha256(
            (
                REPO
                / (
                    "sidecar/uv.lock"
                    if target == "base"
                    else "optional-component/uv.lock"
                )
            ).read_bytes()
        ).hexdigest(),
        "release_build_sha256": hashlib.sha256(
            (REPO / "release-build.json").read_bytes()
        ).hexdigest(),
    }
    assert inventory["inputs"] == expected_inputs

    reviewed = {
        (canonicalize_name(item["name"]), item["license"])
        for item in inventory["reviewed_licenses"]
    }
    independently_reviewed = validate_license_policy(target, inventory["entries"])
    assert reviewed == EXPECTED_REVIEWED_LICENSES[target]
    assert independently_reviewed == EXPECTED_REVIEWED_LICENSES[target]

    for entry in inventory["entries"]:
        if entry.get("source_path"):
            relative = Path(entry["source_path"])
            assert not relative.is_absolute() and ".." not in relative.parts
            source_root = REPO / relative
            assert source_root.is_dir() and not source_root.is_symlink()
            assert entry["source_tree_sha256"] == source_tree_sha256(source_root)
        for item in bundled_items(entry):
            assert "components" not in item, (
                f"unstructured native component list for {item['name']}"
            )
            assert item["name"] and item["version"] and item["source"]
            assert item["license_files"], f"missing license files for {item['name']}"
            for license_file in item["license_files"]:
                relative = Path(license_file["path"])
                assert not relative.is_absolute() and ".." not in relative.parts
                path = root / relative
                assert path.is_file(), path
                assert hashlib.sha256(path.read_bytes()).hexdigest() == license_file["sha256"]
        for dependency in entry.get("system_dependencies", []):
            assert dependency.get("distributed") is False
            assert dependency.get("name") and dependency.get("version")
            assert dependency.get("source") and dependency.get("artifact_reference")

    names = {canonicalize_name(entry["name"]) for entry in inventory["entries"]}
    if target == "base":
        assert "streamrip" not in names and "deezer-py" not in names
    else:
        streamrip = next(entry for entry in inventory["entries"] if entry["name"] == "streamrip")
        assert streamrip["source"].endswith(
            "#189acda489927719aa8591f6acdd7d67aecf929b"
        )

    return {
        "entries": len(inventory["entries"]),
        "files": len(actual_files),
        "project_assets": inventory["project"]["assets"],
        "reviewed_licenses": [
            {"name": name, "license": license_name}
            for name, license_name in sorted(reviewed)
        ],
    }


def runtime_license_inventory(
    project: Path | None = None,
    root_package: str = "syncbox",
    legal_root: Path | None = None,
) -> dict[str, dict[str, str]]:
    project = project or REPO / "sidecar"
    lock = tomllib.loads((project / "uv.lock").read_text())
    packages = {
        canonicalize_name(package["name"]): package for package in lock["package"]
    }
    pending = [
        canonicalize_name(dep["name"])
        for dep in packages[canonicalize_name(root_package)]["dependencies"]
    ]
    runtime = set()
    while pending:
        name = pending.pop()
        if name in runtime:
            continue
        runtime.add(name)
        for dependency in packages[name].get("dependencies", []):
            if dependency.get("marker") and not Marker(dependency["marker"]).evaluate():
                continue
            pending.append(canonicalize_name(dependency["name"]))

    installed = {
        canonicalize_name(dist.metadata["Name"]): dist
        for dist in importlib.metadata.distributions()
    }
    inventoried_licenses = {}
    if legal_root is not None:
        legal_inventory = json.loads(
            (legal_root / "dependency-inventory.json").read_text()
        )
        inventoried_licenses = {
            canonicalize_name(entry["name"]): entry["license"]
            for entry in legal_inventory["entries"]
            if entry["ecosystem"] == "python"
            and entry.get("distributed") is not False
        }
    inventory = {}
    for name in sorted(runtime):
        dist = installed.get(name)
        assert dist is not None, f"locked runtime distribution is not installed: {name}"
        expected_version = packages[name]["version"]
        assert dist.version == expected_version, (
            f"runtime version drift for {name}: {dist.version} != {expected_version}"
        )
        license_name = inventoried_licenses.get(name) or (
            dist.metadata.get("License-Expression")
            or dist.metadata.get("License")
            or "UNKNOWN"
        ).splitlines()[0]
        assert license_name != "UNKNOWN", f"runtime license is unknown: {name}"
        inventory[name] = {"version": dist.version, "license": license_name}
    return inventory


def optional_license_probe(executable: Path) -> dict:
    python = REPO / "optional-component/.venv/bin/python"
    assert python.is_file(), f"missing locked optional Python environment: {python}"
    result = run(
        str(python),
        str(Path(__file__).resolve()),
        "--frozen-license-probe",
        str(executable),
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


def frozen_distribution_inventory(archive_listing: str) -> dict[str, str]:
    marker = "Contents of 'PYZ.pyz' (PYZ):"
    lines = archive_listing.splitlines()
    assert marker in lines, "PyInstaller PYZ archive listing is missing"
    modules = {
        line.strip().split(".", 1)[0]
        for line in lines[lines.index(marker) + 1 :]
        if line.startswith(" ")
    }
    package_map = importlib.metadata.packages_distributions()
    unmapped = {
        name
        for name in modules
        if name not in sys.stdlib_module_names
        and name != "syncbox"
        and not name.startswith("_sysconfigdata_")
        and name not in package_map
    }
    assert not unmapped, f"unmapped frozen Python modules: {sorted(unmapped)}"
    distributions = {
        canonicalize_name(distribution)
        for module in modules
        for distribution in package_map.get(module, ())
    }
    installed = {
        canonicalize_name(dist.metadata["Name"]): dist.version
        for dist in importlib.metadata.distributions()
    }
    missing = distributions - installed.keys()
    assert not missing, f"frozen distributions are not installed: {sorted(missing)}"
    return {name: installed[name] for name in sorted(distributions)}


def validate_runtime_license_alignment(
    legal_root: Path,
    runtime_licenses: dict[str, dict[str, str]],
    frozen_distributions: dict[str, str],
    required_packages: dict[str, str],
) -> dict:
    inventory = json.loads((legal_root / "dependency-inventory.json").read_text())
    inventoried = {
        canonicalize_name(entry["name"]): entry
        for entry in inventory["entries"]
        if entry["ecosystem"] == "python" and entry.get("distributed") is not False
    }
    assert runtime_licenses.keys() <= inventoried.keys(), (
        "locked runtime distributions absent from license inventory: "
        f"{sorted(runtime_licenses.keys() - inventoried.keys())}"
    )
    for name, metadata in runtime_licenses.items():
        assert inventoried[name]["version"] == metadata["version"], (
            f"inventoried runtime version drift for {name}: "
            f"{inventoried[name]['version']} != {metadata['version']}"
        )
    assert frozen_distributions.keys() <= runtime_licenses.keys(), (
        "frozen distributions absent from the locked runtime graph: "
        f"{sorted(frozen_distributions.keys() - runtime_licenses.keys())}"
    )
    for name, version in frozen_distributions.items():
        assert runtime_licenses[name]["version"] == version, (
            f"frozen runtime version drift for {name}: "
            f"{version} != {runtime_licenses[name]['version']}"
        )
    required_versions = {
        canonicalize_name(name): version
        for name, version in required_packages.items()
    }
    required = required_versions.keys()
    assert required <= frozen_distributions.keys(), (
        f"packaging-check distributions absent from frozen PYZ: "
        f"{sorted(required - frozen_distributions.keys())}"
    )
    for name, version in required_versions.items():
        assert frozen_distributions[name] == version, (
            f"packaging-check version drift for {name}: "
            f"{version} != {frozen_distributions[name]}"
        )
    return {
        "frozen_distributions": frozen_distributions,
        "frozen_distribution_count": len(frozen_distributions),
        "locked_runtime_distribution_count": len(runtime_licenses),
    }


def validate_source_secrets() -> int:
    skipped = {
        ".git",
        ".idea",
        ".playwright-mcp",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "target",
        "testdata",
    }
    checked = 0
    for path in REPO.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if any(part in skipped for part in path.relative_to(REPO).parts):
            continue
        relative = path.relative_to(REPO)
        raw = path.read_bytes()
        for pattern in SECRET_PATTERNS:
            assert not pattern.search(raw), f"secret-shaped value in source file {path}"
        is_text = (
            path.suffix.lower() in TEXT_SUFFIXES
            or path.name == ".env"
            or path.name.startswith(".env.")
        )
        if not is_text:
            checked += 1
            continue
        assert not ARL_SHAPED.search(raw), f"ARL-shaped value in source file {path}"
        assert not ARL_ASSIGNMENT.search(raw), f"ARL value in source file {path}"
        assert str(Path.home()).encode() not in raw, f"local home path in source file {path}"
        if "tests" not in relative.parts:
            assert not PERSONAL_HOME_PATH.search(raw), (
                f"personal macOS home path in source file {path}"
            )
        checked += 1
    return checked


def validate_sorted_base_library(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    assert names == sorted(names), f"non-deterministic base_library.zip order: {path}"
    return len(names)


def validate_optional_component(archive: Path, manifest_path: Path) -> dict:
    archive = archive.resolve(strict=True)
    manifest_path = manifest_path.resolve(strict=True)
    manifest = json.loads(manifest_path.read_text())
    assert archive.name == manifest["archive"]
    assert archive.stat().st_size == manifest["size"]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["sha256"]
    assert manifest["platform"] == "macos" and manifest["architecture"] == "arm64"
    zip_entries = validate_zip_metadata(archive, manifest["root"])

    sys.path.insert(0, str(REPO / "sidecar/src"))
    from syncbox import acquisition

    previous = os.environ.get(acquisition.COMPONENT_ARCHIVE_ENV)
    os.environ[acquisition.COMPONENT_ARCHIVE_ENV] = str(archive)
    try:
        with tempfile.TemporaryDirectory(prefix="syncbox-component-scan-") as raw_data:
            status = acquisition.install_component(raw_data)
            assert status["installed"] is True
            root = acquisition.component_root(raw_data)
            executable = acquisition.component_executable(raw_data)
            check = json.loads(run(str(executable), "--check").stdout)
            assert check["result"] == "CHECK_PASSED"
            assert check["streamrip_commit"] == manifest["streamrip_commit"]
            assert check["streamrip_version"] == manifest["streamrip_version"]
            assert check["certifi_version"] == manifest["certifi_version"]
            assert check["pillow_version"] == manifest["pillow_version"]
            assert check["pillow_wheel"] == manifest["pillow_wheel"]
            assert (
                check["pillow_wheel_sha256"]
                == manifest["pillow_wheel_sha256"]
            )
            assert check["artwork"] == "pillow_jpeg_ready"
            assert check["cryptography"] == "aes_blowfish_ready"

            help_text = run(str(executable), "--help").stdout.lower()
            for forbidden in ("ffmpeg", "qobuz", "soundcloud", "tidal"):
                assert forbidden not in help_text
            assert not any("ffmpeg" in path.name.lower() for path in root.rglob("*"))
            internal = root / "_internal"
            license_bundle = validate_license_bundle(
                internal / "licenses", "optional"
            )
            license_inventory = json.loads(
                (internal / "licenses/dependency-inventory.json").read_text()
            )
            streamrip_metadata = (
                internal
                / f"streamrip-{manifest['streamrip_version']}.dist-info"
            )
            assert {
                path.relative_to(streamrip_metadata).as_posix()
                for path in streamrip_metadata.rglob("*")
                if path.is_file()
            } == EXPECTED_STREAMRIP_METADATA
            assert not any(path.suffix == ".db" for path in root.rglob("*"))
            base_library_modules = validate_sorted_base_library(
                internal / "base_library.zip"
            )

            cryptodome_binaries = {
                path.relative_to(internal).as_posix()
                for path in (internal / "Cryptodome").rglob("*")
                if path.is_file()
            }
            assert cryptodome_binaries == EXPECTED_OPTIONAL_CRYPTODOME_BINARIES
            pillow_binaries = {
                path.relative_to(internal).as_posix()
                for path in (internal / "PIL").rglob("*")
                if path.is_file()
            }
            pillow_entry = next(
                entry
                for entry in license_inventory["entries"]
                if entry["name"] == "Pillow macOS arm64 wheel native libraries"
            )
            expected_pillow_binaries = {
                artifact
                for item in bundled_items(pillow_entry)
                for artifact in item.get("artifact_paths", [])
            }
            assert pillow_binaries == expected_pillow_binaries
            pillow_aliases = {
                alias: target
                for item in bundled_items(pillow_entry)
                for alias, target in item.get("artifact_aliases", {}).items()
            }
            for alias, target in pillow_aliases.items():
                alias_path = internal / alias
                assert alias_path.is_symlink(), alias_path
                assert os.readlink(alias_path) == target, alias_path

            native = list(mach_o_files(root))
            assert native, "optional component has no Mach-O files"
            native_license_coverage = validate_native_license_coverage(
                root, "optional", native, license_inventory
            )
            targets = []
            for path in native:
                validate_arm64(path)
                validate_adhoc_signature(path)
                targets.append(minimum_version(path))
            effective_minimum = max(targets)
            assert effective_minimum <= (14, 0), effective_minimum

            for path in root.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    raw = path.read_bytes()
                    # REPO, not Path.home(): upstream wheels built on GitHub
                    # Actions embed the runner-home prefix, colliding with
                    # the CI builder's home (see BASE_FORBIDDEN).
                    assert str(REPO).encode() not in raw, (
                        f"local build tree path in optional component: {path}"
                    )
                    for pattern in SECRET_PATTERNS:
                        assert not pattern.search(raw), f"secret-shaped value in {path}"
                    if path.suffix.lower() in TEXT_SUFFIXES:
                        assert not ARL_SHAPED.search(raw), f"ARL-shaped value in {path}"
                        assert not ARL_ASSIGNMENT.search(raw), f"ARL value in {path}"

            modules = run(
                str(Path(os.environ.get("PYI_ARCHIVE_VIEWER", "pyi-archive_viewer"))),
                "-r",
                "-b",
                str(executable),
            ).stdout.lower()
            assert "streamrip.client.deezer" in modules
            assert "cryptodome.cipher.blowfish" in modules
            for forbidden in (
                "streamrip.client.qobuz",
                "streamrip.client.soundcloud",
                "streamrip.client.tidal",
                "streamrip.rip.cli",
                "streamrip.rip.main",
            ):
                assert forbidden not in modules, forbidden
            license_alignment = optional_license_probe(executable)
            frozen_licenses = validate_runtime_license_alignment(
                internal / "licenses",
                license_alignment["runtime_licenses"],
                license_alignment["frozen_distributions"],
                {
                    "certifi": check["certifi_version"],
                    "pillow": check["pillow_version"],
                    "streamrip": check["streamrip_version"],
                },
            )
            return {
                "archive": archive.name,
                "archive_bytes": archive.stat().st_size,
                "archive_sha256": manifest["sha256"],
                "archive_entries": zip_entries,
                "archive_source_date_epoch": json.loads(
                    (REPO / "release-build.json").read_text()
                )["source_date_epoch"],
                "base_library_modules": base_library_modules,
                "installed_check": check,
                "mach_o_files": len(native),
                "adhoc_signed_mach_o_files": len(native),
                "native_license_coverage": native_license_coverage,
                "effective_minimum_macos": ".".join(map(str, effective_minimum)),
                "streamrip_license_present": True,
                "streamrip_metadata": sorted(EXPECTED_STREAMRIP_METADATA),
                "ffmpeg_binary": False,
                "soundcloud_interface": False,
                "provider_client_modules": ["deezer"],
                "pillow_native_files": sorted(expected_pillow_binaries),
                "pillow_native_aliases": pillow_aliases,
                "cryptodome_native_files": sorted(
                    EXPECTED_OPTIONAL_CRYPTODOME_BINARIES
                ),
                "license_bundle": license_bundle,
                "frozen_license_alignment": frozen_licenses,
            }
    finally:
        if previous is None:
            os.environ.pop(acquisition.COMPONENT_ARCHIVE_ENV, None)
        else:
            os.environ[acquisition.COMPONENT_ARCHIVE_ENV] = previous


def validate(
    app: Path,
    archive: Path | None,
    component_archive: Path | None,
    component_manifest: Path,
) -> dict:
    if archive is None or component_archive is None:
        raise ValueError(
            "full release scan requires both --archive and --component-archive"
        )
    app = app.resolve(strict=True)
    assert app.suffix == ".app"
    info_path = app / "Contents/Info.plist"
    shell = app / "Contents/MacOS/syncbox-shell"
    sidecar = app / "Contents/Resources/sidecar/syncbox-sidecar"
    migrations = app / "Contents/Resources/sidecar/_internal/syncbox/migrations"
    ca_file = app / "Contents/Resources/sidecar/_internal/certifi/cacert.pem"
    embedded_manifest = (
        app / "Contents/Resources/sidecar/_internal/syncbox/optional_component.json"
    )
    legal_root = app / "Contents/Resources/sidecar/_internal/licenses"
    for required in (
        info_path,
        shell,
        sidecar,
        migrations,
        ca_file,
        embedded_manifest,
        legal_root,
    ):
        assert required.exists(), f"missing packaged resource: {required}"
    license_bundle = validate_license_bundle(legal_root, "base")
    license_inventory = json.loads(
        (legal_root / "dependency-inventory.json").read_text()
    )
    validate_project_assets(app, license_bundle["project_assets"])
    assert embedded_manifest.read_bytes() == component_manifest.resolve(strict=True).read_bytes()
    component_name = json.loads(embedded_manifest.read_text())["component"]
    assert not any(path.name == component_name for path in app.rglob("*"))

    canonical = json.loads((REPO / "ui/package.json").read_text())["version"]
    with info_path.open("rb") as handle:
        info = plistlib.load(handle)
    assert info["CFBundleShortVersionString"] == canonical
    assert info["CFBundleVersion"] == canonical
    assert info["CFBundleIdentifier"] == APP_IDENTIFIER
    assert info["LSMinimumSystemVersion"] == "14.0"

    native = list(mach_o_files(app))
    assert native, "no Mach-O files found"
    native_license_coverage = validate_native_license_coverage(
        app, "base", native, license_inventory
    )
    deployment_targets = []
    for path in native:
        validate_arm64(path)
        validate_adhoc_signature(path)
        linkage = run("otool", "-L", str(path)).stdout.lower()
        for forbidden in BASE_FORBIDDEN_NATIVE:
            assert forbidden not in linkage, (
                f"unexpected native dependency {forbidden!r} in {path}"
            )
        deployment_targets.append(minimum_version(path))
    effective_minimum = max(deployment_targets)
    assert effective_minimum <= (14, 0), effective_minimum

    runtime = json.loads(run(str(sidecar), "--packaging-check").stdout)
    assert runtime["ok"] is True and runtime["architecture"] == "arm64"
    assert runtime["streamrip_importable"] is False
    assert runtime["packages"]["sqlcipher3-wheels"] == (
        "0.6.2+syncbox.commoncrypto.1"
    )
    assert runtime["sqlcipher"] == "4.12.0 community"
    assert runtime["sqlcipher_provider"] == "commoncrypto"
    assert runtime["sqlcipher_provider_version"]
    assert runtime["sqlcipher_status"] == "1"
    assert runtime["api_port"] == 8766
    assert runtime["oauth_callback_port"] == 8765
    base_library_modules = validate_sorted_base_library(
        app / "Contents/Resources/sidecar/_internal/base_library.zip"
    )

    sqlcipher_extensions = list(
        app.glob(
            "Contents/Resources/sidecar/_internal/sqlcipher3/"
            "_sqlite3*.so"
        )
    )
    assert len(sqlcipher_extensions) == 1, sqlcipher_extensions
    sqlcipher_linkage = run("otool", "-L", str(sqlcipher_extensions[0])).stdout
    assert "/System/Library/Frameworks/Security.framework/" in sqlcipher_linkage
    assert "/System/Library/Frameworks/CoreFoundation.framework/" in sqlcipher_linkage
    assert "/usr/lib/libSystem.B.dylib" in sqlcipher_linkage
    assert "libcrypto" not in sqlcipher_linkage.lower()
    assert "openssl" not in sqlcipher_linkage.lower()

    validate_adhoc_signature(app, deep=True)

    assert not any(app.rglob("direct_url.json")), (
        "base artifact must not expose local or VCS installation paths"
    )

    for path in app.rglob("*"):
        if path.is_file() and not path.is_symlink():
            raw = path.read_bytes()
            data = raw.lower()
            assert LEGACY_APP_IDENTIFIER not in data, (
                f"legacy application identifier in {path}"
            )
            for marker in BASE_FORBIDDEN:
                assert marker not in data, f"forbidden marker {marker!r} in {path}"
            for pattern in SECRET_PATTERNS:
                assert not pattern.search(raw), f"secret-shaped value in {path}"
            if path.suffix.lower() in TEXT_SUFFIXES:
                assert not ARL_SHAPED.search(raw), f"ARL-shaped value in {path}"
                assert not ARL_ASSIGNMENT.search(raw), f"ARL value in {path}"

    archive_listing = run(
        str(Path(os.environ.get("PYI_ARCHIVE_VIEWER", "pyi-archive_viewer"))),
        "-r",
        "-b",
        str(sidecar),
    ).stdout
    archive_modules = archive_listing.lower()
    assert "streamrip" not in archive_modules
    assert "deemix" not in archive_modules

    licenses = runtime_license_inventory()
    frozen_licenses = validate_runtime_license_alignment(
        legal_root,
        licenses,
        frozen_distribution_inventory(archive_listing),
        runtime["packages"],
    )
    forbidden_packages = {
        name for name in licenses if any(term in name for term in ("streamrip", "deemix", "deezer"))
    }
    assert not forbidden_packages, sorted(forbidden_packages)
    gpl_packages = {
        name for name, metadata in licenses.items() if "gpl" in metadata["license"].lower()
    }
    symlinks = validate_archive(app, archive.resolve(strict=True))
    component = validate_optional_component(component_archive, component_manifest)
    source_secret_files = validate_source_secrets()
    return {
        "ok": True,
        "version": canonical,
        "architecture": "arm64",
        "declared_minimum_macos": info["LSMinimumSystemVersion"],
        "effective_minimum_macos": ".".join(map(str, effective_minimum)),
        "mach_o_files": len(native),
        "adhoc_signed_mach_o_files": len(native),
        "native_license_coverage": native_license_coverage,
        "runtime_packages": runtime["packages"],
        "base_library_modules": base_library_modules,
        "app_bytes": sum(
            path.stat().st_size
            for path in app.rglob("*")
            if path.is_file() and not path.is_symlink()
        ),
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "archive_content_match": True,
        "archive_symlinks": symlinks,
        "app_tree_sha256": tree_hash(app),
        "developer_id": False,
        "gpl_runtime_packages": sorted(gpl_packages),
        "license_bundle": license_bundle,
        "frozen_license_alignment": frozen_licenses,
        "runtime_licenses": licenses,
        "notarized": False,
        "streamrip_component_in_base": False,
        "streamrip_importable_in_base": runtime["streamrip_importable"],
        "optional_component": component,
        "source_secret_files_scanned": source_secret_files,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("app", type=Path, nargs="?")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--component-archive", type=Path)
    parser.add_argument("--component-only", action="store_true")
    parser.add_argument("--frozen-license-probe", type=Path)
    parser.add_argument(
        "--component-manifest",
        type=Path,
        default=REPO / "sidecar/src/syncbox/optional_component.json",
    )
    args = parser.parse_args()
    if args.frozen_license_probe is not None:
        if args.app is not None or args.component_only:
            parser.error("frozen license probe does not accept an app or component mode")
        listing = run(
            str(Path(os.environ.get("PYI_ARCHIVE_VIEWER", "pyi-archive_viewer"))),
            "-r",
            "-b",
            str(args.frozen_license_probe.resolve(strict=True)),
        ).stdout
        print(
            json.dumps(
                {
                    "frozen_distributions": frozen_distribution_inventory(listing),
                    "runtime_licenses": runtime_license_inventory(
                        REPO / "optional-component",
                        "syncbox-deezer-component",
                        REPO / "release/licenses/optional",
                    ),
                },
                sort_keys=True,
            )
        )
        return
    if args.component_only:
        if args.app is not None:
            parser.error("app cannot be used with --component-only")
        if args.component_archive is None:
            parser.error("--component-archive is required with --component-only")
        result = validate_optional_component(
            args.component_archive,
            args.component_manifest,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    if args.app is None:
        parser.error("app is required unless --component-only is used")
    if args.archive is None or args.component_archive is None:
        parser.error(
            "--archive and --component-archive are both required for a full release scan"
        )
    result = validate(
        args.app,
        args.archive,
        args.component_archive,
        args.component_manifest,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
