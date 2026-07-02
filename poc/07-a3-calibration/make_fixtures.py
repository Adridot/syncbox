#!/usr/bin/env python
"""POC #7 fixture generator - SYNTHETIC audio only, no copyrighted material.

Synthesizes ~60 s of music-like audio (broadband noise + harmonic stack +
transients, energy up to Nyquist) with numpy, writes a 44.1 kHz stereo WAV,
then shells out to the DEV MACHINE tools /opt/homebrew/bin/lame and
/opt/homebrew/bin/ffmpeg (fixture tooling only, NEVER app dependencies) to
produce the labeled set under build/.

Labeled set:
  true_lossless.flac          FLAC from the original WAV
  mp3_320.mp3 / mp3_v0.mp3 / mp3_256.mp3 / mp3_192.mp3 / mp3_v2.mp3 / mp3_128.mp3
  fake320_from128.mp3         128 kbps MP3 decoded and re-encoded as 320 CBR
  fakeflac_from128.flac       128 kbps MP3 decoded and encoded as FLAC
  fakeflac_from192.flac       192 kbps MP3 decoded and encoded as FLAC
  bandlimited_brickwall18k.flac  original WAV brickwall-lowpassed at 18 kHz (numpy FFT)
  bandlimited_gentle18k.flac     original WAV 2nd-order butterworth lowpass 18 kHz (ffmpeg)
  tiny.m4a                    3 s AAC, undecodable by miniaudio (graceful-degradation probe)
"""
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

LAME = "/opt/homebrew/bin/lame"
FFMPEG = "/opt/homebrew/bin/ffmpeg"
BUILD = Path(__file__).resolve().parent / "build"
SR = 44100
DUR_S = 60


def synth() -> np.ndarray:
    """Music-like synthetic signal: noise + harmonic stack + transients."""
    rng = np.random.default_rng(42)
    n = SR * DUR_S
    t = np.arange(n) / SR

    # Broadband noise bed (flat to Nyquist) - guarantees measurable HF energy.
    noise_l = rng.standard_normal(n) * 0.06
    noise_r = rng.standard_normal(n) * 0.06

    # Harmonic stack: non-bandlimited sawtooths (full-band harmonics),
    # changing "chord" every 4 s to be music-like.
    harm = np.zeros(n)
    roots = [55.0, 73.42, 82.41, 61.74]  # A1, D2, E2, B1
    seg = 4 * SR
    for i in range(0, n, seg):
        f0 = roots[(i // seg) % len(roots)]
        tt = t[i : i + seg]
        for mult in (1.0, 2.0, 3.0, 4.98):  # slight detune on top voice
            f = f0 * mult
            harm[i : i + seg] += (1.0 / mult) * (2.0 * ((tt * f) % 1.0) - 1.0)
    harm *= 0.18 / np.max(np.abs(harm))

    # Transients: 10 ms decaying white-noise bursts every 0.5 s (hi-hat-like).
    trans = np.zeros(n)
    burst_len = int(0.010 * SR)
    env = np.exp(-np.arange(burst_len) / (burst_len / 5))
    for start in range(0, n - burst_len, SR // 2):
        trans[start : start + burst_len] += rng.standard_normal(burst_len) * env * 0.5

    # Slow amplitude modulation (musical dynamics).
    lfo = 0.75 + 0.25 * np.sin(2 * np.pi * 0.1 * t)

    left = (noise_l + harm + trans) * lfo
    right = (noise_r + harm * 0.9 + trans) * lfo
    stereo = np.stack([left, right], axis=1)
    stereo *= 0.7 / np.max(np.abs(stereo))
    return stereo


def write_wav(path: Path, stereo: np.ndarray) -> None:
    pcm = (np.clip(stereo, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"FAILED: {' '.join(cmd)}\n{r.stderr[-2000:]}")


def main() -> None:
    BUILD.mkdir(exist_ok=True)
    original = BUILD / "original.wav"
    print("synthesizing 60 s music-like signal ...")
    stereo = synth()
    write_wav(original, stereo)

    print("encoding labeled set ...")
    # True lossless
    run([FFMPEG, "-y", "-i", str(original), "-c:a", "flac", str(BUILD / "true_lossless.flac")])

    # Genuine lossy MP3s
    run([LAME, "--silent", "-b", "320", "--cbr", str(original), str(BUILD / "mp3_320.mp3")])
    run([LAME, "--silent", "-V", "0", str(original), str(BUILD / "mp3_v0.mp3")])
    run([LAME, "--silent", "-b", "256", "--cbr", str(original), str(BUILD / "mp3_256.mp3")])
    run([LAME, "--silent", "-b", "192", "--cbr", str(original), str(BUILD / "mp3_192.mp3")])
    run([LAME, "--silent", "-V", "2", str(original), str(BUILD / "mp3_v2.mp3")])
    run([LAME, "--silent", "-b", "128", "--cbr", str(original), str(BUILD / "mp3_128.mp3")])

    # Decode the 128 and 192 sources back to WAV (transcoding stock)
    dec128 = BUILD / "dec128.wav"
    dec192 = BUILD / "dec192.wav"
    run([LAME, "--silent", "--decode", str(BUILD / "mp3_128.mp3"), str(dec128)])
    run([LAME, "--silent", "--decode", str(BUILD / "mp3_192.mp3"), str(dec192)])

    # Fake-320: 128-sourced re-encoded as 320 CBR
    run([LAME, "--silent", "-b", "320", "--cbr", str(dec128), str(BUILD / "fake320_from128.mp3")])

    # Fake-FLAC: 128- and 192-sourced encoded as FLAC
    run([FFMPEG, "-y", "-i", str(dec128), "-c:a", "flac", str(BUILD / "fakeflac_from128.flac")])
    run([FFMPEG, "-y", "-i", str(dec192), "-c:a", "flac", str(BUILD / "fakeflac_from192.flac")])

    # Band-limited legit master probes (false-positive arbitration case, 5.12)
    # (a) brickwall at 18 kHz via numpy FFT zeroing - worst case, cliff like a lossy cutoff
    spec = np.fft.rfft(stereo, axis=0)
    freqs = np.fft.rfftfreq(stereo.shape[0], 1 / SR)
    spec[freqs > 18000, :] = 0
    brick = np.fft.irfft(spec, n=stereo.shape[0], axis=0)
    bw_wav = BUILD / "bandlimited_brickwall18k.wav"
    write_wav(bw_wav, brick)
    run([FFMPEG, "-y", "-i", str(bw_wav), "-c:a", "flac", str(BUILD / "bandlimited_brickwall18k.flac")])
    # (b) gentle 2nd-order butterworth lowpass at 18 kHz (analog-style master rolloff)
    run([FFMPEG, "-y", "-i", str(original), "-af", "lowpass=f=18000", "-c:a", "flac",
         str(BUILD / "bandlimited_gentle18k.flac")])

    # Undecodable-by-miniaudio probe: tiny AAC/m4a
    run([FFMPEG, "-y", "-i", str(original), "-t", "3", "-c:a", "aac", str(BUILD / "tiny.m4a")])

    for f in sorted(BUILD.iterdir()):
        if f.suffix in (".mp3", ".flac", ".wav", ".m4a"):
            print(f"  {f.name:32s} {f.stat().st_size/1e6:7.2f} MB")
    print("fixtures OK")


if __name__ == "__main__":
    main()
