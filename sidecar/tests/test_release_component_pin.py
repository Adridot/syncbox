"""The committed component pin cannot ship stale again.

Regression for v0.2.4-v0.4.0: the manifest carried the sha256/size of a
2026-07-13 local build, no published archive ever matched it, and installing
the component from a GitHub release failed its integrity check (fixed for
v0.4.0 by PR #33). The release workflow now rebuilds the component and blocks
publishing unless the tagged manifest matches the regenerated one; these
tests keep that guard and its preconditions in place.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "sidecar" / "src" / "syncbox" / "optional_component.json"


def test_manifest_is_in_canonical_form():
    # scripts/package_optional_component.py serialization; a hand-edited pin
    # in any other form would fail the release diff on formatting alone.
    text = MANIFEST.read_text()
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"


def test_manifest_pin_fields_are_plausible():
    manifest = json.loads(MANIFEST.read_text())
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["sha256"])
    assert isinstance(manifest["size"], int) and manifest["size"] > 0


def test_release_workflow_diffs_the_committed_pin():
    workflow = (REPO / ".github" / "workflows" / "release.yml").read_text()
    assert '"$GITHUB_WORKSPACE/sidecar/src/syncbox/optional_component.json"' in workflow
    assert '"$SRC/sidecar/src/syncbox/optional_component.json"' in workflow
    assert "Run the Release Pin workflow on the release branch" in workflow
    assert "Do not move or replace a release tag" in workflow


def test_release_pin_workflow_exports_and_checks_the_hosted_manifest():
    workflow = (REPO / ".github" / "workflows" / "release-pin.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "pull_request:" in workflow
    assert "runs-on: macos-15" in workflow
    assert "SYNCBOX_RELEASE_HOST_TOOLCHAIN: unpinned" in workflow
    assert "pnpm bundle:macos --component-only" in workflow
    assert "name: optional-component-manifest" in workflow
    assert "path: sidecar/src/syncbox/optional_component.json" in workflow
    assert 'git diff --quiet -- "$MANIFEST"' in workflow
    assert 'if [ "$GITHUB_EVENT_NAME" = "pull_request" ]' in workflow
