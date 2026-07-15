# POC #6 — A3 Audio-Quality Validation

Date: 2026-07-12

## Objective and risk

Validate the local `miniaudio` + CFFI + NumPy FFT path in source mode, a fresh
PyInstaller onedir, and the sidecar embedded in a fresh macOS app. The product
risk is a confident keeper penalty against a legitimate band-limited master.

## Environment

- macOS 26.5.1 (25F80), Apple Silicon arm64;
- Python 3.14.5;
- PyInstaller 6.21.0;
- miniaudio 1.71 / miniaudio C 0.11.25;
- CFFI 2.0.0;
- NumPy 2.5.0;
- FFmpeg 8.1.1;
- LAME 3.100.

The corpus is generated in a temporary directory and is never committed. It
contains genuine LAME 320 CBR, V0, 256 CBR, 192 CBR, 128 CBR, genuine FLAC,
192-to-FLAC, legitimate 16 kHz band-limited FLAC and 320 CBR, silence, a
sub-second file, and undecodable bytes.

## Exact commands

```sh
PYTHONDONTWRITEBYTECODE=1 sidecar/.venv/bin/python poc/run_a3_audio_quality.py

cd sidecar
.venv/bin/pyinstaller --noconfirm --clean sidecar.spec
cd ..

PYTHONDONTWRITEBYTECODE=1 sidecar/.venv/bin/python \
  poc/run_a3_audio_quality.py \
  --analyzer sidecar/dist/syncbox-sidecar/syncbox-sidecar

pnpm --dir shell tauri build --bundles app

PYTHONDONTWRITEBYTECODE=1 sidecar/.venv/bin/python \
  poc/run_a3_audio_quality.py \
  --analyzer shell/src-tauri/target/release/bundle/macos/Syncbox.app/Contents/Resources/sidecar/syncbox-sidecar

SYNCBOX_SHELL_BIN=shell/src-tauri/target/release/bundle/macos/Syncbox.app/Contents/MacOS/syncbox-shell \
  sidecar/.venv/bin/python shell/harness/test_single_instance.py
```

## Results

All three analyzer modes produced the same measurements:

| Case | Expected | Actual | Cutoff |
|---|---|---|---:|
| genuine 320 CBR | `ok` | `ok` | 20,157 Hz |
| genuine V0 | `ok` | `ok` | 22,050 Hz |
| genuine 256 CBR | `incertain` | `incertain` | 19,461 Hz |
| genuine 192 CBR | penalizing signal | `incertain` | 18,763 Hz |
| genuine 128 CBR | penalizing signal | `incertain` | 16,671 Hz |
| genuine lossless | `ok` | `ok` | 22,050 Hz |
| 192 CBR to FLAC | penalizing signal | `incertain` | 18,763 Hz |
| band-limited lossless master | `incertain` | `incertain` | 15,963 Hz |
| band-limited 320 master | `incertain` | `incertain` | 16,057 Hz |
| silence | neutral | `ok` | neutral |
| very short | neutral | `ok` | neutral |
| undecodable | neutral | `ok` | neutral |

- exact displayed verdicts: 9/12;
- keeper-penalty confusion after fallback: TP=0, FP=0, TN=9, FN=3;
- onedir: 52 MiB;
- app: 73 MiB;
- `_miniaudio`, `_cffi_backend`, and NumPy PocketFFT are arm64 Mach-O bundles;
- the onedir and app copies of those three binaries have matching SHA-256;
- the packaged shell spawned exactly one embedded sidecar, reached `/health`,
  shut down cleanly, and released port 8765.

The exact-path test covers spaces and non-ASCII characters. Source guards and
the CLI smoke verify no directory enumeration, network call, file mutation,
application composition, or app-data creation on the diagnostic path.

## Verdict and fallback

**NO-GO for full A3 spectral-only detection.** Low cutoffs describe both the
legitimate band-limited cases and lossy sources. Moving a threshold cannot
separate the overlapping cases.

The accepted fallback returns `incertain` for every sub-threshold decoded
file. `incertain` is keeper-neutral, and the spectral path emits no
`lossy_source_probable` penalty. This deliberately creates three false
negatives in the corpus and zero false-positive penalties. A trusted penalty
remains deferred until real labeled evidence supports it.

Supported native miniaudio decoders are WAV, FLAC, MP3, and Vorbis. AAC/M4A,
Opus, read errors, silence, and very short files remain neutral.

## Sources

- [pyminiaudio formats and decode API](https://github.com/irmen/pyminiaudio)
- [NumPy `rfft`](https://numpy.org/doc/stable/reference/generated/numpy.fft.rfft.html)
- [FFmpeg libmp3lame options, including configurable low-pass](https://ffmpeg.org/ffmpeg-codecs.html#libmp3lame)
- [PyInstaller hidden-import guidance](https://pyinstaller.org/en/stable/when-things-go-wrong.html#listing-hidden-imports)
- [Apple file-access guidance](https://developer.apple.com/documentation/security/accessing-files-from-the-macos-app-sandbox)

The historical `docs/_research/12_FFT-faux-320.md` file referenced by older
specifications is absent from this checkpoint and was not reconstructed.
