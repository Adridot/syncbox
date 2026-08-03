"""Static contracts for the native macOS window chrome configuration."""

import json
import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
TAURI_CONFIG = REPO / "shell" / "src-tauri" / "tauri.conf.json"
TAURI_CAPABILITY = REPO / "shell" / "src-tauri" / "capabilities" / "default.json"
TOKENS_CSS = REPO / "ui" / "src" / "styles" / "tokens.css"


def _configuration() -> dict:
    return json.loads(TAURI_CONFIG.read_text(encoding="utf-8"))


def _main_window(configuration: dict) -> dict:
    windows = configuration["app"]["windows"]
    matches = [window for window in windows if window.get("label") == "main"]
    assert len(matches) == 1, "Expected exactly one Tauri window labeled 'main'"
    return matches[0]


def _css_color_token(name: str) -> str:
    css = TOKENS_CSS.read_text(encoding="utf-8")
    match = re.search(
        rf"^\s*{re.escape(name)}:\s*(#[0-9a-fA-F]{{6}})\s*;",
        css,
        re.MULTILINE,
    )
    assert match is not None, f"Missing six-digit color token {name}"
    return match.group(1).lower()


def test_main_window_uses_native_dark_overlay_chrome():
    configuration = _configuration()
    window = _main_window(configuration)

    assert window["decorations"] is True
    assert window["titleBarStyle"] == "Overlay"
    assert window["hiddenTitle"] is True
    assert window["theme"] == "Dark"
    assert window["backgroundColor"] == "#0a0c10"
    assert window["trafficLightPosition"] == {"x": 16, "y": 18}
    assert window.get("transparent", False) is False
    assert configuration["app"].get("macOSPrivateApi", False) is False


def test_macos_baseline_and_native_web_background_stay_aligned():
    configuration = _configuration()
    window = _main_window(configuration)

    assert configuration["bundle"]["macOS"]["minimumSystemVersion"] == "14.0"
    assert window["backgroundColor"].lower() == _css_color_token("--bg-base")


def test_main_window_capability_allows_native_dragging():
    capability = json.loads(TAURI_CAPABILITY.read_text(encoding="utf-8"))

    assert capability["windows"] == ["main"]
    assert "core:window:allow-start-dragging" in capability["permissions"]
