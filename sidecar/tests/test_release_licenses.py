"""Release license inventory and redistribution-material gates."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load_scanner():
    path = REPO / "poc/run_phase6_packaging.py"
    spec = importlib.util.spec_from_file_location("run_phase6_packaging", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inventory(target: str) -> dict:
    path = REPO / f"release/licenses/{target}/dependency-inventory.json"
    return json.loads(path.read_text())


def _bundled_items(entry: dict):
    yield entry
    for field in ("statically_linked_components", "bundled_components"):
        for component in entry.get(field, []):
            yield from _bundled_items(component)


def _source_tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        assert not path.is_symlink()
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


def test_generated_license_material_is_current():
    subprocess.run(
        [sys.executable, REPO / "poc/generate_release_licenses.py", "--check"],
        cwd=REPO,
        check=True,
    )


def test_release_scanner_rejects_python_optimization():
    result = subprocess.run(
        [sys.executable, "-O", REPO / "poc/run_phase6_packaging.py", "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "release scanner must run without Python optimization" in result.stderr


def test_full_release_scan_requires_both_archives():
    scanner = _load_scanner()

    with pytest.raises(ValueError, match="requires both"):
        scanner.validate(Path("unused.app"), None, None, Path("unused.json"))


@pytest.mark.parametrize("filename", ["payload.js", ".env", ".env.production"])
def test_source_secret_scan_covers_distributable_text_files(
    monkeypatch, tmp_path, filename
):
    scanner = _load_scanner()
    monkeypatch.setattr(scanner, "REPO", tmp_path)
    secret = tmp_path / filename
    secret.write_text("-----BEGIN " + "PRIVATE KEY-----\nnot-a-real-key\n")

    with pytest.raises(AssertionError, match="secret-shaped value"):
        scanner.validate_source_secrets()


def test_source_secret_scan_ignores_generated_python_caches(monkeypatch, tmp_path):
    scanner = _load_scanner()
    monkeypatch.setattr(scanner, "REPO", tmp_path)
    (tmp_path / "source.py").write_text("print('safe')\n")
    cache = tmp_path / "tests/__pycache__"
    cache.mkdir(parents=True)
    (cache / "test_source.pyc").write_bytes(
        b"-----BEGIN " + b"PRIVATE KEY-----\nsynthetic test payload\n"
    )

    assert scanner.validate_source_secrets() == 1


def test_frozen_distribution_inventory_uses_the_pyinstaller_pyz(
    monkeypatch,
):
    scanner = _load_scanner()
    monkeypatch.setattr(
        scanner.importlib.metadata,
        "packages_distributions",
        lambda: {"third_party": ["Third_Party"]},
    )

    class Distribution:
        metadata = {"Name": "Third-Party"}
        version = "1.2.3"

    monkeypatch.setattr(
        scanner.importlib.metadata,
        "distributions",
        lambda: [Distribution()],
    )
    listing = "\n".join(
        [
            "Contents of 'bundle' (PKG/CArchive):",
            " PYZ.pyz",
            "Contents of 'PYZ.pyz' (PYZ):",
            " json",
            " syncbox.api",
            " third_party.module",
            " _sysconfigdata__darwin_darwin",
        ]
    )

    assert scanner.frozen_distribution_inventory(listing) == {
        "third-party": "1.2.3"
    }


def test_optional_frozen_license_probe_uses_its_locked_python(monkeypatch, tmp_path):
    scanner = _load_scanner()
    python = tmp_path / "optional-component/.venv/bin/python"
    python.parent.mkdir(parents=True)
    python.touch()
    executable = tmp_path / "component"
    executable.touch()
    payload = {
        "frozen_distributions": {"example": "1.0"},
        "runtime_licenses": {"example": {"license": "MIT", "version": "1.0"}},
    }
    calls = []

    def fake_run(*command, check=True):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(scanner, "REPO", tmp_path)
    monkeypatch.setattr(scanner, "run", fake_run)

    assert scanner.optional_license_probe(executable) == payload
    assert calls == [
        (
            str(python),
            str(REPO / "poc/run_phase6_packaging.py"),
            "--frozen-license-probe",
            str(executable),
        )
    ]


def test_frozen_distributions_must_match_locked_and_inventoried_versions(tmp_path):
    scanner = _load_scanner()
    (tmp_path / "dependency-inventory.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "ecosystem": "python",
                        "name": "example-package",
                        "version": "1.0",
                    }
                ]
            }
        )
    )
    runtime = {"example-package": {"license": "MIT", "version": "1.0"}}

    assert scanner.validate_runtime_license_alignment(
        tmp_path,
        runtime,
        {"example-package": "1.0"},
        {"example_package": "1.0"},
    )["frozen_distribution_count"] == 1

    with pytest.raises(AssertionError, match="frozen runtime version drift"):
        scanner.validate_runtime_license_alignment(
            tmp_path,
            runtime,
            {"example-package": "2.0"},
            {"example_package": "2.0"},
        )

    with pytest.raises(AssertionError, match="packaging-check version drift"):
        scanner.validate_runtime_license_alignment(
            tmp_path,
            runtime,
            {"example-package": "1.0"},
            {"example_package": "2.0"},
        )


def test_license_bundles_are_complete_and_policy_reviewed():
    scanner = _load_scanner()
    expected = {"base": (321, 588), "optional": (47, 87)}
    for target, (entries, files) in expected.items():
        result = scanner.validate_license_bundle(
            REPO / f"release/licenses/{target}", target
        )
        assert result["entries"] == entries
        assert result["files"] == files


@pytest.mark.parametrize(
    "license_name",
    [
        "AGPL-3.0-only",
        "SSPL-1.0",
        "BUSL-1.1",
        "EUPL-1.2",
        "CC-BY-NC-4.0",
        "LicenseRef-Proprietary",
        "UNLICENSED",
    ],
)
def test_license_policy_rejects_unaccepted_or_invalid_expressions(license_name):
    scanner = _load_scanner()
    entries = [
        {
            "ecosystem": "test",
            "license": "MIT",
            "name": "permissive-parent",
            "statically_linked_components": [
                {"license": license_name, "name": "unexpected-child"}
            ],
        }
    ]

    with pytest.raises(AssertionError):
        scanner.validate_license_policy("base", entries)


def test_license_policy_accepts_only_exact_review_and_custom_exceptions():
    scanner = _load_scanner()
    entries = [
        {"ecosystem": "python", "license": "GPL-2.0-or-later", "name": "mutagen"},
        {
            "ecosystem": "native-runtime",
            "license": "LicenseRef-CPython-and-Statically-Linked-Components",
            "name": "python-build-standalone-cpython",
            "statically_linked_components": [
                {"license": "LicenseRef-CPython-Composite", "name": "CPython"},
                {"license": "MIT", "name": "Expat"},
            ],
        },
    ]

    assert scanner.validate_license_policy("base", entries) == {
        ("mutagen", "GPL-2.0-or-later")
    }


def test_inventory_paths_and_hashes_are_relocatable():
    for target in ("base", "optional"):
        root = REPO / f"release/licenses/{target}"
        raw = (root / "dependency-inventory.json").read_bytes()
        assert b"/Users/" not in raw
        assert b"/private/" not in raw
        assert b"/tmp/" not in raw
        for entry in _inventory(target)["entries"]:
            if entry.get("source_path"):
                relative_source = Path(entry["source_path"])
                assert not relative_source.is_absolute()
                assert ".." not in relative_source.parts
                source = REPO / relative_source
                assert source.is_dir() and not source.is_symlink()
                assert entry["source_tree_sha256"] == _source_tree_sha256(source)
            for component in _bundled_items(entry):
                assert "components" not in component
                assert {
                    "license",
                    "license_files",
                    "name",
                    "source",
                    "version",
                } <= component.keys()
                for item in component["license_files"]:
                    relative = Path(item["path"])
                    assert not relative.is_absolute() and ".." not in relative.parts
                    path = root / relative
                    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_project_assets_are_complete_and_source_hashed():
    base = _inventory("base")["project"]["assets"]
    optional = _inventory("optional")["project"]["assets"]
    assert optional == []
    assert {item["source_path"] for item in base} == {
        "shell/src-tauri/icons/icon.icns",
        "shell/src-tauri/icons/128x128@2x.png",
        "ui/src/assets/logo.png",
    }
    for item in base:
        source = REPO / item["source_path"]
        assert item["license"] == "MIT"
        assert item["provenance"] == "owner-confirmed original Syncbox project asset"
        assert item["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()


def test_frozen_runtime_and_build_only_boundaries_are_explicit():
    for target in ("base", "optional"):
        entries = _inventory(target)["entries"]
        hooks = next(
            entry for entry in entries if entry["name"] == "pyinstaller-hooks-contrib"
        )
        assert hooks["distributed"] is False
        assert hooks["scope"] == f"{target}-build-only"

        runtime = next(
            entry
            for entry in entries
            if entry["name"] == "python-build-standalone-cpython"
        )
        components = {
            component["name"] for component in runtime["statically_linked_components"]
        }
        if target == "base":
            assert "Zstandard" in components
        else:
            assert "Zstandard" not in components


def test_specs_embed_only_the_matching_license_tree():
    base_spec = (REPO / "sidecar/sidecar.spec").read_text()
    optional_spec = (
        REPO / "optional-component/syncbox-deezer-component.spec"
    ).read_text()
    assert '("../release/licenses/base", "licenses")' in base_spec
    assert '("../release/licenses/optional", "licenses")' in optional_spec
    assert "release/licenses/optional" not in base_spec
    assert "release/licenses/base" not in optional_spec


def test_base_native_builds_are_exact_and_use_apple_system_crypto():
    entries = _inventory("base")["entries"]
    numpy = next(
        entry
        for entry in entries
        if entry["name"] == "NumPy macOS Accelerate wheel native extensions"
    )
    assert numpy["wheel_sha256"] == (
        "efd736408cc97c79b9e6917338dfc8f06013b2274f992e96b1d9a81a71e2a2c2"
    )
    assert numpy["wheel_size"] == 5335944
    assert numpy["system_dependencies"] == [
        {
            "artifact_reference": "/System/Library/Frameworks/Accelerate.framework",
            "distributed": False,
            "name": "Apple Accelerate",
            "source": "https://developer.apple.com/accelerate/",
            "version": "macOS 14+ system framework",
        }
    ]

    sqlcipher = next(
        entry for entry in entries if entry["name"] == "SQLCipher Community Edition"
    )
    assert not {"wheel_source", "wheel_sha256", "wheel_size"} & sqlcipher.keys()
    assert {
        (item["name"], item["version"])
        for item in sqlcipher["bundled_components"]
    } == {("SQLite", "3.51.1")}
    assert sqlcipher["system_dependencies"] == [
        {
            "artifact_reference": "/usr/lib/libSystem.B.dylib",
            "distributed": False,
            "name": "Apple CommonCrypto",
            "source": (
                "https://developer.apple.com/library/archive/documentation/"
                "System/Conceptual/ManPages_iPhoneOS/man3/CC_crypto.3cc.html"
            ),
            "version": "macOS 14+ system library",
        },
        {
            "artifact_reference": (
                "/System/Library/Frameworks/CoreFoundation.framework/Versions/A/"
                "CoreFoundation"
            ),
            "distributed": False,
            "name": "Apple CoreFoundation",
            "source": "https://developer.apple.com/documentation/corefoundation",
            "version": "macOS 14+ system framework",
        },
        {
            "artifact_reference": (
                "/System/Library/Frameworks/Security.framework/Versions/A/Security"
            ),
            "distributed": False,
            "name": "Apple Security",
            "source": "https://developer.apple.com/documentation/security",
            "version": "macOS 14+ system framework",
        },
    ]

    binding = next(
        entry
        for entry in entries
        if entry["ecosystem"] == "python" and entry["name"] == "sqlcipher3-wheels"
    )
    assert binding["version"] == "0.6.2+syncbox.commoncrypto.1"
    assert binding["license"] == "Zlib"
    assert binding["source_path"] == "sidecar/vendor/sqlcipher3-commoncrypto"
    assert binding["source_tree_sha256"] == _source_tree_sha256(
        REPO / binding["source_path"]
    )
    assert binding["upstream_declared_license"] == "MIT"
    assert binding["upstream_version"] == "0.6.2"
    assert binding["upstream_source_size"] == 2663213
    assert binding["upstream_source_sha256"] == (
        "a2b675289ba8889f389625a21f3a01f1ff159a551b5b88fba8fd92da0e02380a"
    )


def test_optional_pillow_native_inventory_matches_packaged_payload():
    pillow = next(
        entry
        for entry in _inventory("optional")["entries"]
        if entry["name"] == "Pillow macOS arm64 wheel native libraries"
    )
    components = {
        (item["name"], item["version"], item["license"])
        for item in pillow["bundled_components"]
    }
    assert components == {
        ("libXau", "1.0.11", "MIT-open-group"),
        ("libjpeg-turbo", "3.0.3", "IJG"),
        ("XZ liblzma", "5.4.5", "LicenseRef-XZ-Utils-Public-Domain"),
        ("OpenJPEG", "2.5.2", "BSD-2-Clause"),
        ("libtiff", "4.6.0", "libtiff AND LicenseRef-libtiff-LZW"),
        ("libxcb", "1.17.0", "X11"),
        ("zlib", "1.3.1", "Zlib"),
    }
    artifacts = {
        path
        for item in _bundled_items(pillow)
        for path in item.get("artifact_paths", [])
    }
    assert artifacts == {
        "PIL/.dylibs/libXau.6.0.0.dylib",
        "PIL/.dylibs/libjpeg.62.4.0.dylib",
        "PIL/.dylibs/liblzma.5.dylib",
        "PIL/.dylibs/libopenjp2.2.5.2.dylib",
        "PIL/.dylibs/libtiff.6.dylib",
        "PIL/.dylibs/libxcb.1.1.0.dylib",
        "PIL/.dylibs/libz.1.3.1.dylib",
        "PIL/_imaging.cpython-313-darwin.so",
    }
