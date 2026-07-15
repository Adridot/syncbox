#!/usr/bin/env python3
"""Build the macOS release with a controlled reproducible environment."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SHELL = REPO / "shell"
CANONICAL_PYTHON_INSTALL_DIR = Path("/tmp/syncbox-release-python-20260127")
LOCAL_BUILD_PRODUCTS = (
    REPO / "sidecar/vendor/sqlcipher3-commoncrypto/build",
    REPO / "sidecar/vendor/sqlcipher3-commoncrypto/sqlcipher3_wheels.egg-info",
)
# Fields owned by the Apple host, not by any lockfile. CI runners cannot
# match the owner's machine on these, so SYNCBOX_RELEASE_HOST_TOOLCHAIN=unpinned
# logs them instead of enforcing them; every other pin stays fail-closed.
HOST_TOOLCHAIN_KEYS = (
    "apple_clang",
    "apple_ld",
    "developer_dir",
    "macos_build",
    "macos_sdk",
    "macos_sdk_path",
)


def _is_pinned(section: str, name: str) -> bool:
    if section != "toolchain" or name not in HOST_TOOLCHAIN_KEYS:
        return True
    return os.environ.get("SYNCBOX_RELEASE_HOST_TOOLCHAIN") != "unpinned"


def _clean_local_build_products() -> None:
    for path in LOCAL_BUILD_PRODUCTS:
        shutil.rmtree(path, ignore_errors=True)


def _release_environment() -> dict[str, str]:
    metadata = json.loads((REPO / "release-build.json").read_text())
    if metadata.get("schema") != 1:
        raise SystemExit("unsupported release-build.json schema")
    epoch = metadata.get("source_date_epoch")
    if not isinstance(epoch, int) or epoch < 315532800:
        raise SystemExit("release source_date_epoch must be a ZIP-compatible integer")
    release = metadata.get("release") or {}
    version = json.loads((REPO / "ui/package.json").read_text())["version"]
    try:
        declared_epoch = datetime.fromisoformat(
            release["source_date_epoch_utc"].replace("Z", "+00:00")
        )
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise SystemExit("release source_date_epoch provenance is invalid") from error
    if (
        release.get("version") != version
        or release.get("source_date_epoch_basis") != "versioned-release-metadata"
        or declared_epoch.tzinfo != timezone.utc
        or int(declared_epoch.timestamp()) != epoch
    ):
        raise SystemExit("release source_date_epoch provenance does not match metadata")

    environment = os.environ.copy()
    cargo_overrides = {
        "CARGO_BUILD_BUILD_DIR",
        "CARGO_BUILD_INCREMENTAL",
        "CARGO_BUILD_RUSTC",
        "CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER",
        "CARGO_BUILD_RUSTC_WRAPPER",
        "CARGO_BUILD_RUSTDOC",
        "CARGO_BUILD_RUSTDOCFLAGS",
        "CARGO_BUILD_RUSTFLAGS",
        "CARGO_BUILD_TARGET",
        "CARGO_BUILD_TARGET_DIR",
        "CARGO_ENCODED_RUSTDOCFLAGS",
        "CARGO_ENCODED_RUSTFLAGS",
        "CARGO_TARGET_DIR",
        "RUSTC",
        "RUSTC_WORKSPACE_WRAPPER",
        "RUSTC_WRAPPER",
        "RUSTDOC",
        "RUSTDOCFLAGS",
        "RUSTFLAGS",
    }
    toolchain_overrides = {
        "API_PRIVATE_KEYS_DIR",
        "AR",
        "ARCHFLAGS",
        "CC",
        "CFLAGS",
        "CODESIGN_ALLOCATE",
        "CPPFLAGS",
        "CXX",
        "CXXFLAGS",
        "DEVELOPER_DIR",
        "LD",
        "LDFLAGS",
        "RANLIB",
        "RUSTC_BOOTSTRAP",
        "RUSTUP_TOOLCHAIN",
        "SDKROOT",
    }
    for name in tuple(environment):
        if (
            name in cargo_overrides
            or name in toolchain_overrides
            or name.startswith("APPLE_")
            or name.startswith("CARGO_PROFILE_")
            or name.startswith("CARGO_TARGET_")
            or name.startswith("NODE_")
            or name.startswith("PYTHON")
            or name.startswith("TAURI_")
            or name.startswith("UV_")
            or name.startswith(("ARFLAGS", "CRATE_CC_", "HOST_", "TARGET_"))
            or any(
                name.startswith(f"{prefix}_")
                for prefix in (
                    "AR",
                    "CC",
                    "CFLAGS",
                    "CPPFLAGS",
                    "CXX",
                    "LDFLAGS",
                    "RANLIB",
                )
            )
        ):
            del environment[name]

    rust_flags = (
        f"--remap-path-prefix={Path.home()}=/Users/build",
        f"--remap-path-prefix={REPO}=/src/syncbox",
        "-C",
        f"link-arg=-Wl,-oso_prefix,{REPO}",
        "-C",
        "link-arg=-Wl,-reproducible",
    )
    environment.update(
        {
            "APPLE_SIGNING_IDENTITY": "-",
            "AR": "/usr/bin/ar",
            "CARGO_BUILD_RUSTC": "rustc",
            "CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER": "",
            "CARGO_BUILD_RUSTC_WRAPPER": "",
            "CARGO_BUILD_RUSTDOC": "rustdoc",
            "CARGO_BUILD_TARGET": "aarch64-apple-darwin",
            "CARGO_ENCODED_RUSTFLAGS": "\x1f".join(rust_flags),
            "CARGO_INCREMENTAL": "0",
            "CARGO_TARGET_AARCH64_APPLE_DARWIN_LINKER": "/usr/bin/clang",
            "CARGO_TARGET_DIR": str(SHELL / "src-tauri" / "target"),
            "CC": "/usr/bin/clang",
            "COPYFILE_DISABLE": "1",
            "CXX": "/usr/bin/clang++",
            "LANG": "C",
            "LC_ALL": "C",
            "MACOSX_DEPLOYMENT_TARGET": "14.0",
            "PATH": f"/usr/bin:/bin:{environment['PATH']}",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "RANLIB": "/usr/bin/ranlib",
            "SDKROOT": _sdkroot(metadata),
            "SOURCE_DATE_EPOCH": str(epoch),
            "TZ": "UTC",
            "UV_CACHE_DIR": "/tmp/syncbox-uv-cache",
            "UV_PYTHON_INSTALL_DIR": str(CANONICAL_PYTHON_INSTALL_DIR),
            "ZERO_AR_DATE": "1",
        }
    )
    return environment


def _sdkroot(metadata: dict) -> str:
    if _is_pinned("toolchain", "macos_sdk_path"):
        return metadata["toolchain"]["macos_sdk_path"]
    return subprocess.run(
        ["xcrun", "--sdk", "macosx", "--show-sdk-path"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _run(command: list[str], cwd: Path, environment: dict[str, str]) -> None:
    subprocess.run(command, cwd=cwd, env=environment, check=True)


def _output(command: list[str], cwd: Path, environment: dict[str, str]) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        details = (result.stderr.strip() or result.stdout.strip() or "no output")
        raise SystemExit(
            f"release toolchain probe failed ({' '.join(command)}):\n{details}"
        )
    return (result.stdout.strip() or result.stderr.strip())


def _verify_toolchain(environment: dict[str, str]) -> None:
    expected = json.loads((REPO / "release-build.json").read_text())
    actual_toolchain = {
        "apple_clang": _output(
            ["/usr/bin/clang", "--version"], REPO, environment
        ).splitlines()[0],
        "apple_ld": _output(["xcrun", "ld", "-v"], REPO, environment).splitlines()[
            0
        ],
        "architecture": platform.machine(),
        "cargo": _output(["cargo", "--version"], REPO, environment),
        "developer_dir": _output(["xcode-select", "-p"], REPO, environment),
        "macos_build": _output(
            ["/usr/bin/sw_vers", "-buildVersion"], REPO, environment
        ),
        "macos_sdk": _output(
            ["xcrun", "--sdk", "macosx", "--show-sdk-version"], REPO, environment
        ),
        "macos_sdk_path": _output(
            ["xcrun", "--sdk", "macosx", "--show-sdk-path"], REPO, environment
        ),
        "node": _output(["node", "--version"], REPO, environment),
        "pnpm": _output(["pnpm", "--version"], REPO, environment),
        "rustc": _output(["rustc", "--version"], REPO, environment),
        "tauri_cli": _output(
            ["pnpm", "exec", "tauri", "--version"], SHELL, environment
        ),
        "uv": _output(["uv", "--version"], REPO, environment),
    }
    python_probe = """\
