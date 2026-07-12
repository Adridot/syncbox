"""Tests for the conservative, read-only A3 spectral diagnostic."""

import wave

import numpy as np
import pytest

from syncbox.quality import (
    LOSSLESS_CONTAINER_OK_FROM_HZ,
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
    assert LOSSY_CONTAINER_OK_FROM_HZ == 19800
    assert LOSSLESS_CONTAINER_OK_FROM_HZ == 20800


@pytest.mark.parametrize(
    "container,cutoff,expected",
    [
        ("lossy", 20158, "ok"),  # genuine 320 CBR
        ("lossy", 22050, "ok"),  # V0 - full spectrum
        ("lossy", 19468, "incertain"),  # genuine 256: no penalty
        ("lossy", 18774, "incertain"),  # 192 or a band-limited master
        ("lossy", 16000, "incertain"),  # lower rate or band-limited master
        ("lossless", 22050, "ok"),
        ("lossless", 20800, "ok"),
        ("lossless", 20799, "incertain"),
        ("lossless", 16000, "incertain"),  # fake FLAC or band-limited master
        ("unknown", 15000, "ok"),  # decoded but unknown container: neutral
    ],
)
def test_classify_three_levels(container, cutoff, expected):
    verdict, reason = classify(container, cutoff)
    assert verdict == expected
    assert reason  # always an i18n-able reason key


def test_cutoff_alone_never_triggers_keeper_penalty():
    for container in ("lossy", "lossless", "unknown"):
        for cutoff in range(10_000, 22_051, 250):
            verdict, _ = classify(container, cutoff)
            assert verdict in ("ok", "incertain")


# --- end-to-end on synthetic files ---------------------------------------------


def test_full_spectrum_wav_is_ok(tmp_path):
    result = analyze(write_wav(tmp_path / "full.wav"))
    assert result.verdict == "ok"
    assert result.cutoff_hz > 20800


def test_band_limited_wav_is_uncertain_without_keeper_penalty(tmp_path):
    # A legitimate band-limited master and a lossy transcode can have the same
    # spectrum, so the diagnostic must not claim one from the cutoff alone.
    result = analyze(write_wav(tmp_path / "band-limited.wav", lowpass_hz=16_000))
    assert result.verdict == "incertain"
    assert result.cutoff_hz < 19500
    assert result.reason == "spectral_cutoff_ambiguous"


def test_antiphase_stereo_is_analyzed_per_channel(tmp_path):
    path = tmp_path / "antiphase.wav"
    rng = np.random.default_rng(7)
    left = rng.standard_normal(SR * 2)
    stereo = np.column_stack((left, -left))
    stereo = stereo / np.max(np.abs(stereo)) * 0.7
    with wave.open(str(path), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes((stereo * 32767).astype("<i2").tobytes())

    result = analyze(path)

    assert result.verdict == "ok"
    assert result.cutoff_hz is not None


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


def test_decode_receives_the_exact_path(tmp_path, monkeypatch):
    import syncbox.quality as quality_module

    path = tmp_path / "Folder With Spaces" / "音楽.mp3"
    path.parent.mkdir()
    path.write_bytes(b"not decoded by this test")
    seen = []

    def fail_decode(value):
        seen.append(value)
        raise RuntimeError("stop after exact-path assertion")

    monkeypatch.setattr(quality_module.miniaudio, "decode_file", fail_decode)

    result = analyze(path)

    assert seen == [str(path)]
    assert result.verdict == "ok"
    assert result.reason == "undecodable_neutral:RuntimeError"


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
    for forbidden in (
        "urlopen",
        "requests",
        "httpx",
        "socket",
        "shutil",
        "os.remove",
        ".iterdir(",
        ".glob(",
        ".rglob(",
        ".mkdir(",
        ".rename(",
        ".replace(",
        ".unlink(",
        ".write_bytes(",
        ".write_text(",
        "os.listdir",
        "os.walk",
        "subprocess",
    ):
        assert forbidden not in source
