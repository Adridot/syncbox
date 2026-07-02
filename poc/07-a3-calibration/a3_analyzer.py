#!/usr/bin/env python
"""POC #7 - A3 fake-320/FLAC analyzer prototype (SPEC-UNIFIED 5.12).

Venv deps only: miniaudio (read-only PCM decode), numpy.fft, mutagen (declared
bitrate readout). Read-only: Path.exists()/stat on the RESOLVED path first
(TCC-safe pattern), decode by exact resolved path, NEVER enumerate the parent
directory, never move/copy the file, no network.

Pipeline: decode -> mono mix -> up to 60 x 1 s Hann-windowed numpy.fft.rfft
frames -> averaged power spectrum -> rolloff/cutoff estimate -> mapping to the
LAME lowpass table -> 3-level verdict ok / incertain / lossy_source_probable.

Undecodable input (AAC/m4a/opus), missing file, or any decode error degrades
to neutral "ok" - never an unhandled exception (5.12).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import miniaudio
import numpy as np

# ---------------------------------------------------------------------------
# Calibrated boundaries (POC #7). LAME lowpass anchors (research note 12):
#   CBR 320 ~ 20.1-20.6 kHz ; V0 ~ no extra lowpass (~20.5 kHz residual)
#   256 ~ 19.4-19.9 kHz ; 192/V2 ~ 18.6-19.2 kHz ; 128 ~ 17 kHz
# Verdict is content-based (estimated source quality from the measured
# cutoff), 3 levels, never binary (5.12). The 320/V0 boundary must land in
# `incertain` or `ok`, never `lossy_source_probable`.
LOSSY_CONTAINER_LOSSY_BELOW_HZ = 19100   # mp3: cutoff below => <=192-class source
LOSSY_CONTAINER_OK_FROM_HZ = 19800       # mp3: cutoff at/above => 320/V0-class source
LOSSLESS_CONTAINER_LOSSY_BELOW_HZ = 19500  # flac/wav: sharp cutoff below => lossy source
LOSSLESS_CONTAINER_OK_FROM_HZ = 20800      # flac/wav: reaches (near) Nyquist => ok

ANALYSIS_MAX_FRAMES = 60      # 30-60 s window per 5.12 (1 s frames)
REF_BAND_HZ = (10000, 15000)  # reference level band, below any plausible cutoff
DROP_DB = 24.0                # cutoff = highest freq still within DROP_DB of ref
SMOOTH_BINS = 201             # ~201 Hz moving average on the dB spectrum

LOSSLESS_EXTS = {".flac", ".wav", ".aiff", ".aif"}
LOSSY_EXTS = {".mp3", ".ogg"}


@dataclass
class A3Result:
    verdict: str              # ok | incertain | lossy_source_probable
    cutoff_hz: float | None   # intermediate value, never persisted (5.12)
    reason: str
    declared_bitrate_kbps: int | None = None
    analysis_s: float | None = None


def _declared_bitrate_kbps(path: Path) -> int | None:
    try:
        from mutagen import File as MutagenFile
        mf = MutagenFile(str(path))
        br = getattr(getattr(mf, "info", None), "bitrate", None)
        return round(br / 1000) if br else None
    except Exception:
        return None


def _averaged_db_spectrum(path: Path) -> tuple[np.ndarray, int] | None:
    """Decode (read-only, resolved path) and average Hann-windowed rfft power."""
    decoded = miniaudio.decode_file(str(path))  # raises DecodeError on aac/m4a/opus
    sr = decoded.sample_rate
    pcm = np.asarray(decoded.samples, dtype=np.float32) / 32768.0
    if decoded.nchannels > 1:
        pcm = pcm.reshape(-1, decoded.nchannels).mean(axis=1)
    frame = sr  # 1 s frames -> ~1 Hz bins
    n_frames = min(len(pcm) // frame, ANALYSIS_MAX_FRAMES)
    if n_frames < 1:
        return None
    window = np.hanning(frame)
    acc = np.zeros(frame // 2 + 1)
    used = 0
    for i in range(n_frames):
        chunk = pcm[i * frame : (i + 1) * frame]
        if np.max(np.abs(chunk)) < 1e-4:  # skip silence
            continue
        acc += np.abs(np.fft.rfft(chunk * window)) ** 2
        used += 1
    if used == 0:
        return None
    db = 10.0 * np.log10(acc / used + 1e-30)
    kernel = np.ones(SMOOTH_BINS) / SMOOTH_BINS
    db_smooth = np.convolve(db, kernel, mode="same")
    return db_smooth, sr


def _estimate_cutoff_hz(db_smooth: np.ndarray, sr: int) -> float:
    """Highest frequency still within DROP_DB of the 10-15 kHz reference level."""
    n_bins = len(db_smooth)
    hz_per_bin = (sr / 2) / (n_bins - 1)
    lo = int(REF_BAND_HZ[0] / hz_per_bin)
    hi = int(REF_BAND_HZ[1] / hz_per_bin)
    ref = float(np.median(db_smooth[lo:hi]))
    above = np.nonzero(db_smooth[lo:] >= ref - DROP_DB)[0]
    if len(above) == 0:
        return float(REF_BAND_HZ[0])
    return float((lo + above[-1]) * hz_per_bin)


def analyze(file_path: str | Path) -> A3Result:
    """A3 diagnostic. Read-only, resolved-path-only, degrades to neutral ok."""
    t0 = time.perf_counter()
    path = Path(file_path)
    try:
        # TCC-safe pattern: existence check on the exact resolved path first;
        # never listdir/enumerate the parent (cloud-placeholder cache bypass).
        if not path.exists() or not path.is_file():
            return A3Result("ok", None, "file_missing_neutral")
        path.stat()

        spec = _averaged_db_spectrum(path)
        if spec is None:
            return A3Result("ok", None, "too_short_or_silent_neutral")
        db_smooth, sr = spec
        cutoff = _estimate_cutoff_hz(db_smooth, sr)
        declared = _declared_bitrate_kbps(path)
        elapsed = time.perf_counter() - t0

        ext = path.suffix.lower()
        if ext in LOSSLESS_EXTS:
            if cutoff >= LOSSLESS_CONTAINER_OK_FROM_HZ:
                v, why = "ok", "lossless_container_full_spectrum"
            elif cutoff >= LOSSLESS_CONTAINER_LOSSY_BELOW_HZ:
                v, why = "incertain", "lossless_container_cutoff_in_320_v0_zone"
            else:
                v, why = "lossy_source_probable", "sharp_cutoff_in_lossless_container"
        elif ext in LOSSY_EXTS:
            if cutoff >= LOSSY_CONTAINER_OK_FROM_HZ:
                v, why = "ok", "cutoff_consistent_with_320_v0_source"
            elif cutoff >= LOSSY_CONTAINER_LOSSY_BELOW_HZ:
                v, why = "incertain", "cutoff_in_256_class_zone"
            else:
                v, why = "lossy_source_probable", "cutoff_indicates_le192_source"
        else:
            # Unknown container that still decoded - stay conservative/neutral.
            v, why = "ok", "unknown_container_neutral"
        return A3Result(v, cutoff, why, declared, elapsed)
    except Exception as exc:  # undecodable (aac/m4a/opus), I/O error, cloud read
        return A3Result("ok", None, f"undecodable_neutral:{type(exc).__name__}",
                        analysis_s=time.perf_counter() - t0)


if __name__ == "__main__":
    import sys
    for arg in sys.argv[1:]:
        r = analyze(arg)
        cut = f"{r.cutoff_hz:7.0f} Hz" if r.cutoff_hz else "      n/a"
        t = f"{r.analysis_s:.3f}s" if r.analysis_s is not None else "-"
        print(f"{Path(arg).name:34s} cutoff={cut}  verdict={r.verdict:22s} "
              f"declared={r.declared_bitrate_kbps or '-':>4} kbps  "
              f"t={t}  ({r.reason})")