import importlib.metadata
import json
import platform
import sqlite3
import ssl
import sys
import zlib
from pathlib import Path
print(json.dumps({
    "build": list(platform.python_build()),
    "distribution": Path(sys.base_prefix).name,
    "openssl": ssl.OPENSSL_VERSION,
    "pyinstaller": importlib.metadata.version("pyinstaller"),
    "python": platform.python_version(),
    "sqlite": sqlite3.sqlite_version,
    "zlib": zlib.ZLIB_RUNTIME_VERSION,
}, sort_keys=True))
"""
    actual_python = json.loads(
        _output(
            [
                "uv",
                "run",
                "--locked",
                "--exact",
                "--managed-python",
                "python",
                "-c",
                python_probe,
            ],
            REPO / "sidecar",
            environment,
        )
    )
    actual_optional_python = json.loads(
        _output(
            [
                "uv",
                "run",
                "--locked",
                "--exact",
                "--managed-python",
                "python",
                "-c",
                python_probe.replace(
                    '"zlib": zlib.ZLIB_RUNTIME_VERSION,',
                    '"zlib": zlib.ZLIB_RUNTIME_VERSION,\n'
                    '    "pillow": importlib.metadata.version("pillow"),',
                ),
            ],
            REPO / "optional-component",
            environment,
        )
    )
    mismatches = []
    for section, expected_values, actual_values in (
        ("toolchain", expected["toolchain"], actual_toolchain),
        ("base_python", expected["base_python"], actual_python),
        (
            "optional_python",
            expected["optional_python"],
            actual_optional_python,
        ),
    ):
        for name, expected_value in expected_values.items():
            if not _is_pinned(section, name):
                continue
            actual_value = actual_values.get(name)
            if actual_value != expected_value:
                mismatches.append(
                    f"{section}.{name}: {actual_value!r} != {expected_value!r}"
                )
    if mismatches:
        raise SystemExit("release toolchain mismatch:\n" + "\n".join(mismatches))
    unpinned = [
        name for name in HOST_TOOLCHAIN_KEYS if not _is_pinned("toolchain", name)
    ]
    if unpinned:
        print(
            "host toolchain (unpinned): "
            + json.dumps(
                {name: actual_toolchain[name] for name in unpinned}, sort_keys=True
            )
        )


def main() -> int:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("release build requires macOS arm64")
    environment = _release_environment()
    _clean_local_build_products()
    try:
        _verify_toolchain(environment)
        _clean_local_build_products()
        component_only = sys.argv[1:] == ["--component-only"]
        if sys.argv[1:]:
            if sys.argv[1:] == ["--preflight-only"]:
                print("release toolchain preflight passed")
                return 0
            if not component_only:
                raise SystemExit(
                    "usage: build_macos_release.py "
                    "[--preflight-only|--component-only]"
                )
        _run(
            [
                "uv",
                "run",
                "--locked",
                "--exact",
                "--managed-python",
                "python",
                "../poc/generate_release_licenses.py",
                "--check",
            ],
            REPO / "sidecar",
            environment,
        )
        _run(
            ["pnpm", "freeze:component"],
            SHELL,
            environment,
        )
        version = json.loads((REPO / "ui/package.json").read_text())["version"]
        component_archive = (
            REPO
            / "optional-component"
            / "dist"
            / f"syncbox-deezer-component-{version}-macos-arm64.zip"
        )
        _run(
            [
                "uv",
                "run",
                "--locked",
                "--exact",
                "--managed-python",
                "python",
                "../poc/run_phase6_packaging.py",
                "--component-only",
                "--component-archive",
                str(component_archive),
            ],
            REPO / "sidecar",
            environment,
        )
        if component_only:
            return 0
        _run(
            [
                "pnpm",
                "exec",
                "tauri",
                "build",
                "--bundles",
                "app",
                "--target",
                "aarch64-apple-darwin",
                "--",
                "--locked",
            ],
            SHELL,
            environment,
        )
        _run(
            [
                "uv",
                "run",
                "--locked",
                "--exact",
                "--managed-python",
                "python",
                "../poc/package_base_app.py",
            ],
            REPO / "sidecar",
            environment,
        )
        app = (
            SHELL
            / "src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app"
        )
        base_archive = app.parent / f"Syncbox-{version}-macos-arm64.zip"
        _run(
            [
                "uv",
                "run",
                "--locked",
                "--exact",
                "--managed-python",
                "python",
                "../poc/run_phase6_packaging.py",
                str(app),
                "--archive",
                str(base_archive),
                "--component-archive",
                str(component_archive),
            ],
            REPO / "sidecar",
            environment,
        )
        # Convenience drag-to-Applications installer, built after the scanner
        # passes. Not part of the reproducible/scanned contract; the ZIP is.
        _run(["python3", "../poc/package_base_dmg.py"], SHELL, environment)
        return 0
    finally:
        _clean_local_build_products()


if __name__ == "__main__":
    raise SystemExit(main())
