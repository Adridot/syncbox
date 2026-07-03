"""Tests for the A3 quality verdict (SPEC-UNIFIED 5.12, POC #7 boundaries)."""

import wave

import numpy as np
import pytest

from syncbox.quality import (
    LOSSLESS_CONTAINER_LOSSY_BELOW_HZ,
    LOSSLESS_CONTAINER_OK_FROM_HZ,
    LOSSY_CONTAINER_LOSSY_BELOW_HZ,
    LOSSY_CONTAINER_OK_FROM_HZ,
    analyze,
    classify,
)

SR = 44_100


def write_wav(path, seconds=2.0, lowpass_hz=None):
    """Synthetic white noise WAV; optional brick-wall lowpass via rfft zeroing."""
    rng = np.random.default_rng(42)
    samples = rng.standard_normal(int(SR * seconds)).astype(np.float64)
    if lowpass_hz is not None:
        spectrum = np.fft.rfft(samples)
        freqs = np.fft.rfftfreq(len(samples), d=1 / SR)
        spectrum[freqs > lowpass_hz] = 0
        samples = np.fft.irfft(spectrum, n=len(samples))
    pcm = np.clip(samples / np.max(np.abs(samples)) * 0.7, -1, 1)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes((pcm * 32767).astype("<i2").tobytes())
    return path


# --- boundary mapping (calibrated constants are the contract) ------------------


def test_calibrated_boundaries_pinned():
    assert LOSSY_CONTAINER_LOSSY_BELOW_HZ == 19100
    assert LOSSY_CONTAINER_OK_FROM_HZ == 19800
    assert LOSSLESS_CONTAINER_LOSSY_BELOW_HZ == 19500
    assert LOSSLESS_CONTAINER_OK_FROM_HZ == 20800


@pytest.mark.parametrize(
    "container,cutoff,expected",
    [
        ("lossy", 20158, "ok"),        # genuine 320 CBR (measured POC #7)
        ("lossy", 22050, "ok"),        # V0 - full spectrum
        ("lossy", 19468, "incertain"), # genuine 256: conservative, no penalty
        ("lossy", 19100, "incertain"), # exact lower boundary is incertain
        ("lossy", 19099, "lossy_source_probable"),
        ("lossy", 18774, "lossy_source_probable"),  # 192-class
        ("lossless", 22050, "ok"),
        ("lossless", 20800, "ok"),
        ("lossless", 20799, "incertain"),
        ("lossless", 19500, "incertain"),
        ("lossless", 19499, "lossy_source_probable"),  # fake FLAC
        ("unknown", 15000, "ok"),  # decoded but unknown container: neutral
    ],
)
def test_classify_three_levels(container, cutoff, expected):
    verdict, reason = classify(container, cutoff)
    assert verdict == expected
    assert reason  # always an i18n-able reason key


def test_320_v0_zone_never_flagged_lossy():
    # The physical 320/V0 boundary zone must never yield lossy (5.12).
    for cutoff in range(19100, 22051, 50):
        verdict, _ = classify("lossy", cutoff)
        assert verdict in ("ok", "incertain")


# --- end-to-end on synthetic files ---------------------------------------------


def test_full_spectrum_wav_is_ok(tmp_path):
    result = analyze(write_wav(tmp_path / "full.wav"))
    assert result.verdict == "ok"
    assert result.cutoff_hz > 20800


def test_band_limited_wav_is_flagged(tmp_path):
    # 16 kHz brick-wall inside a lossless container = fake-lossless signature
    result = analyze(write_wav(tmp_path / "fake.wav", lowpass_hz=16_000))
    assert result.verdict == "lossy_source_probable"
    assert result.cutoff_hz < 19500


# --- neutral degradation (never an exception) ----------------------------------


def test_missing_file_is_neutral(tmp_path):
    result = analyze(tmp_path / "nope.flac")
    assert result.verdict == "ok"
    assert result.reason == "file_missing_neutral"


def test_undecodable_bytes_are_neutral(tmp_path):
    garbage = tmp_path / "fake.m4a"
    garbage.write_bytes(b"\x00\x01\x02 definitely not audio " * 100)
    result = analyze(garbage)
    assert result.verdict == "ok"
    assert result.reason.startswith("undecodable_neutral")


def test_silent_file_is_neutral(tmp_path):
    silent = tmp_path / "silent.wav"
    with wave.open(str(silent), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(b"\x00\x00" * SR * 2)
    result = analyze(silent)
    assert result.verdict == "ok"
    assert result.reason == "too_short_or_silent_neutral"


def test_quality_module_is_read_only_and_offline():
    import syncbox.quality as quality_module
    from pathlib import Path

    source = Path(quality_module.__file__).read_text()
    for forbidden in ("urlopen", "requests", "httpx", "socket", "shutil", "os.remove"):
        assert forbidden not in source
