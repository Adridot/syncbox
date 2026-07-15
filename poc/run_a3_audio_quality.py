#!/usr/bin/env python3
"""Run the deterministic synthetic corpus for the A3 spectral diagnostic."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SIDECAR_SRC = REPO / "sidecar" / "src"
SAMPLE_RATE = 44_100
SECONDS = 30


@dataclass(frozen=True)
class CorpusCase:
    name: str
    expected_verdict: str
    penalty_expected: bool
    path: Path


@dataclass(frozen=True)
class AnalyzerResult:
    verdict: str
    cutoff_hz: float | None
    reason: str


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True)


def _write_wav(np, path: Path, *, seconds: float, lowpass_hz=None, silent=False):
    frames = int(SAMPLE_RATE * seconds)
    if silent:
        samples = np.zeros((frames, 2), dtype=np.float64)
    else:
        samples = np.random.default_rng(42).standard_normal((frames, 2))
        if lowpass_hz is not None:
            spectrum = np.fft.rfft(samples, axis=0)
            frequencies = np.fft.rfftfreq(frames, d=1 / SAMPLE_RATE)
            spectrum[frequencies > lowpass_hz] = 0
            samples = np.fft.irfft(spectrum, n=frames, axis=0)
        samples = samples / np.max(np.abs(samples)) * 0.7

    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes((samples * 32767).astype("<i2").tobytes())
    return path


def _version_line(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return (result.stdout or result.stderr).splitlines()[0]


def _external_analyzer(executable: Path, side_effect_root: Path):
    if not executable.is_file():
        raise RuntimeError(f"analyzer does not exist: {executable}")

    def analyze(path: Path) -> AnalyzerResult:
        env = os.environ.copy()
        env["SYNCBOX_DATA_DIR"] = str(side_effect_root)
        completed = subprocess.run(
            [str(executable), "--quality-analyze", str(path)],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        payload = json.loads(completed.stdout)
        return AnalyzerResult(
            verdict=payload["verdict"],
            cutoff_hz=payload["cutoff_hz"],
            reason=payload["reason"],
        )

    return analyze


def _preflight():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("this POC is limited to macOS Apple Silicon")
    tools = {name: shutil.which(name) for name in ("ffmpeg", "lame")}
    missing = [name for name, path in tools.items() if path is None]
    if missing:
        raise RuntimeError(f"required local executable(s) missing: {', '.join(missing)}")

    sys.path.insert(0, str(SIDECAR_SRC))
    import _cffi_backend
    import miniaudio
    import numpy as np
    from syncbox.quality import analyze

    return tools, _cffi_backend, miniaudio, np, analyze


def _build_corpus(base: Path, tools, np) -> list[CorpusCase]:
    source = _write_wav(np, base / "source.wav", seconds=SECONDS)
    band_limited = _write_wav(
        np, base / "band-limited-source.wav", seconds=SECONDS, lowpass_hz=16_000
    )
    silent = _write_wav(np, base / "silence.wav", seconds=2, silent=True)
    very_short = _write_wav(np, base / "very-short.wav", seconds=0.25)

    encoded = {}
    for name, arguments in (
        ("genuine-320-cbr", ["-b", "320"]),
        ("genuine-v0", ["-V", "0"]),
        ("genuine-256-cbr", ["-b", "256"]),
        ("genuine-192-cbr", ["-b", "192"]),
        ("genuine-128-cbr", ["-b", "128"]),
    ):
        path = base / f"{name}.mp3"
        _run([tools["lame"], "--silent", *arguments, str(source), str(path)])
        encoded[name] = path

    band_limited_320 = base / "band-limited-320-cbr.mp3"
    _run(
        [
            tools["lame"],
            "--silent",
            "-b",
            "320",
            str(band_limited),
            str(band_limited_320),
        ]
    )

    genuine_lossless = base / "genuine-lossless.flac"
    _run(
        [
            tools["ffmpeg"],
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-c:a",
            "flac",
            str(genuine_lossless),
        ]
    )
    lossy_to_flac = base / "lossy-to-flac.flac"
    _run(
        [
            tools["ffmpeg"],
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(encoded["genuine-192-cbr"]),
            "-c:a",
            "flac",
            str(lossy_to_flac),
        ]
    )
    band_limited_lossless = base / "band-limited-lossless.flac"
    _run(
        [
            tools["ffmpeg"],
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(band_limited),
            "-c:a",
            "flac",
            str(band_limited_lossless),
        ]
    )
    undecodable = base / "undecodable.mp3"
    undecodable.write_bytes(b"not an audio file")

    return [
        CorpusCase("genuine 320 CBR", "ok", False, encoded["genuine-320-cbr"]),
        CorpusCase("genuine V0", "ok", False, encoded["genuine-v0"]),
        CorpusCase("genuine 256 CBR", "incertain", False, encoded["genuine-256-cbr"]),
        CorpusCase(
            "genuine 192 CBR",
            "lossy_source_probable",
            True,
            encoded["genuine-192-cbr"],
        ),
        CorpusCase(
            "genuine 128 CBR",
            "lossy_source_probable",
            True,
            encoded["genuine-128-cbr"],
        ),
        CorpusCase("genuine lossless", "ok", False, genuine_lossless),
        CorpusCase("lossy to FLAC", "lossy_source_probable", True, lossy_to_flac),
        CorpusCase(
            "band-limited lossless master",
            "incertain",
            False,
            band_limited_lossless,
        ),
        CorpusCase("band-limited 320 master", "incertain", False, band_limited_320),
        CorpusCase("silence", "ok", False, silent),
        CorpusCase("very short", "ok", False, very_short),
        CorpusCase("undecodable", "ok", False, undecodable),
    ]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--analyzer",
        type=Path,
        help="frozen sidecar executable to validate instead of source mode",
    )
    args = parser.parse_args(argv)

    try:
        tools, cffi_backend, miniaudio, np, source_analyze = _preflight()
    except (ImportError, OSError, RuntimeError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2

    print("A3 deterministic synthetic corpus")
    print(f"Platform: {platform.platform()}")
    print(f"Python: {platform.python_version()}")
    print(
        f"miniaudio: {importlib.metadata.version('miniaudio')} "
        f"/ C {miniaudio.lib_version()}"
    )
    print(f"cffi: {importlib.metadata.version('cffi')} ({cffi_backend.__file__})")
    print(f"numpy: {np.__version__}")
    print(f"ffmpeg: {_version_line([tools['ffmpeg'], '-version'])}")
    print(f"lame: {_version_line([tools['lame'], '--version'])}")

    try:
        with tempfile.TemporaryDirectory(prefix="syncbox-a3-") as temp:
            temp_root = Path(temp)
            side_effect_root = temp_root / "unexpected-app-data"
            analyze = (
                _external_analyzer(args.analyzer.resolve(), side_effect_root)
                if args.analyzer
                else source_analyze
            )
            print(f"Analyzer: {args.analyzer.resolve() if args.analyzer else 'source'}")
            cases = _build_corpus(temp_root, tools, np)
            results = [(case, analyze(case.path)) for case in cases]
            if side_effect_root.exists():
                raise RuntimeError("quality analyzer created application data")
    except (
        json.JSONDecodeError,
        KeyError,
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"BLOCKED: corpus generation failed: {error}", file=sys.stderr)
        return 2

    print(
        "\nCase                              Expected                 "
        "Actual                   Cutoff"
    )
    print("-" * 96)
    for case, result in results:
        cutoff = "neutral" if result.cutoff_hz is None else f"{result.cutoff_hz:.0f} Hz"
        print(
            f"{case.name:<33} {case.expected_verdict:<24} "
            f"{result.verdict:<24} {cutoff}"
        )

    true_positive = sum(
        case.penalty_expected and result.verdict == "lossy_source_probable"
        for case, result in results
    )
    false_positive = sum(
        not case.penalty_expected and result.verdict == "lossy_source_probable"
        for case, result in results
    )
    true_negative = sum(
        not case.penalty_expected and result.verdict != "lossy_source_probable"
        for case, result in results
    )
    false_negative = sum(
        case.penalty_expected and result.verdict != "lossy_source_probable"
        for case, result in results
    )
    exact = sum(case.expected_verdict == result.verdict for case, result in results)

    print(f"\nExact verdicts: {exact}/{len(results)}")
    print(
        "Keeper-penalty confusion: "
        f"TP={true_positive} FP={false_positive} TN={true_negative} FN={false_negative}"
    )
    if false_positive:
        print("VERDICT: NO-GO - the detector produces unsafe false-positive penalties.")
    elif false_negative:
        print(
            "VERDICT: NO-GO for full A3 detection; conservative fallback active "
            "with zero false-positive penalties and explicit false negatives."
        )
    else:
        print(
            "VERDICT: GO for this synthetic corpus only; "
            "a labeled real corpus remains required."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
