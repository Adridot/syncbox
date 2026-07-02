#!/usr/bin/env python
"""POC #7 calibration harness - labeled confusion table + gate asserts.

Gate (SPEC-UNIFIED section 8 item 7 + 5.12):
  - frank lossy (<=192-sourced) and fake-FLAC reliably flagged lossy_source_probable
  - true lossless and genuine 320/V0 NEVER flagged lossy_source_probable
    (320/V0 boundary lands in incertain or ok)
  - band-limited legit master case documented (neutral or accepted-risk)
  - undecodable input degrades to neutral ok without unhandled exception
Also spot-checks boundary stability on a second synthetic seed and reports
per-file analysis time (target <0.5 s/file, research note 12).
"""
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from a3_analyzer import analyze  # noqa: E402

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
LAME = "/opt/homebrew/bin/lame"
FFMPEG = "/opt/homebrew/bin/ffmpeg"

# label -> (file, expected verdict set)
LOSSY = {"lossy_source_probable"}
NEUTRAL = {"ok", "incertain"}  # incertain = display nuance, no keeper penalty (5.12)
CASES = [
    ("true lossless FLAC",          "true_lossless.flac",          {"ok"}),
    ("genuine MP3 320 CBR",         "mp3_320.mp3",                 {"ok", "incertain"}),
    ("genuine MP3 V0",              "mp3_v0.mp3",                  {"ok", "incertain"}),
    ("genuine MP3 256 CBR",         "mp3_256.mp3",                 NEUTRAL | LOSSY),  # in-between class, either side ok
    ("genuine MP3 192 CBR",         "mp3_192.mp3",                 LOSSY),
    ("genuine MP3 V2 (~190k)",      "mp3_v2.mp3",                  LOSSY),
    ("genuine MP3 128 CBR",         "mp3_128.mp3",                 LOSSY),
    ("fake-320 (128-sourced)",      "fake320_from128.mp3",         LOSSY),
    ("fake-FLAC (128-sourced)",     "fakeflac_from128.flac",       LOSSY),
    ("fake-FLAC (192-sourced)",     "fakeflac_from192.flac",       LOSSY),
    ("band-limited master 18k brickwall", "bandlimited_brickwall18k.flac", LOSSY | NEUTRAL),  # accepted-risk case, documented
    ("band-limited master 18k gentle",    "bandlimited_gentle18k.flac",    NEUTRAL),
    ("undecodable AAC/m4a",         "tiny.m4a",                    {"ok"}),
    ("missing file",                "does_not_exist.flac",         {"ok"}),
]


def confusion_table() -> bool:
    print(f"{'label':38s} {'file':32s} {'cutoff':>9s} {'verdict':24s} {'t/file':>7s}  gate")
    print("-" * 125)
    all_ok = True
    times = []
    for label, fname, expected in CASES:
        r = analyze(BUILD / fname)
        ok = r.verdict in expected
        all_ok &= ok
        if r.analysis_s is not None and r.cutoff_hz is not None:
            times.append(r.analysis_s)
        cut = f"{r.cutoff_hz:7.0f}Hz" if r.cutoff_hz else "     n/a"
        t = f"{r.analysis_s:.3f}s" if r.analysis_s is not None else "-"
        print(f"{label:38s} {fname:32s} {cut:>9s} {r.verdict:24s} {t:>7s}  {'PASS' if ok else 'FAIL'}")
    if times:
        print(f"\nper-file analysis time: mean {np.mean(times):.3f}s  max {np.max(times):.3f}s "
              f"(target <0.5s, research note 12)")
        assert max(times) < 0.5, "analysis slower than 0.5 s/file target"
    return all_ok


def alt_seed_spot_check() -> None:
    """Second synthetic signal (different seed/chord/roots) to confirm the
    tightest boundaries (genuine 320 -> never lossy ; 192 -> lossy) hold."""
    print("\nalt-seed stability spot check (seed 7, different chords/noise level)")
    alt = BUILD / "alt"
    alt.mkdir(exist_ok=True)
    sr, dur = 44100, 40
    rng = np.random.default_rng(7)
    n = sr * dur
    t = np.arange(n) / sr
    sig = rng.standard_normal(n) * 0.04  # quieter HF bed than primary set
    for f0 in (65.4, 98.0):
        sig += 0.12 * (2.0 * ((t * f0) % 1.0) - 1.0)
    burst = int(0.008 * sr)
    env = np.exp(-np.arange(burst) / (burst / 5))
    for start in range(0, n - burst, sr // 3):
        sig[start:start + burst] += rng.standard_normal(burst) * env * 0.4
    sig *= 0.7 / np.max(np.abs(sig))
    pcm = (np.clip(np.stack([sig, sig * 0.95], axis=1), -1, 1) * 32767).astype("<i2")
    wav = alt / "alt.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(pcm.tobytes())

    def sh(cmd):
        r = subprocess.run(cmd, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-500:]

    sh([LAME, "--silent", "-b", "320", "--cbr", str(wav), str(alt / "alt_320.mp3")])
    sh([LAME, "--silent", "-b", "192", "--cbr", str(wav), str(alt / "alt_192.mp3")])
    sh([LAME, "--silent", "-b", "128", "--cbr", str(wav), str(alt / "alt_128.mp3")])
    sh([LAME, "--silent", "--decode", str(alt / "alt_128.mp3"), str(alt / "alt_dec128.wav")])
    sh([FFMPEG, "-y", "-i", str(alt / "alt_dec128.wav"), "-c:a", "flac", str(alt / "alt_fakeflac128.flac")])
    sh([FFMPEG, "-y", "-i", str(wav), "-c:a", "flac", str(alt / "alt_lossless.flac")])

    checks = [
        ("alt_lossless.flac", {"ok"}),
        ("alt_320.mp3", {"ok", "incertain"}),
        ("alt_192.mp3", LOSSY),
        ("alt_128.mp3", LOSSY),
        ("alt_fakeflac128.flac", LOSSY),
    ]
    for fname, expected in checks:
        r = analyze(alt / fname)
        cut = f"{r.cutoff_hz:7.0f}Hz" if r.cutoff_hz else "n/a"
        print(f"  {fname:26s} cutoff={cut}  verdict={r.verdict:24s} "
              f"{'PASS' if r.verdict in expected else 'FAIL'}")
        assert r.verdict in expected, f"alt-seed regression on {fname}: {r.verdict}"


def main() -> None:
    ok = confusion_table()
    # Hard gate asserts (redundant with table, explicit for the verdict):
    assert analyze(BUILD / "true_lossless.flac").verdict == "ok"
    assert analyze(BUILD / "mp3_320.mp3").verdict != "lossy_source_probable"
    assert analyze(BUILD / "mp3_v0.mp3").verdict != "lossy_source_probable"
    for f in ("mp3_192.mp3", "mp3_v2.mp3", "mp3_128.mp3", "fake320_from128.mp3",
              "fakeflac_from128.flac", "fakeflac_from192.flac"):
        assert analyze(BUILD / f).verdict == "lossy_source_probable", f
    assert analyze(BUILD / "tiny.m4a").verdict == "ok"          # graceful degrade
    assert analyze(BUILD / "does_not_exist.flac").verdict == "ok"
    assert ok, "confusion table has FAIL rows"
    alt_seed_spot_check()
    print("\nALL GATE ASSERTS PASSED")


if __name__ == "__main__":
    main()
