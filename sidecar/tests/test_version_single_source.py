"""Version single-source guard (SPEC-UNIFIED 6.11, closes skew T13).

ui/package.json is the canonical version. The other historical skew spots
either derive from it natively (tauri.conf.json points at the file, the two
Vue components render the vite-injected __APP_VERSION__) or are pinned equal
by this test (pyproject.toml, Cargo.toml). Bumping the version = edit
ui/package.json, then let this test list what else to touch.
"""

import json
import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP_IDENTIFIER = "io.github.adridot.syncbox"

CANONICAL = json.loads((REPO / "ui" / "package.json").read_text())["version"]


def locked_package_version(path: Path, package_name: str) -> str:
    lock = tomllib.loads(path.read_text())
    matches = [
        package["version"]
        for package in lock["package"]
        if package["name"] == package_name
    ]
    assert len(matches) == 1, (path, package_name, matches)
    return matches[0]


def test_canonical_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", CANONICAL), CANONICAL


def test_pyproject_pinned_to_canonical():
    pyproject = tomllib.loads((REPO / "sidecar" / "pyproject.toml").read_text())
    assert pyproject["project"]["version"] == CANONICAL


def test_cargo_pinned_to_canonical():
    cargo = tomllib.loads((REPO / "shell" / "src-tauri" / "Cargo.toml").read_text())
    assert cargo["package"]["version"] == CANONICAL


def test_shell_package_json_pinned_to_canonical():
    # 7th spot, found during M5 (not in the kit's list of 6): inert private
    # package, but a skew is a skew.
    shell_pkg = json.loads((REPO / "shell" / "package.json").read_text())
    assert shell_pkg["version"] == CANONICAL


def test_optional_component_and_manifest_are_pinned_to_canonical():
    component = tomllib.loads(
        (REPO / "optional-component" / "pyproject.toml").read_text()
    )
    manifest = json.loads(
        (REPO / "sidecar" / "src" / "syncbox" / "optional_component.json").read_text()
    )
    assert component["project"]["version"] == CANONICAL
    assert manifest["component_version"] == CANONICAL
    assert manifest["archive"] == (
        f"syncbox-deezer-component-{CANONICAL}-macos-arm64.zip"
    )
    assert f"/releases/download/v{CANONICAL}/{manifest['archive']}" in manifest[
        "download_url"
    ]


def test_release_metadata_and_lockfiles_are_pinned_to_canonical():
    release_build = json.loads((REPO / "release-build.json").read_text())
    assert release_build["release"]["version"] == CANONICAL
    assert locked_package_version(REPO / "sidecar" / "uv.lock", "syncbox") == CANONICAL
    assert (
        locked_package_version(
            REPO / "optional-component" / "uv.lock",
            "syncbox-deezer-component",
        )
        == CANONICAL
    )
    assert (
        locked_package_version(
            REPO / "shell" / "src-tauri" / "Cargo.lock",
            "syncbox-shell",
        )
        == CANONICAL
    )


def test_release_license_inventories_are_pinned_to_canonical():
    for lane in ("base", "optional"):
        inventory = json.loads(
            (REPO / "release" / "licenses" / lane / "dependency-inventory.json").read_text()
        )
        assert inventory["artifact_version"] == CANONICAL


def test_tauri_conf_derives_from_package_json():
    conf = json.loads((REPO / "shell" / "src-tauri" / "tauri.conf.json").read_text())
    # Native derivation (tauri-utils: version may be a path to a package.json).
    assert conf["version"] == "../../ui/package.json"
    assert conf["identifier"] == APP_IDENTIFIER


def test_readme_download_matches_canonical():
    # The landing-page README (379f8ff) no longer states the source version
    # outright; it publishes it through the Install step's download name and
    # release tag, which is what a reader actually acts on. Retarget authored
    # in a parallel session, folded in here so the bump lands green in one go.
    readme = (REPO / "README.md").read_text()
    assert f"Syncbox-{CANONICAL}-macos-arm64.dmg" in readme
    assert f"/releases/tag/v{CANONICAL}" in readme


def test_vite_injects_the_version():
    vite_conf = (REPO / "ui" / "vite.config.ts").read_text()
    assert "__APP_VERSION__" in vite_conf and "pkg.version" in vite_conf


def test_no_hardcoded_version_in_the_ui_spots():
    for spot in ("components/AppSidebar.vue", "screens/SettingsScreen.vue"):
        text = (REPO / "ui" / "src" / spot).read_text()
        assert "__APP_VERSION__" in text, f"{spot} no longer renders the injected version"
        hardcoded = re.findall(r"\bv\d+\.\d+", text)
        assert not hardcoded, f"{spot} hardcodes {hardcoded}"
