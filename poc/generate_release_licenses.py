#!/usr/bin/env python3
"""Generate deterministic release license inventories and notice bundles."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

from packaging.licenses import InvalidLicenseExpression, canonicalize_license_expression
from packaging.markers import Marker, default_environment

REPO = Path(__file__).resolve().parents[1]
OUTPUT = REPO / "release" / "licenses"
PYTHON_RUNTIME_LICENSES = (
    REPO / "poc/license-overrides/python-build-standalone-20260127"
)
LICENSE_NAMES = re.compile(
    r"^(?:licen[cs]e|copying|notice|copyright|authors|unlicense)", re.IGNORECASE
)
CANONICAL = re.compile(r"[-_.]+")
LICENSE_OVERRIDES = {
    "aiofiles": "Apache-2.0",
    "aiosignal": "Apache-2.0",
    "deezer-py": "GPL-3.0-or-later",
    "markdown-it-py": "MIT",
    "mdurl": "MIT",
    "multidict": "Apache-2.0",
    "pathvalidate": "MIT",
    "pyinstaller": "GPL-2.0-or-later WITH Bootloader-exception",
    "pycryptodomex": "BSD-2-Clause AND LicenseRef-Public-Domain",
    "pyinstaller-hooks-contrib": "GPL-2.0-or-later AND Apache-2.0",
    "pyrekordbox": "MIT",
    "python-dateutil": "Apache-2.0 OR BSD-3-Clause",
    "sqlcipher3-wheels": "Zlib",
    "streamrip": "GPL-3.0-only",
}
NPM_LICENSE_OVERRIDES = {
    ("@vue/devtools-api", "6.6.4"): (
        REPO / "poc/license-overrides/vue-devtools-api-6.6.4-LICENSE"
    )
}
RUST_LICENSE_OVERRIDE_DIR = REPO / "poc/license-overrides/rust"
RUST_LICENSE_OVERRIDE_GROUPS = {
    "alloc-stdlib": ("alloc-stdlib-LICENSE",),
    "block2": ("objc2-LICENSE.md", "SPDX-3.28.0-MIT.txt"),
    "dispatch2": (
        "objc2-LICENSE.md",
        "SPDX-3.28.0-Apache-2.0.txt",
        "SPDX-3.28.0-MIT.txt",
        "SPDX-3.28.0-Zlib.txt",
    ),
    "objc2": ("objc2-LICENSE.md", "SPDX-3.28.0-MIT.txt"),
    "objc2-encode": ("objc2-LICENSE.md", "SPDX-3.28.0-MIT.txt"),
    "objc2-foundation": ("objc2-LICENSE.md", "SPDX-3.28.0-MIT.txt"),
    "selectors": ("SPDX-3.28.0-MPL-2.0.txt",),
    "unic-char-property": ("rust-unic-COPYRIGHT.md", "rust-unic-LICENSE-APACHE", "rust-unic-LICENSE-MIT"),
    "unic-char-range": ("rust-unic-COPYRIGHT.md", "rust-unic-LICENSE-APACHE", "rust-unic-LICENSE-MIT"),
    "unic-common": ("rust-unic-COPYRIGHT.md", "rust-unic-LICENSE-APACHE", "rust-unic-LICENSE-MIT"),
    "unic-ucd-ident": ("rust-unic-COPYRIGHT.md", "rust-unic-LICENSE-APACHE", "rust-unic-LICENSE-MIT"),
    "unic-ucd-version": ("rust-unic-COPYRIGHT.md", "rust-unic-LICENSE-APACHE", "rust-unic-LICENSE-MIT"),
}
for _framework in (
    "app-kit",
    "cloud-kit",
    "core-data",
    "core-foundation",
    "core-graphics",
    "core-image",
    "core-text",
    "core-video",
    "exception-helper",
    "quartz-core",
    "web-kit",
):
    RUST_LICENSE_OVERRIDE_GROUPS[f"objc2-{_framework}"] = (
        "objc2-LICENSE.md",
        "SPDX-3.28.0-Apache-2.0.txt",
        "SPDX-3.28.0-MIT.txt",
        "SPDX-3.28.0-Zlib.txt",
    )
ACCEPTED_REVIEW_LICENSES = {
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
CARGO_LICENSE_ALIASES = {
    ("brotli-decompressor", "BSD-3-Clause/MIT"): "BSD-3-Clause OR MIT",
    ("fnv", "Apache-2.0 / MIT"): "Apache-2.0 OR MIT",
    ("same-file", "Unlicense/MIT"): "Unlicense OR MIT",
    ("walkdir", "Unlicense/MIT"): "Unlicense OR MIT",
}
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


def canonical(name: str) -> str:
    return CANONICAL.sub("-", name).lower()


def normalized_license(name: str, expression: str, ecosystem: str) -> str:
    if ecosystem == "rust":
        expression = CARGO_LICENSE_ALIASES.get(
            (canonical(name), expression), expression
        )
    try:
        return str(canonicalize_license_expression(expression))
    except InvalidLicenseExpression as error:
        raise SystemExit(
            f"invalid SPDX license expression for {ecosystem} package {name}: "
            f"{expression!r}"
        ) from error


def license_ids(expression: str) -> set[str]:
    return {
        token
        for token in expression.replace("(", " ( ").replace(")", " ) ").split()
        if token not in {"AND", "OR", "WITH", "(", ")"}
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args: str, cwd: Path = REPO) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def source_tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise SystemExit(f"local dependency contains a symlink: {path}")
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


def source_from_lock(package: dict, lock_path: Path) -> dict:
    if package.get("source", {}).get("git"):
        return {"source": package["source"]["git"]}
    if package.get("source", {}).get("directory"):
        raw = Path(package["source"]["directory"])
        lexical = lock_path.parent / raw
        if lexical.is_symlink():
            raise SystemExit(f"local dependency is a symlink: {lexical}")
        root = lexical.resolve()
        try:
            relative = root.relative_to(REPO.resolve())
        except ValueError as error:
            raise SystemExit(f"local dependency escapes the repository: {raw}") from error
        if not root.is_dir():
            raise SystemExit(f"local dependency is not a directory: {raw}")
        version = json.loads((REPO / "ui/package.json").read_text())["version"]
        result = {
            "source": (
                f"https://github.com/Adridot/syncbox/tree/v{version}/"
                f"{relative.as_posix()}"
            ),
            "source_path": relative.as_posix(),
            "source_tree_sha256": source_tree_sha256(root),
        }
        if canonical(package["name"]) == "sqlcipher3-wheels":
            result.update(
                {
                    "upstream_declared_license": "MIT",
                    "upstream_source": (
                        "https://files.pythonhosted.org/packages/ae/c1/"
                        "414003d77549c444bafd636149ab3ace6f4e2cb4666c9955d54ad62096cb/"
                        "sqlcipher3-0.6.2.tar.gz"
                    ),
                    "upstream_source_sha256": (
                        "a2b675289ba8889f389625a21f3a01f1ff159a551b5b88fba8fd92da0e02380a"
                    ),
                    "upstream_source_size": 2663213,
                    "upstream_version": "0.6.2",
                }
            )
        return result
    if package.get("sdist", {}).get("url"):
        return {
            "source": package["sdist"]["url"],
            "source_sha256": package["sdist"]["hash"].removeprefix("sha256:"),
            "source_size": package["sdist"]["size"],
        }
    wheels = package.get("wheels", [])
    if wheels:
        return {
            "source": wheels[0]["url"],
            "source_sha256": wheels[0]["hash"].removeprefix("sha256:"),
            "source_size": wheels[0]["size"],
        }
    return {"source": "project source tree"}


def runtime_python_packages(lock_path: Path, root_name: str, python: str) -> dict:
    lock = tomllib.loads(lock_path.read_text())
    packages = {canonical(item["name"]): item for item in lock["package"]}
    environment = default_environment()
    environment.update(
        {
            "platform_machine": "arm64",
            "python_full_version": python,
            "python_version": ".".join(python.split(".")[:2]),
            "sys_platform": "darwin",
        }
    )
    pending = [canonical(item["name"]) for item in packages[root_name]["dependencies"]]
    result = {}
    while pending:
        name = pending.pop()
        if name in result:
            continue
        package = packages[name]
        result[name] = package
        for dependency in package.get("dependencies", []):
            marker = dependency.get("marker")
            if marker and not Marker(marker).evaluate(environment=environment):
                continue
            pending.append(canonical(dependency["name"]))
    return result


def distributions(site_packages: Path) -> dict[str, importlib.metadata.Distribution]:
    return {
        canonical(dist.metadata["Name"]): dist
        for dist in importlib.metadata.distributions(path=[str(site_packages)])
        if dist.metadata.get("Name")
    }


def installed_license(dist: importlib.metadata.Distribution, name: str) -> str:
    raw_declared = (
        dist.metadata.get("License-Expression")
        or dist.metadata.get("License")
        or ""
    )
    declared = raw_declared.splitlines()[0].strip() if raw_declared.splitlines() else ""
    if name in LICENSE_OVERRIDES:
        return LICENSE_OVERRIDES[name]
    if declared == "MPL 2.0":
        return "MPL-2.0"
    if not declared:
        raise SystemExit(f"missing license metadata for Python package {name}")
    return declared


def copy_file(source: Path, destination: Path) -> dict[str, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    legal_root = next(
        parent for parent in destination.parents if parent.name in {"base", "optional"}
    )
    return {
        "path": destination.relative_to(legal_root).as_posix(),
        "sha256": sha256(destination),
    }


def copy_distribution_licenses(
    dist: importlib.metadata.Distribution,
    output: Path,
    ecosystem: str,
    name: str,
    version: str,
) -> list[dict[str, str]]:
    candidates = []
    for item in dist.files or ():
        relative = Path(str(item))
        if "licenses" not in {part.lower() for part in relative.parts} and not LICENSE_NAMES.match(
            relative.name
        ):
            continue
        source = Path(dist.locate_file(item))
        if source.is_file() and not source.is_symlink():
            candidates.append((relative.as_posix(), source))
    if not candidates:
        raise SystemExit(f"missing installed license file for {ecosystem} package {name}")
    copied = []
    for index, (_, source) in enumerate(sorted(candidates)):
        destination = (
            output
            / "texts"
            / ecosystem
            / f"{name}-{version}"
            / f"{index:02d}-{source.name}"
        )
        copied.append(copy_file(source, destination))
    return copied


def python_inventory(
    target: str,
    output: Path,
    lock_path: Path,
    root_name: str,
    python: str,
    site_packages: Path,
) -> list[dict]:
    locked = runtime_python_packages(lock_path, root_name, python)
    all_locked = {
        canonical(item["name"]): item
        for item in tomllib.loads(lock_path.read_text())["package"]
    }
    installed = distributions(site_packages)
    entries = []
    for name, package in sorted(locked.items()):
        dist = installed.get(name)
        if dist is None or dist.version != package["version"]:
            raise SystemExit(f"Python environment drift for {name} {package['version']}")
        entries.append(
            {
                "ecosystem": "python",
                "license": installed_license(dist, name),
                "license_files": copy_distribution_licenses(
                    dist, output, "python", name, dist.version
                ),
                "name": name,
                "scope": f"{target}-runtime",
                "version": dist.version,
                **source_from_lock(package, lock_path),
            }
        )
    for name, dist in sorted(installed.items()):
        if name in locked or name == root_name or name not in all_locked:
            continue
        package = all_locked[name]
        if package.get("version") != dist.version:
            raise SystemExit(f"Python build environment drift for {name}")
        entries.append(
            {
                "distributed": False,
                "ecosystem": "python-build",
                "license": installed_license(dist, name),
                "license_files": copy_distribution_licenses(
                    dist, output, "python-build", name, dist.version
                ),
                "name": name,
                "scope": f"{target}-build-only",
                "version": dist.version,
                **source_from_lock(package, lock_path),
            }
        )
    return entries


def pnpm_integrities() -> dict[tuple[str, str], str]:
    result = {}
    current = None
    in_packages = False
    for line in (REPO / "pnpm-lock.yaml").read_text().splitlines():
        if line == "packages:":
            in_packages = True
            continue
        if in_packages and line == "snapshots:":
            break
        if not in_packages:
            continue
        package_match = re.match(r"^  (['\"]?)(.+)\1:$", line)
        if package_match:
            key = package_match.group(2)
            if "@" not in key:
                current = None
                continue
            name, raw_version = key.rsplit("@", 1)
            current = (name, raw_version.split("(", 1)[0])
            continue
        integrity_match = re.search(r"integrity: ([^},]+)", line)
        if current and integrity_match:
            result[current] = integrity_match.group(1).strip()
    return result


def pinned_pnpm() -> str:
    declarations = {
        json.loads((REPO / path).read_text())["packageManager"]
        for path in ("shell/package.json", "ui/package.json")
    }
    if len(declarations) != 1:
        raise SystemExit(f"pnpm package-manager declarations differ: {declarations}")
    declaration = declarations.pop()
    name, separator, expected = declaration.partition("@")
    if name != "pnpm" or not separator or not expected:
        raise SystemExit(f"invalid pnpm package-manager declaration: {declaration}")

    checked = set()
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / "pnpm"
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            continue
        resolved = candidate.resolve()
        if resolved in checked:
            continue
        checked.add(resolved)
        result = subprocess.run(
            [str(candidate), "--version"], capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip() == expected:
            return str(candidate)
    raise SystemExit(f"pnpm {expected} is not available on PATH")


def node_inventory(output: Path) -> list[dict]:
    data = json.loads(
        command(
            pinned_pnpm(),
            "list",
            "--prod",
            "--recursive",
            "--depth",
            "Infinity",
            "--json",
        )
    )
    packages: dict[tuple[str, str], dict] = {}

    def walk(node: dict) -> None:
        for dependency in node.get("dependencies", {}).values():
            key = (dependency["from"], dependency["version"])
            packages[key] = dependency
            walk(dependency)

    for importer in data:
        walk(importer)
    integrities = pnpm_integrities()
    entries = []
    for (name, version), dependency in sorted(packages.items()):
        package_root = Path(dependency["path"])
        metadata = json.loads((package_root / "package.json").read_text())
        license_name = metadata.get("license")
        if not isinstance(license_name, str) or not license_name:
            raise SystemExit(f"missing npm license metadata for {name}")
        files = [
            path
            for path in sorted(package_root.iterdir())
            if path.is_file() and not path.is_symlink() and LICENSE_NAMES.match(path.name)
        ]
        if not files and (name, version) in NPM_LICENSE_OVERRIDES:
            files = [NPM_LICENSE_OVERRIDES[(name, version)]]
        if not files:
            raise SystemExit(f"missing npm license file for {name}@{version}")
        copied = [
            copy_file(
                path,
                output
                / "texts"
                / "javascript"
                / f"{canonical(name)}-{version}"
                / f"{index:02d}-{path.name}",
            )
            for index, path in enumerate(files)
        ]
        entries.append(
            {
                "ecosystem": "javascript",
                "license": license_name,
                "license_files": copied,
                "name": name,
                "source_integrity": integrities[(name, version)],
                "scope": "base-production",
                "source": dependency["resolved"],
                "version": version,
            }
        )
    return entries


def rust_inventory(output: Path) -> list[dict]:
    metadata = json.loads(
        command(
            "cargo",
            "metadata",
            "--locked",
            "--filter-platform",
            "aarch64-apple-darwin",
            "--format-version",
            "1",
            cwd=REPO / "shell/src-tauri",
        )
    )
    packages = {
        (item["name"], item["version"]): item for item in metadata["packages"]
    }
    runtime = {
        match.groups()
        for line in command(
            "cargo",
            "tree",
            "--locked",
            "--target",
            "aarch64-apple-darwin",
            "--edges",
            "normal",
            "--prefix",
            "none",
            "--format",
            "{p}",
            cwd=REPO / "shell/src-tauri",
        ).splitlines()
        if (match := re.match(r"^(\S+) v(\S+)", line))
    }
    cargo_lock = {
        (item["name"], item["version"]): item
        for item in tomllib.loads((REPO / "shell/src-tauri/Cargo.lock").read_text())[
            "package"
        ]
    }
    entries = []
    for identifier in sorted(runtime):
        package = packages[identifier]
        if package["name"] == "syncbox-shell":
            continue
        license_name = package.get("license")
        if not license_name:
            raise SystemExit(f"missing Cargo license metadata for {package['name']}")
        package_root = Path(package["manifest_path"]).parent
        files = [
            path
            for path in sorted(package_root.iterdir())
            if path.is_file() and not path.is_symlink() and LICENSE_NAMES.match(path.name)
        ]
        if package.get("license_file"):
            files.append((package_root / package["license_file"]).resolve(strict=True))
        files = sorted(set(files))
        override_names = ()
        if not files and package["name"] in RUST_LICENSE_OVERRIDE_GROUPS:
            override_names = RUST_LICENSE_OVERRIDE_GROUPS[package["name"]]
            files = [RUST_LICENSE_OVERRIDE_DIR / name for name in override_names]
        if not files:
            raise SystemExit(
                f"missing Cargo license file for {package['name']} {package['version']}"
            )
        copied = [
            copy_file(
                path,
                output
                / "texts"
                / "rust"
                / f"{package['name']}-{package['version']}"
                / f"{index:02d}-{path.name}",
            )
            for index, path in enumerate(files)
        ]
        if license_name == "MIT/Apache-2.0":
            license_name = "MIT OR Apache-2.0"
        lock_package = cargo_lock[identifier]
        entry = {
            "crate_checksum": lock_package.get("checksum"),
            "ecosystem": "rust",
            "license": license_name,
            "license_files": copied,
            "name": package["name"],
            "repository": package.get("repository"),
            "scope": "base-runtime",
            "source": f"https://crates.io/crates/{package['name']}/{package['version']}",
            "version": package["version"],
        }
        vcs_path = package_root / ".cargo_vcs_info.json"
        vcs_commit = None
        if vcs_path.is_file():
            vcs_commit = json.loads(vcs_path.read_text()).get("git", {}).get("sha1")
            if vcs_commit:
                entry["source_commit"] = vcs_commit
        if override_names:
            override_sources = []
            for name in override_names:
                if name == "alloc-stdlib-LICENSE":
                    source = (
                        "https://raw.githubusercontent.com/dropbox/"
                        "rust-alloc-no-stdlib/"
                        "ae42d22078b98549e987d2f03d12df7b984fde47/LICENSE"
                    )
                elif name == "objc2-LICENSE.md":
                    if not vcs_commit:
                        raise SystemExit("missing objc2 source commit")
                    source = (
                        "https://raw.githubusercontent.com/madsmtm/objc2/"
                        f"{vcs_commit}/LICENSE.md"
                    )
                elif name.startswith("rust-unic-"):
                    if not vcs_commit:
                        raise SystemExit("missing rust-unic source commit")
                    upstream_name = name.removeprefix("rust-unic-")
                    source = (
                        "https://raw.githubusercontent.com/open-i18n/rust-unic/"
                        f"{vcs_commit}/{upstream_name}"
                    )
                elif name.startswith("SPDX-3.28.0-"):
                    source = (
                        "https://raw.githubusercontent.com/spdx/license-list-data/"
                        f"v3.28.0/text/{name.removeprefix('SPDX-3.28.0-')}"
                    )
                else:
                    raise SystemExit(f"missing Rust override provenance for {name}")
                override_sources.append(source)
            entry["license_file_sources"] = override_sources
        entries.append(entry)
    return entries


def build_runtime_entries(target: str, output: Path, site_packages: Path) -> list[dict]:
    if not PYTHON_RUNTIME_LICENSES.is_dir():
        raise SystemExit(f"missing pinned Python runtime license source: {PYTHON_RUNTIME_LICENSES}")
    pyinstaller = distributions(site_packages)["pyinstaller"]
    lock_path = REPO / (
        "sidecar/uv.lock" if target == "base" else "optional-component/uv.lock"
    )
    pyinstaller_lock = next(
        item
        for item in tomllib.loads(lock_path.read_text())["package"]
        if item["name"] == "pyinstaller"
    )
    bootloader_files = copy_distribution_licenses(
        pyinstaller,
        output,
        "build-runtime",
        "pyinstaller-bootloader",
        pyinstaller.version,
    )
    python_version = "3.14.2" if target == "base" else "3.13.11"
    provenance = json.loads((REPO / "release-build.json").read_text())[
        "python_build_standalone"
    ]
    archive_key = "base_archive" if target == "base" else "optional_archive"
    components = [
        {
            "license": "LicenseRef-CPython-Composite",
            "license_file": "LICENSE.cpython.txt",
            "name": "CPython",
            "source": f"https://www.python.org/ftp/python/{python_version}/Python-{python_version}.tar.xz",
            "source_sha256": (
                "ce543ab854bc256b61b71e9b27f831ffd1bfd60a479d639f8be7f9757cf573e9"
                if target == "base"
                else "16ede7bb7cdbfa895d11b0642fa0e523f291e6487194d53cf6d3b338c3a17ea2"
            ),
            "version": python_version,
        },
        {
            "license": "bzip2-1.0.6",
            "license_file": "LICENSE.bzip2.txt",
            "name": "bzip2",
            "source": "https://astral-sh.github.io/mirror/files/bzip2-1.0.8.tar.gz",
            "source_sha256": "ab5a03176ee106d3f0fa90e381da478ddae405918153cca248e682cd0c4a2269",
            "version": "1.0.8",
        },
        {
            "license": "MIT",
            "license_file": "LICENSE.expat.txt",
            "name": "Expat",
            "source": "https://github.com/libexpat/libexpat/releases/download/R_2_6_3/expat-2.6.3.tar.xz",
            "source_sha256": "274db254a6979bde5aad404763a704956940e465843f2a9bd9ed7af22e2c0efc",
            "version": "2.6.3",
        },
        {
            "license": "MIT",
            "license_file": "LICENSE.libffi.txt",
            "name": "libffi",
            "source": "https://github.com/libffi/libffi/releases/download/v3.4.6/libffi-3.4.6.tar.gz",
            "source_sha256": "b0dea9df23c863a7a50e825440f3ebffabd65df1497108e5d437747843895a4e",
            "version": "3.4.6",
        },
        {
            "license": "ISC",
            "license_file": "LICENSE.liblzma.txt",
            "name": "XZ liblzma",
            "source": "https://github.com/tukaani-project/xz/releases/download/v5.8.1/xz-5.8.1.tar.gz",
            "source_sha256": "507825b599356c10dca1cd720c9d0d0c9d5400b9de300af00e4d1ea150795543",
            "version": "5.8.1",
        },
        {
            "license": "BSD-3-Clause",
            "license_file": "LICENSE.libuuid.txt",
            "name": "libuuid",
            "source": "https://sourceforge.net/projects/libuuid/files/libuuid-1.0.3.tar.gz",
            "source_sha256": "46af3275291091009ad7f1b899de3d0cea0252737550e7919d17237997db5644",
            "version": "1.0.3",
        },
        {
            "license": "BSD-2-Clause",
            "license_file": "LICENSE.mpdecimal.txt",
            "name": "mpdecimal",
            "source": "https://www.bytereef.org/software/mpdecimal/releases/mpdecimal-4.0.0.tar.gz",
            "source_sha256": "942445c3245b22730fd41a67a7c5c231d11cb1b9936b9c0f76334fb7d0b4468c",
            "version": "4.0.0",
        },
        {
            "license": "Apache-2.0",
            "license_file": "LICENSE.openssl-3.txt",
            "name": "OpenSSL",
            "source": "https://github.com/openssl/openssl/releases/download/openssl-3.5.5/openssl-3.5.5.tar.gz",
            "source_sha256": "b28c91532a8b65a1f983b4c28b7488174e4a01008e29ce8e69bd789f28bc2a89",
            "version": "3.5.5",
        },
        {
            "license": "LicenseRef-SQLite-Public-Domain",
            "license_file": "LICENSE.sqlite.txt",
            "name": "SQLite",
            "source": "https://www.sqlite.org/2025/sqlite-autoconf-3500400.tar.gz",
            "source_sha256": "a3db587a1b92ee5ddac2f66b3edb41b26f9c867275782d46c3a088977d6a5b18",
            "version": "3.50.4",
        },
    ]
    if target == "base":
        components.append(
            {
                "license": "BSD-3-Clause",
                "license_file": "LICENSE.zstd.txt",
                "name": "Zstandard",
                "source": "https://github.com/python/cpython-source-deps/archive/refs/tags/zstd-1.5.7.tar.gz",
                "source_sha256": "f24b52470d12f466e9fa4fcc94e6c530625ada51d7b36de7fdc6ed7e6f499c8e",
                "version": "1.5.7",
            }
        )
    runtime_files = []
    for component in components:
        source = PYTHON_RUNTIME_LICENSES / component.pop("license_file")
        copied = copy_file(source, output / "texts/python-runtime" / source.name)
        component["license_files"] = [copied]
        runtime_files.append(copied)
    entries = [
        {
            "archive": provenance[archive_key],
            "archive_sha256": provenance[f"{archive_key}_sha256"],
            "embedded": f"libpython{'.'.join(python_version.split('.')[:2])}.dylib and PyInstaller-selected built-in modules",
            "ecosystem": "native-runtime",
            "license": "LicenseRef-CPython-and-Statically-Linked-Components",
            "license_files": runtime_files,
            "name": "python-build-standalone-cpython",
            "scope": f"{target}-embedded-runtime",
            "source": (
                "https://github.com/astral-sh/python-build-standalone/"
                "releases/tag/20260127"
            ),
            "source_archive_sha256": provenance["source_archive_sha256"],
            "statically_linked_components": components,
            "system_dynamic_libraries_not_distributed": [
                "libedit.3.dylib",
                "libncurses.5.4.dylib",
                "libpanel.5.4.dylib",
                "libz.1.dylib 1.2.12",
            ],
            "version": f"{python_version}+20260127",
        },
        {
            "ecosystem": "native-runtime",
            "license": "GPL-2.0-or-later WITH Bootloader-exception",
            "license_files": bootloader_files,
            "name": "pyinstaller-bootloader",
            "scope": f"{target}-executable-loader",
            "source": "https://github.com/pyinstaller/pyinstaller/tree/v6.21.0",
            "version": pyinstaller.version,
            "package_source": source_from_lock(pyinstaller_lock, lock_path),
        },
    ]
    return entries


def entry_license_files(entries: list[dict], ecosystem: str, name: str) -> list[dict]:
    return next(
        entry["license_files"]
        for entry in entries
        if entry["ecosystem"] == ecosystem and canonical(entry["name"]) == canonical(name)
    )


def native_override_files(output: Path, name: str, filenames: tuple[str, ...]) -> list[dict]:
    return [
        copy_file(
            REPO / "poc/license-overrides/native" / filename,
            output / "texts/bundled-native" / name / filename,
        )
        for filename in filenames
    ]


def native_entries(target: str, output: Path, entries: list[dict]) -> list[dict]:
    if target == "base":
        return [
            {
                "ecosystem": "bundled-native",
                "license": "MIT",
                "license_files": entry_license_files(entries, "python", "miniaudio"),
                "name": "miniaudio",
                "scope": "base-static-extension",
                "source": "https://github.com/mackron/miniaudio/tree/0.11.25",
                "version": "0.11.25",
            },
            {
                "ecosystem": "bundled-native",
                "license": "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0",
                "license_files": entry_license_files(entries, "python", "numpy"),
                "name": "NumPy macOS Accelerate wheel native extensions",
                "scope": "base-native-extensions",
                "source": (
                    "https://files.pythonhosted.org/packages/b5/59/"
                    "2b844c7a6e9deff69b404a66221e1542937734f65d5e6e39411876053862/"
                    "numpy-2.5.1-cp314-cp314-macosx_14_0_arm64.whl"
                ),
                "version": "2.5.1",
                "wheel_sha256": "efd736408cc97c79b9e6917338dfc8f06013b2274f992e96b1d9a81a71e2a2c2",
                "wheel_size": 5335944,
                "system_dependencies": [
                    {
                        "artifact_reference": "/System/Library/Frameworks/Accelerate.framework",
                        "distributed": False,
                        "name": "Apple Accelerate",
                        "source": "https://developer.apple.com/accelerate/",
                        "version": "macOS 14+ system framework",
                    }
                ],
            },
            {
                "bundled_components": [
                    {
                        "license": "LicenseRef-SQLite-Public-Domain",
                        "license_files": [
                            item
                            for item in entry_license_files(
                                entries,
                                "native-runtime",
                                "python-build-standalone-cpython",
                            )
                            if Path(item["path"]).name == "LICENSE.sqlite.txt"
                        ],
                        "name": "SQLite",
                        "source": "https://www.sqlite.org/2025/sqlite-src-3510100.zip",
                        "version": "3.51.1",
                    },
                ],
                "ecosystem": "bundled-native",
                "license": "BSD-3-Clause",
                "license_files": (
                    entry_license_files(entries, "python", "sqlcipher3-wheels")
                    + native_override_files(
                        output, "sqlcipher-4.12.0", ("sqlcipher-4.12.0-LICENSE.txt",)
                    )
                ),
                "name": "SQLCipher Community Edition",
                "scope": "base-static-extension",
                "source": "https://github.com/sqlcipher/sqlcipher/tree/v4.12.0",
                "system_dependencies": [
                    {
                        "artifact_reference": "/usr/lib/libSystem.B.dylib",
                        "distributed": False,
                        "name": "Apple CommonCrypto",
                        "source": (
                            "https://developer.apple.com/library/archive/"
                            "documentation/System/Conceptual/ManPages_iPhoneOS/"
                            "man3/CC_crypto.3cc.html"
                        ),
                        "version": "macOS 14+ system library",
                    },
                    {
                        "artifact_reference": (
                            "/System/Library/Frameworks/CoreFoundation.framework/"
                            "Versions/A/CoreFoundation"
                        ),
                        "distributed": False,
                        "name": "Apple CoreFoundation",
                        "source": "https://developer.apple.com/documentation/corefoundation",
                        "version": "macOS 14+ system framework",
                    },
                    {
                        "artifact_reference": (
                            "/System/Library/Frameworks/Security.framework/"
                            "Versions/A/Security"
                        ),
                        "distributed": False,
                        "name": "Apple Security",
                        "source": "https://developer.apple.com/documentation/security",
                        "version": "macOS 14+ system framework",
                    },
                ],
                "version": "4.12.0",
            },
        ]
    return [
        {
            "ecosystem": "bundled-native",
            "license": "MIT",
            "license_files": (
                entry_license_files(entries, "python", "pycares")
                + native_override_files(
                    output, "c-ares-1.34.5", ("c-ares-1.34.5-LICENSE.md",)
                )
            ),
            "name": "c-ares",
            "scope": "optional-static-extension",
            "source": "https://github.com/c-ares/c-ares/tree/v1.34.5",
            "version": "1.34.5",
        },
        {
            "ecosystem": "bundled-native",
            "license": "MIT",
            "license_files": (
                entry_license_files(entries, "python", "aiohttp")
                + native_override_files(
                    output, "llhttp", ("llhttp-LICENSE-MIT",)
                )
            ),
            "name": "llhttp",
            "scope": "optional-static-extension",
            "source": (
                "https://github.com/nodejs/llhttp/tree/"
                "96b15fb3bc00117d2db3df8e87fa6d3e9bcff328"
            ),
            "version": "9.4.1 (aiohttp 3.14.1 submodule 96b15fb3bc00117d2db3df8e87fa6d3e9bcff328)",
        },
        {
            "artifact_paths": ["PIL/_imaging.cpython-313-darwin.so"],
            "bundled_components": [
                {
                    "artifact_aliases": {
                        "libXau.6.0.0.dylib": "PIL/.dylibs/libXau.6.0.0.dylib"
                    },
                    "artifact_paths": ["PIL/.dylibs/libXau.6.0.0.dylib"],
                    "license": "MIT-open-group",
                    "license_files": entry_license_files(entries, "python", "pillow"),
                    "name": "libXau",
                    "source": "https://www.x.org/archive/individual/lib/libXau-1.0.11.tar.xz",
                    "version": "1.0.11",
                },
                {
                    "artifact_aliases": {
                        "libjpeg.62.4.0.dylib": "PIL/.dylibs/libjpeg.62.4.0.dylib"
                    },
                    "artifact_paths": ["PIL/.dylibs/libjpeg.62.4.0.dylib"],
                    "license": "IJG",
                    "license_files": entry_license_files(entries, "python", "pillow"),
                    "name": "libjpeg-turbo",
                    "source": "https://github.com/libjpeg-turbo/libjpeg-turbo/tree/3.0.3",
                    "version": "3.0.3",
                },
                {
                    "artifact_aliases": {
                        "liblzma.5.dylib": "PIL/.dylibs/liblzma.5.dylib"
                    },
                    "artifact_paths": ["PIL/.dylibs/liblzma.5.dylib"],
                    "license": "LicenseRef-XZ-Utils-Public-Domain",
                    "license_files": entry_license_files(entries, "python", "pillow"),
                    "name": "XZ liblzma",
                    "source": "https://github.com/tukaani-project/xz/tree/v5.4.5",
                    "version": "5.4.5",
                },
                {
                    "artifact_aliases": {
                        "libopenjp2.2.5.2.dylib": "PIL/.dylibs/libopenjp2.2.5.2.dylib"
                    },
                    "artifact_paths": ["PIL/.dylibs/libopenjp2.2.5.2.dylib"],
                    "license": "BSD-2-Clause",
                    "license_files": entry_license_files(entries, "python", "pillow"),
                    "name": "OpenJPEG",
                    "source": "https://github.com/uclouvain/openjpeg/tree/v2.5.2",
                    "version": "2.5.2",
                },
                {
                    "artifact_aliases": {
                        "libtiff.6.dylib": "PIL/.dylibs/libtiff.6.dylib"
                    },
                    "artifact_paths": ["PIL/.dylibs/libtiff.6.dylib"],
                    "license": "libtiff AND LicenseRef-libtiff-LZW",
                    "license_files": (
                        entry_license_files(entries, "python", "pillow")
                        + native_override_files(
                            output,
                            "libtiff-4.6.0",
                            ("libtiff-4.6.0-LZW-LICENSE.txt",),
                        )
                    ),
                    "name": "libtiff",
                    "source": "https://gitlab.com/libtiff/libtiff/-/tree/v4.6.0",
                    "version": "4.6.0",
                },
                {
                    "artifact_aliases": {
                        "libxcb.1.1.0.dylib": "PIL/.dylibs/libxcb.1.1.0.dylib"
                    },
                    "artifact_paths": ["PIL/.dylibs/libxcb.1.1.0.dylib"],
                    "license": "X11",
                    "license_files": entry_license_files(entries, "python", "pillow"),
                    "name": "libxcb",
                    "source": "https://www.x.org/archive/individual/lib/libxcb-1.17.0.tar.xz",
                    "version": "1.17.0",
                },
                {
                    "artifact_aliases": {
                        "libz.1.3.1.dylib": "PIL/.dylibs/libz.1.3.1.dylib"
                    },
                    "artifact_paths": ["PIL/.dylibs/libz.1.3.1.dylib"],
                    "license": "Zlib",
                    "license_files": entry_license_files(entries, "python", "pillow"),
                    "name": "zlib",
                    "source": "https://github.com/madler/zlib/tree/v1.3.1",
                    "version": "1.3.1",
                },
            ],
            "ecosystem": "bundled-native",
            "license": "HPND",
            "license_files": entry_license_files(entries, "python", "pillow"),
            "name": "Pillow macOS arm64 wheel native libraries",
            "scope": "optional-dynamic-libraries",
            "source": (
                "https://files.pythonhosted.org/packages/cf/76/"
                "f658cbfa49405e5ecbfb9ba42d07074ad9792031267e782d409fd8fe7c69/"
                "pillow-10.4.0-cp313-cp313-macosx_11_0_arm64.whl"
            ),
            "version": "10.4.0",
            "wheel_sha256": "6209bb41dc692ddfee4942517c19ee81b86c864b626dbfca272ec0f7cff5d9fb",
        },
    ]


def bundled_items(entry: dict):
    yield entry
    for field in ("statically_linked_components", "bundled_components"):
        for component in entry.get(field, []):
            yield from bundled_items(component)


def check_policy(target: str, entries: list[dict]) -> list[dict[str, str]]:
    reviewed = []
    for entry in entries:
        for item in bundled_items(entry):
            item["license"] = normalized_license(
                item["name"], item["license"], entry["ecosystem"]
            )
        if entry.get("distributed") is False:
            continue
        for item in bundled_items(entry):
            if item.get("distributed") is False:
                continue
            pair = (canonical(item["name"]), item["license"])
            if pair in CUSTOM_LICENSE_EXCEPTIONS[target]:
                continue
            if license_ids(item["license"]) <= PERMISSIVE_LICENSES:
                continue
            if pair not in ACCEPTED_REVIEW_LICENSES[target]:
                raise SystemExit(f"unaccepted license in {target}: {pair}")
            reviewed.append(
                {
                    "decision": "owner-approved for Syncbox v1 distribution",
                    "license": item["license"],
                    "name": item["name"],
                }
            )
    expected = ACCEPTED_REVIEW_LICENSES[target]
    actual = {(canonical(item["name"]), item["license"]) for item in reviewed}
    missing = expected - actual
    if missing:
        raise SystemExit(f"accepted review licenses are absent from {target}: {sorted(missing)}")
    return sorted(reviewed, key=lambda item: (item["name"].lower(), item["license"]))


def notice(target: str, entries: list[dict], reviewed: list[dict]) -> str:
    lines = [
        f"Syncbox {target} distribution third-party notices",
        "",
        "This reviewed inventory records the exact dependency versions and source",
        "locations used for the release. The accompanying license files preserve",
        "upstream notices. This evidence does not constitute legal advice or a claim",
        "of compliance beyond the material included here.",
        "",
        "Owner-approved review licenses",
        "",
    ]
    lines.extend(
        f"- {item['name']}: {item['license']} ({item['decision']})" for item in reviewed
    )
    if target == "base":
        lines.extend(
            [
                "",
                "Recorded upstream metadata discrepancy",
                "",
                "- sqlcipher3 0.6.2 declares MIT in its PyPI core metadata, while",
                "  the source distribution ships a Zlib LICENSE. The Syncbox fork",
                "  preserves that exact Zlib text and records both facts without",
                "  asserting an invented composite license expression.",
            ]
        )
    lines.extend(["", "Dependency inventory", ""])
    for entry in sorted(entries, key=lambda item: (item["ecosystem"], item["name"].lower(), item["version"])):
        lines.append(
            f"- [{entry['ecosystem']}] {entry['name']} {entry['version']} — "
            f"{entry['license']} — {entry['source']}"
        )
        for component in list(bundled_items(entry))[1:]:
            lines.append(
                f"  - {component['name']} {component['version']} — "
                f"{component['license']} — {component['source']}"
            )
    if target == "optional":
        lines.extend(
            [
                "",
                "Required binary attribution",
                "",
                "This software is based in part on the work of the Independent JPEG Group.",
            ]
        )
    lines.extend(
        [
            "",
            "Copyleft source availability",
            "",
        "The machine-readable inventory records the source URL and immutable hash",
        "or commit for each locked Python package. This includes mutagen and, in",
        "the optional distribution, deezer-py and streamrip. The streamrip source",
        "is pinned to commit 189acda489927719aa8591f6acdd7d67aecf929b.",
        "The publisher must retain these exact sources and make them available for",
        "as long as the corresponding binaries are offered; source requests may be",
        "made through https://github.com/Adridot/syncbox/issues.",
            "",
        ]
    )
    return "\n".join(lines)


def font_asset_entries(entries: list[dict]) -> list[dict]:
    result = []
    for name in ("@fontsource/geist-mono", "@fontsource/geist-sans"):
        package = next(
            entry
            for entry in entries
            if entry["ecosystem"] == "javascript" and entry["name"] == name
        )
        result.append(
            {
                "ecosystem": "font-asset",
                "license": "OFL-1.1",
                "license_files": package["license_files"],
                "name": name.removeprefix("@fontsource/"),
                "scope": "base-bundled-fonts",
                "source": package["source"],
                "source_integrity": package["source_integrity"],
                "version": package["version"],
            }
        )
    return result


def project_assets(target: str) -> list[dict[str, str]]:
    if target == "optional":
        return []
    return [
        {
            "artifact_path": artifact_path,
            "embedding": embedding,
            "license": "MIT",
            "provenance": "owner-confirmed original Syncbox project asset",
            "sha256": sha256(REPO / source_path),
            "source": (
                "https://github.com/Adridot/syncbox/blob/v0.2.2/" + source_path
            ),
            "source_path": source_path,
        }
        for source_path, artifact_path, embedding in PROJECT_ASSET_SPECS
    ]


def generate(root: Path) -> None:
    base = root / "base"
    optional = root / "optional"
    base.mkdir(parents=True)
    optional.mkdir(parents=True)
    shutil.copyfile(REPO / "LICENSE", base / "LICENSE")
    shutil.copyfile(REPO / "LICENSE", optional / "LICENSE")

    base_site = next((REPO / "sidecar/.venv/lib").glob("python*/site-packages"))
    optional_site = next(
        (REPO / "optional-component/.venv/lib").glob("python*/site-packages")
    )
    base_entries = python_inventory(
        "base",
        base,
        REPO / "sidecar/uv.lock",
        "syncbox",
        "3.14.2",
        base_site,
    )
    base_entries += build_runtime_entries("base", base, base_site)
    base_entries += node_inventory(base)
    base_entries += font_asset_entries(base_entries)
    base_entries += rust_inventory(base)
    base_entries += native_entries("base", base, base_entries)
    optional_entries = python_inventory(
        "optional",
        optional,
        REPO / "optional-component/uv.lock",
        "syncbox-deezer-component",
        "3.13.11",
        optional_site,
    )
    optional_entries += build_runtime_entries("optional", optional, optional_site)
    optional_entries += native_entries("optional", optional, optional_entries)

    for target, destination, entries in (
        ("base", base, base_entries),
        ("optional", optional, optional_entries),
    ):
        reviewed = check_policy(target, entries)
        inventory = {
            "artifact": target,
            "artifact_version": json.loads((REPO / "ui/package.json").read_text())[
                "version"
            ],
            "entries": sorted(
                entries,
                key=lambda item: (
                    item["ecosystem"],
                    item["name"].lower(),
                    item["version"],
                ),
            ),
            "inputs": {
                "cargo_lock_sha256": sha256(REPO / "shell/src-tauri/Cargo.lock")
                if target == "base"
                else None,
                "pnpm_lock_sha256": sha256(REPO / "pnpm-lock.yaml")
                if target == "base"
                else None,
                "python_lock_sha256": sha256(
                    REPO
                    / (
                        "sidecar/uv.lock"
                        if target == "base"
                        else "optional-component/uv.lock"
                    )
                ),
                "release_build_sha256": sha256(REPO / "release-build.json"),
            },
            "project": {
                "assets": project_assets(target),
                "license": "MIT",
                "license_sha256": sha256(destination / "LICENSE"),
                "name": "Syncbox",
                "source": "https://github.com/Adridot/syncbox",
            },
            "reviewed_licenses": reviewed,
            "schema": 1,
        }
        (destination / "dependency-inventory.json").write_text(
            json.dumps(inventory, indent=2, sort_keys=True) + "\n"
        )
        (destination / "THIRD_PARTY_NOTICES.txt").write_text(
            notice(target, entries, reviewed)
        )


def compare(expected: Path, actual: Path) -> None:
    expected_files = {
        path.relative_to(expected): sha256(path)
        for path in expected.rglob("*")
        if path.is_file()
    }
    actual_files = {
        path.relative_to(actual): sha256(path)
        for path in actual.rglob("*")
        if path.is_file()
    }
    if expected_files != actual_files:
        raise SystemExit("release license material is stale")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="syncbox-licenses-") as raw:
        generated = Path(raw) / "licenses"
        generate(generated)
        if args.check:
            compare(OUTPUT, generated)
        else:
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            if OUTPUT.exists():
                shutil.rmtree(OUTPUT)
            shutil.copytree(generated, OUTPUT)
    print("release license material is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
