# POC #7 - A3 fake-320/FLAC rolloff calibration - VERDICT: GO

Date: 2026-07-02. Gate: SPEC-UNIFIED section 8 item 7 + 5.12; research note `docs/_research/12_FFT-faux-320.md`.

## Method

- **Fixtures: 100% synthetic** (numpy, seed 42): 60 s music-like signal (broadband noise bed + sawtooth harmonic stack + 10 ms transient bursts, energy up to Nyquist), 44.1 kHz stereo 16-bit WAV. No copyrighted or downloaded audio, ever. Labeled set produced with the DEV MACHINE tools `/opt/homebrew/bin/lame` (3.101b) and `/opt/homebrew/bin/ffmpeg` - **fixture tooling only, never app dependencies**. Files under `build/` (gitignored).
- **Analyzer prototype** (`a3_analyzer.py`, venv deps only): `Path.exists()`/`stat` on the resolved path first (TCC-safe, never enumerates the parent dir), read-only `miniaudio.decode_file`, mono mix, up to 60 x 1 s Hann-windowed `numpy.fft.rfft` frames, averaged power spectrum smoothed over ~201 Hz, cutoff = highest frequency still within 24 dB of the median level in the 10-15 kHz reference band, mapped to the LAME lowpass table -> 3-level verdict `ok` / `incertain` / `lossy_source_probable`. Cutoff is an intermediate value only (never persisted, per 5.12).
- Harness: `run_calibration.py` (assert-based; re-run with `sidecar/.venv/bin/python` after `make_fixtures.py`).

## Calibrated cutoff boundaries

| Container | `lossy_source_probable` | `incertain` | `ok` |
|---|---|---|---|
| MP3 (lossy container) | cutoff < **19 100 Hz** | 19 100 - 19 800 Hz | >= **19 800 Hz** |
| FLAC/WAV (lossless container) | cutoff < **19 500 Hz** | 19 500 - 20 800 Hz | >= **20 800 Hz** |

Measured cutoffs match the published LAME lowpass table (Hydrogenaudio, note 12): 320 CBR -> 20 158 Hz (table 20 094-20 627), 256 -> 19 468 (19 383-19 916), 192/V2 -> ~18 770 (18 671-19 205), 128 -> 16 700, V0 -> no lowpass (reaches 22 050). Margins to the nearest boundary are >=330 Hz for every genuine class.

## Labeled confusion table (measured)

| Label | File | Cutoff | Verdict | Gate |
|---|---|---|---|---|
| true lossless FLAC | true_lossless.flac | 22 050 Hz | ok | PASS |
| genuine MP3 320 CBR | mp3_320.mp3 | 20 158 Hz | ok | PASS (never lossy) |
| genuine MP3 V0 | mp3_v0.mp3 | 22 050 Hz | ok | PASS (never lossy) |
| genuine MP3 256 CBR | mp3_256.mp3 | 19 468 Hz | incertain | PASS (conservative, no keeper penalty) |
| genuine MP3 192 CBR | mp3_192.mp3 | 18 774 Hz | lossy_source_probable | PASS |
| genuine MP3 V2 (~190k) | mp3_v2.mp3 | 18 768 Hz | lossy_source_probable | PASS |
| genuine MP3 128 CBR | mp3_128.mp3 | 16 700 Hz | lossy_source_probable | PASS |
| fake-320 (128-sourced) | fake320_from128.mp3 | 16 699 Hz | lossy_source_probable | PASS |
| fake-FLAC (128-sourced) | fakeflac_from128.flac | 16 700 Hz | lossy_source_probable | PASS |
| fake-FLAC (192-sourced) | fakeflac_from192.flac | 18 774 Hz | lossy_source_probable | PASS |
| band-limited master, 18 kHz brickwall | bandlimited_brickwall18k.flac | 17 974 Hz | lossy_source_probable | documented accepted risk (below) |
| band-limited master, 18 kHz gentle (2nd-order butterworth) | bandlimited_gentle18k.flac | 21 012 Hz | ok | PASS (neutral) |
| undecodable AAC/m4a | tiny.m4a | n/a | ok | PASS (DecodeError caught, neutral, no unhandled exception) |
| missing file | does_not_exist.flac | n/a | ok | PASS (neutral) |

Alt-seed stability spot check (seed 7, 40 s, different chords, quieter HF bed): lossless -> ok, 320 -> ok (20 160 Hz), 192/128/fake-FLAC-128 -> lossy_source_probable. Cutoff estimates stable within 10 Hz across seeds.

**Performance**: mean 0.086 s/file, max 0.124 s/file on 60 s inputs (target <0.5 s, note 12) - decode dominates; FFT negligible.

## Gate criteria vs evidence

- Frank lossy (<=192-sourced: genuine 192, V2, 128, fake-320-from-128) reliably flagged: **yes, 4/4**.
- Fake-FLAC (128- and 192-sourced) reliably flagged: **yes, 2/2**.
- True lossless and genuine 320/V0 never flagged lossy: **yes** (320 -> ok, V0 -> ok; 320/V0 boundary lands in ok, satisfying "incertain or ok, never lossy_source_probable").
- Band-limited legit master case: **documented as accepted risk per 5.12** - an 18 kHz *brickwall* master is spectrally indistinguishable from a lossy cutoff by rolloff alone, so it is flagged `lossy_source_probable` (false positive accepted and foreseen by 5.12: "faux positifs masters band-limites a arbitrer POC #7"). A *gentle* analog-style 18 kHz rolloff (2nd-order butterworth) correctly stays neutral (`ok`), because it never drops 24 dB below the reference band before Nyquist. In v1 the consequence of the accepted false positive is bounded: one-notch D6 demotion, never deletion, verdict displayed with its reason.
- Undecodable input degrades to neutral `ok` with no unhandled exception: **yes** (AAC/m4a via `miniaudio.DecodeError`; missing path also neutral).

## Caveats (non-blocking)

1. **Brickwall band-limited masters are flagged** (accepted risk per 5.12, see above). If real-catalog sampling later shows this is frequent, raise only the lossless-container `lossy` boundary or add a slope-sharpness discriminator - the 3-level design already reserves `incertain` for arbitration.
2. **Genuine 256 lands in `incertain`** - correct conservative behavior (no keeper penalty per 5.12), but note 256 content is not "proven ok".
3. **320/V0-sourced fakes are undetectable** by rolloff (V0 applies no lowpass; physical limit already acknowledged in 5.12/note 12) - out of scope of the flag by design.
4. Calibration is on synthetic content with healthy HF energy. Quiet/ambient real content with little natural HF may read lower cutoffs; worst plausible effect is genuine-320 drifting into `incertain` (harmless, no penalty). Real-catalog false-positive sampling (POC#A3-3 in note 12) remains an implementation-phase check.
5. AAC/m4a/opus hole assumed per 5.12 (neutral verdict, no ffmpeg in v1).

**A3-lite fallback not needed.** Calibration produced clean, stable, physically anchored boundaries with the venv-only stack (miniaudio + numpy.fft).
