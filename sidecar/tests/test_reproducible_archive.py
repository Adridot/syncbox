"""Regression tests for deterministic release ZIP generation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from reproducible_archive import write_tree_archive  # noqa: E402


def test_commoncrypto_binding_is_local_locked_and_uses_reproducible_linking():
    lock = tomllib.loads((REPO / "sidecar/uv.lock").read_text())
    package = next(
        item for item in lock["package"] if item["name"] == "sqlcipher3-wheels"
    )
    assert package == {
        "name": "sqlcipher3-wheels",
        "version": "0.6.2+syncbox.commoncrypto.1",
        "source": {"directory": "vendor/sqlcipher3-commoncrypto"},
    }

    setup = (REPO / "sidecar/vendor/sqlcipher3-commoncrypto/setup.py").read_text()
    for required in (
        '"SQLCIPHER_CRYPTO_CC", "1"',
        '"-g0"',
        '"-Wl,-x"',
        '"-Wl,-reproducible"',
        '"Security"',
        '"CoreFoundation"',
    ):
        assert required in setup
    assert "Conan" not in setup
    assert "-lcrypto" not in setup


def test_local_sqlcipher_frozen_metadata_excludes_installation_path():
    spec = (REPO / "sidecar/sidecar.spec").read_text()
    assert 'distribution("sqlcipher3-wheels")' in spec
    assert 'sqlcipher_info / "METADATA"' in spec
    assert '"sqlcipher3-wheels",\n)' not in spec
    assert 'not entry[0].endswith(".dist-info/RECORD")' in spec
    assert 'app.rglob("direct_url.json")' in (
        REPO / "scripts/run_phase6_packaging.py"
    ).read_text()


def test_pyinstaller_base_library_inputs_are_sorted():
    marker = "sorted(modules_toc, key=lambda item: item[0])"
    assert marker in (REPO / "sidecar/sidecar.spec").read_text()
    assert marker in (
        REPO / "optional-component/syncbox-deezer-component.spec"
    ).read_text()


def _load_release_builder():
    path = REPO / "scripts" / "build_macos_release.py"
    spec = importlib.util.spec_from_file_location("build_macos_release", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_builder_removes_only_local_sqlcipher_build_products(
    monkeypatch, tmp_path
):
    builder = _load_release_builder()
    build = tmp_path / "build"
    egg_info = tmp_path / "sqlcipher3_wheels.egg-info"
    sibling = tmp_path / "source"
    for path in (build, egg_info, sibling):
        path.mkdir()
        (path / "marker").write_text("keep only source\n")
    monkeypatch.setattr(builder, "LOCAL_BUILD_PRODUCTS", (build, egg_info))

    builder._clean_local_build_products()

    assert not build.exists()
    assert not egg_info.exists()
    assert sibling.is_dir()


def _load_packaging_scanner():
    path = REPO / "scripts" / "run_phase6_packaging.py"
    spec = importlib.util.spec_from_file_location("run_phase6_packaging", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_artifact_comparator():
    path = REPO / "scripts" / "compare_release_artifacts.py"
    spec = importlib.util.spec_from_file_location("compare_release_artifacts", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture(root: Path, mtime: int) -> Path:
    tree = root / "payload"
    (tree / "empty").mkdir(parents=True)
    executable = tree / "bin"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o775)
    data = tree / "data.txt"
    data.write_text("same bytes\n")
    data.chmod(0o664)
    (tree / "link").symlink_to("data.txt")
    for path in (tree, tree / "empty", executable, data):
        os.utime(path, (mtime, mtime))
    return tree


def test_tree_archives_are_identical_across_roots_and_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1784073600")
    first_tree = _fixture(tmp_path / "first-root", 1_700_000_000)
    second_tree = _fixture(tmp_path / "second-root-with-a-longer-name", 1_750_000_000)
    first_archive = tmp_path / "first.zip"
    second_archive = tmp_path / "second.zip"

    write_tree_archive(first_archive, first_tree, "payload")
    write_tree_archive(second_archive, second_tree, "payload")

    assert first_archive.read_bytes() == second_archive.read_bytes()
    assert hashlib.sha256(first_archive.read_bytes()).hexdigest() == hashlib.sha256(
        second_archive.read_bytes()
    ).hexdigest()
    with zipfile.ZipFile(first_archive) as archive:
        infos = archive.infolist()
        assert [info.filename for info in infos] == [
            "payload/",
            "payload/bin",
            "payload/data.txt",
            "payload/empty/",
            "payload/link",
        ]
        assert {info.date_time for info in infos} == {(2026, 7, 15, 0, 0, 0)}
        modes = {
            info.filename: stat.S_IMODE(info.external_attr >> 16) for info in infos
        }
        assert modes == {
            "payload/": 0o755,
            "payload/bin": 0o755,
            "payload/data.txt": 0o644,
            "payload/empty/": 0o755,
            "payload/link": 0o777,
        }
        assert archive.read("payload/link") == b"data.txt"
    assert _load_packaging_scanner().validate_archive(first_tree, first_archive) == 1


def test_source_date_epoch_is_required(monkeypatch, tmp_path):
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    tree = _fixture(tmp_path / "root", 1_700_000_000)
    try:
        write_tree_archive(tmp_path / "archive.zip", tree, "payload")
    except RuntimeError as error:
        assert str(error) == "SOURCE_DATE_EPOCH is required for release packaging"
    else:
        raise AssertionError("missing SOURCE_DATE_EPOCH was accepted")


def test_release_environment_uses_stable_source_metadata(monkeypatch):
    poisoned = {
        "APPLE_API_KEY": "untrusted-key-id",
        "APPLE_CERTIFICATE": "untrusted-certificate",
        "APPLE_SIGNING_IDENTITY": "Developer ID Application: Untrusted",
        "ARFLAGS": "untrusted",
        "CC": "/tmp/untrusted-cc",
        "CFLAGS_AARCH64_APPLE_DARWIN": "-DUNTRUSTED",
        "CARGO_BUILD_RUSTC": "/tmp/untrusted-rustc",
        "CARGO_BUILD_RUSTFLAGS": "--cfg untrusted",
        "CARGO_ENCODED_RUSTFLAGS": "--cfg\x1funtrusted",
        "CARGO_PROFILE_RELEASE_LTO": "true",
        "CARGO_TARGET_AARCH64_APPLE_DARWIN_LINKER": "/tmp/untrusted-linker",
        "CARGO_TARGET_AARCH64_APPLE_DARWIN_RUSTFLAGS": "--cfg untrusted",
        "CARGO_TARGET_DIR": "/tmp/untrusted-target",
        "CRATE_CC_NO_DEFAULTS": "1",
        "DEVELOPER_DIR": "/tmp/untrusted-xcode",
        "NODE_OPTIONS": "--require=/tmp/untrusted.js",
        "NODE_PATH": "/tmp/untrusted-node-modules",
        "PYTHONHOME": "/tmp/untrusted-python-home",
        "PYTHONPATH": "/tmp/untrusted-python-modules",
        "RUSTC_WORKSPACE_WRAPPER": "/tmp/untrusted-wrapper",
        "RUSTC_WRAPPER": "/tmp/untrusted-wrapper",
        "RUSTFLAGS": "--cfg untrusted",
        "RUSTC_BOOTSTRAP": "1",
        "RUSTUP_TOOLCHAIN": "nightly",
        "SDKROOT": "/tmp/untrusted-sdk",
        "TAURI_CONFIG": "/tmp/untrusted-tauri.conf.json",
        "TAURI_SIGNING_PRIVATE_KEY": "untrusted-key",
        "TARGET_CFLAGS": "-DUNTRUSTED",
        "UV_CONFIG_FILE": "/tmp/untrusted-uv.toml",
        "UV_NO_BINARY": ":all:",
        "UV_NO_DEV": "1",
        "UV_NO_SYNC": "1",
        "UV_PROJECT": "/tmp/untrusted-project",
        "UV_PROJECT_ENVIRONMENT": "/tmp/untrusted-venv",
        "UV_PYTHON": "/tmp/untrusted-python",
    }
    for name, value in poisoned.items():
        monkeypatch.setenv(name, value)
    metadata = json.loads((REPO / "release-build.json").read_text())
    assert metadata["schema"] == 1
    assert metadata["source_date_epoch"] == 1784073600
    assert metadata["release"] == {
        "source_date_epoch_basis": "versioned-release-metadata",
        "source_date_epoch_utc": "2026-07-15T00:00:00Z",
        "version": "0.2.3",
    }
    assert metadata["toolchain"]["rustc"].startswith("rustc 1.96.1 ")
    assert metadata["toolchain"]["node"] == "v24.13.0"
    assert metadata["base_python"]["distribution"] == (
        "cpython-3.14.2-macos-aarch64-none"
    )

    environment = _load_release_builder()._release_environment()
    assert environment["SOURCE_DATE_EPOCH"] == "1784073600"
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
    assert environment["PYTHONHASHSEED"] == "0"
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert environment["TZ"] == "UTC"
    assert environment["LC_ALL"] == "C"
    assert environment["MACOSX_DEPLOYMENT_TARGET"] == "14.0"
    assert environment["APPLE_SIGNING_IDENTITY"] == "-"
    assert environment["AR"] == "/usr/bin/ar"
    assert environment["CC"] == "/usr/bin/clang"
    assert environment["CXX"] == "/usr/bin/clang++"
    assert environment["RANLIB"] == "/usr/bin/ranlib"
    assert environment["SDKROOT"] == metadata["toolchain"]["macos_sdk_path"]
    assert environment["UV_CACHE_DIR"] == "/tmp/syncbox-uv-cache"
    assert environment["UV_PYTHON_INSTALL_DIR"] == (
        "/tmp/syncbox-release-python-20260127"
    )
    assert "APPLE_API_KEY" not in environment
    assert "APPLE_CERTIFICATE" not in environment
    assert "TAURI_CONFIG" not in environment
    assert "TAURI_SIGNING_PRIVATE_KEY" not in environment
    assert "DEVELOPER_DIR" not in environment
    assert "ARFLAGS" not in environment
    assert "CFLAGS_AARCH64_APPLE_DARWIN" not in environment
    assert "CRATE_CC_NO_DEFAULTS" not in environment
    assert "NODE_OPTIONS" not in environment
    assert "NODE_PATH" not in environment
    assert "PYTHONHOME" not in environment
    assert "PYTHONPATH" not in environment
    assert "RUSTC_BOOTSTRAP" not in environment
    assert "RUSTUP_TOOLCHAIN" not in environment
    assert "TARGET_CFLAGS" not in environment
    assert environment["CARGO_BUILD_RUSTC"] == "rustc"
    assert environment["CARGO_BUILD_RUSTC_WRAPPER"] == ""
    assert environment["CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER"] == ""
    assert environment["CARGO_BUILD_TARGET"] == "aarch64-apple-darwin"
    assert environment["CARGO_TARGET_AARCH64_APPLE_DARWIN_LINKER"] == (
        "/usr/bin/clang"
    )
    assert environment["CARGO_TARGET_DIR"] == str(
        REPO / "shell" / "src-tauri" / "target"
    )
    assert "UV_PROJECT_ENVIRONMENT" not in environment
    assert "RUSTFLAGS" not in environment
    assert "CARGO_BUILD_RUSTFLAGS" not in environment
    assert "CARGO_PROFILE_RELEASE_LTO" not in environment
    assert "CARGO_TARGET_AARCH64_APPLE_DARWIN_RUSTFLAGS" not in environment
    assert "UV_NO_SYNC" not in environment
    assert "UV_CONFIG_FILE" not in environment
    assert "UV_NO_BINARY" not in environment
    assert "UV_NO_DEV" not in environment
    assert "UV_PROJECT" not in environment
    assert "UV_PYTHON" not in environment
    home_remap = f"--remap-path-prefix={Path.home()}=/Users/build"
    repo_remap = f"--remap-path-prefix={REPO}=/src/syncbox"
    rust_flags = environment["CARGO_ENCODED_RUSTFLAGS"].split("\x1f")
    assert rust_flags == [
        home_remap,
        repo_remap,
        "-C",
        f"link-arg=-Wl,-oso_prefix,{REPO}",
        "-C",
        "link-arg=-Wl,-reproducible",
    ]


def test_release_build_finalizes_component_before_base_bundle():
    config = json.loads(
        (REPO / "shell/src-tauri/tauri.conf.json").read_text()
    )
    assert config["build"]["beforeBuildCommand"] == (
        "pnpm build && pnpm freeze:base"
    )
    source = (REPO / "scripts/build_macos_release.py").read_text()
    shell_package = json.loads((REPO / "shell/package.json").read_text())
    component = source.index('["pnpm", "freeze:component"]')
    component_scan = source.index('"--component-only"', component)
    tauri = source.index('"tauri",', component_scan)
    package_base = source.index('"../scripts/package_base_app.py"', tauri)
    full_scan = source.index('"../scripts/run_phase6_packaging.py"', package_base)
    assert component < component_scan < tauri < package_base < full_scan
    assert source.count('"--exact"') == 6
    assert "uv run --locked --exact --managed-python" in shell_package["scripts"][
        "freeze:component"
    ]
    assert "uv run --locked --exact --managed-python" in shell_package["scripts"][
        "freeze:base"
    ]


def test_signature_gate_verifies_exact_adhoc_identity(monkeypatch):
    scanner = _load_packaging_scanner()
    calls = []

    def fake_run(*command, check=True):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="",
            stderr="Executable=/tmp/bin\nSignature=adhoc\nTeamIdentifier=not set\n",
        )

    monkeypatch.setattr(scanner, "run", fake_run)
    scanner.validate_adhoc_signature(Path("/tmp/bin"))
    scanner.validate_adhoc_signature(Path("/tmp/App.app"), deep=True)

    assert calls == [
        (
            "codesign",
            "--verify",
            "--strict",
            "--all-architectures",
            "/tmp/bin",
        ),
        (
            "codesign",
            "--display",
            "--verbose=4",
            "--all-architectures",
            "/tmp/bin",
        ),
        (
            "codesign",
            "--verify",
            "--deep",
            "--strict",
            "--all-architectures",
            "/tmp/App.app",
        ),
        (
            "codesign",
            "--display",
            "--verbose=4",
            "--all-architectures",
            "/tmp/App.app",
        ),
    ]


@pytest.mark.parametrize(
    "details",
    [
        "Signature=CMS\nTeamIdentifier=not set\n",
        "Signature=adhoc\nAuthority=Developer ID Application: Example\nTeamIdentifier=not set\n",
        "Signature=adhoc\nTeamIdentifier=ABC123\n",
    ],
)
def test_signature_gate_rejects_non_adhoc_identity(monkeypatch, details):
    scanner = _load_packaging_scanner()

    def fake_run(*command, check=True):
        return subprocess.CompletedProcess(command, 0, stdout="", stderr=details)

    monkeypatch.setattr(scanner, "run", fake_run)
    with pytest.raises(AssertionError):
        scanner.validate_adhoc_signature(Path("/tmp/bin"))


def test_signature_gate_propagates_strict_verification_failure(monkeypatch):
    scanner = _load_packaging_scanner()

    def fake_run(*command, check=True):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(scanner, "run", fake_run)
    with pytest.raises(subprocess.CalledProcessError):
        scanner.validate_adhoc_signature(Path("/tmp/bin"))


def test_architecture_gate_accepts_only_arm64(monkeypatch):
    scanner = _load_packaging_scanner()

    monkeypatch.setattr(
        scanner,
        "run",
        lambda *command, **_kwargs: subprocess.CompletedProcess(
            command, 0, stdout="arm64\n", stderr=""
        ),
    )
    scanner.validate_arm64(Path("/tmp/bin"))

    monkeypatch.setattr(
        scanner,
        "run",
        lambda *command, **_kwargs: subprocess.CompletedProcess(
            command, 0, stdout="arm64 x86_64\n", stderr=""
        ),
    )
    with pytest.raises(AssertionError):
        scanner.validate_arm64(Path("/tmp/bin"))


def test_artifact_comparator_reports_entry_level_mismatch(monkeypatch, tmp_path):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1784073600")
    comparator = _load_artifact_comparator()
    first_tree = _fixture(tmp_path / "first", 1_700_000_000)
    second_tree = _fixture(tmp_path / "second", 1_700_000_000)
    (second_tree / "data.txt").write_text("different bytes\n")
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    write_tree_archive(first, first_tree, "payload")
    write_tree_archive(second, second_tree, "payload")

    differences = comparator._differences(first, second)

    assert [item["entry"] for item in differences] == ["payload/data.txt"]
    assert differences[0]["first"]["payload_sha256"] != differences[0]["second"][
        "payload_sha256"
    ]


def test_source_comparator_ignores_only_generated_and_private_trees(tmp_path):
    comparator = _load_artifact_comparator()
    first = tmp_path / "first-root"
    second = tmp_path / "second-root"
    for root in (first, second):
        (root / "src").mkdir(parents=True)
        (root / "src/app.py").write_text("print('same')\n")
        (root / "sidecar/tests/testdata").mkdir(parents=True)
        (root / "sidecar/tests/testdata/README.md").write_text("fixture instructions\n")
        (root / "sidecar/tests/testdata/private.db").write_bytes(b"different private data")
        (root / "sidecar/dist").mkdir(parents=True)
        (root / "sidecar/dist/generated").write_bytes(b"different build data")
    (second / "sidecar/tests/testdata/private.db").write_bytes(b"other private data")
    (second / "sidecar/dist/generated").write_bytes(b"other build data")

    first_records = comparator._source_records(first)
    second_records = comparator._source_records(second)

    assert first_records == second_records
    assert list(first_records) == ["sidecar/tests/testdata/README.md", "src/app.py"]

    (second / "sidecar/tests/testdata/README.md").write_text("changed instructions\n")
    assert comparator._source_records(first) != comparator._source_records(second)


def test_source_comparator_reports_real_source_drift(tmp_path):
    comparator = _load_artifact_comparator()
    first = tmp_path / "first-root"
    second = tmp_path / "second-root"
    first.mkdir()
    second.mkdir()
    (first / "release-build.json").write_text("{}\n")
    (second / "release-build.json").write_text('{"changed": true}\n')

    assert comparator._source_records(first) != comparator._source_records(second)
