"""A3 fake-320/FLAC diagnostic - read-only spectral verdict
(SPEC-UNIFIED 5.12, calibrated by POC #7).

Rules that are load-bearing:
- read-only everywhere: decode by the exact resolved path (Path.exists/stat
  first, never enumerate the parent - TCC pattern), file never moved/copied,
  zero network, NEVER called inside _mutate;
- 3-level verdict ok / incertain / lossy_source_probable, never binary; the
  320/V0 boundary lands in incertain or ok, never lossy;
- any failure (missing file, undecodable AAC/m4a/opus, cloud read error,
  too short/silent) degrades to NEUTRAL 'ok' - no unhandled exception;
- the cutoff frequency is an intermediate value, never persisted; only the
  verdict feeds the D6 keeper (binary effect: lossy_source_probable is
  penalized, incertain/ok are both neutral).
"""

from dataclasses import dataclass
from pathlib import Path

import miniaudio
import numpy as np

# Calibrated boundaries (POC #7, synthetic labeled set; LAME lowpass anchors
# from research note 12). Margins to every genuine class measured >= 330 Hz.
LOSSY_CONTAINER_LOSSY_BELOW_HZ = 19100
LOSSY_CONTAINER_OK_FROM_HZ = 19800
LOSSLESS_CONTAINER_LOSSY_BELOW_HZ = 19500
LOSSLESS_CONTAINER_OK_FROM_HZ = 20800

ANALYSIS_MAX_FRAMES = 60  # 30-60 s window per 5.12 (1 s frames, ~1 Hz bins)
REF_BAND_HZ = (10000, 15000)
DROP_DB = 24.0
SMOOTH_BINS = 201

LOSSLESS_EXTS = {".flac", ".wav", ".aiff", ".aif"}
LOSSY_EXTS = {".mp3", ".ogg"}


@dataclass(frozen=True)
class QualityResult:
    verdict: str  # ok | incertain | lossy_source_probable
    cutoff_hz: float | None  # intermediate, never persisted
    reason: str  # i18n-ready reason key (en.ts/fr.ts label it)


def classify(container: str, cutoff_hz: float) -> tuple[str, str]:
    """Map (container class, measured cutoff) to (verdict, reason key)."""
    if container == "lossless":
        if cutoff_hz >= LOSSLESS_CONTAINER_OK_FROM_HZ:
            return "ok", "lossless_container_full_spectrum"
        if cutoff_hz >= LOSSLESS_CONTAINER_LOSSY_BELOW_HZ:
            return "incertain", "lossless_container_cutoff_in_320_v0_zone"
        return "lossy_source_probable", "sharp_cutoff_in_lossless_container"
    if container == "lossy":
        if cutoff_hz >= LOSSY_CONTAINER_OK_FROM_HZ:
            return "ok", "cutoff_consistent_with_320_v0_source"
        if cutoff_hz >= LOSSY_CONTAINER_LOSSY_BELOW_HZ:
            return "incertain", "cutoff_in_256_class_zone"
        return "lossy_source_probable", "cutoff_indicates_le192_source"
    # Unknown container that still decoded: conservative neutral.
    return "ok", "unknown_container_neutral"


def _averaged_db_spectrum(path: Path):
    decoded = miniaudio.decode_file(str(path))  # DecodeError on aac/m4a/opus
    sr = decoded.sample_rate
    pcm = np.asarray(decoded.samples, dtype=np.float32) / 32768.0
    if decoded.nchannels > 1:
        pcm = pcm.reshape(-1, decoded.nchannels).mean(axis=1)
    frame = sr
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
    return np.convolve(db, kernel, mode="same"), sr


def _estimate_cutoff_hz(db_smooth: np.ndarray, sr: int) -> float:
    """Highest frequency still within DROP_DB of the 10-15 kHz reference."""
    n_bins = len(db_smooth)
    hz_per_bin = (sr / 2) / (n_bins - 1)
    lo = int(REF_BAND_HZ[0] / hz_per_bin)
    hi = int(REF_BAND_HZ[1] / hz_per_bin)
    ref = float(np.median(db_smooth[lo:hi]))
    above = np.nonzero(db_smooth[lo:] >= ref - DROP_DB)[0]
    if len(above) == 0:
        return float(REF_BAND_HZ[0])
    return float((lo + above[-1]) * hz_per_bin)


def analyze(file_path) -> QualityResult:
    """Compute the A3 verdict for one resolved file path. Never raises."""
    path = Path(file_path)
    try:
        if not path.exists() or not path.is_file():
            return QualityResult("ok", None, "file_missing_neutral")
        spec = _averaged_db_spectrum(path)
        if spec is None:
            return QualityResult("ok", None, "too_short_or_silent_neutral")
        db_smooth, sr = spec
        cutoff = _estimate_cutoff_hz(db_smooth, sr)
        ext = path.suffix.lower()
        container = (
            "lossless"
            if ext in LOSSLESS_EXTS
            else "lossy" if ext in LOSSY_EXTS else "unknown"
        )
        verdict, reason = classify(container, cutoff)
        return QualityResult(verdict, cutoff, reason)
    except Exception as exc:
        # Undecodable formats (AAC/m4a/opus - users lawfully own such files),
        # I/O and cloud errors: neutral, never an exception (5.12).
        return QualityResult("ok", None, f"undecodable_neutral:{type(exc).__name__}")
