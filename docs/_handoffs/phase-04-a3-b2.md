# Phase 4 Handoff — A3 Audio Quality and B2 Purchase Links

> Historical Phase 4 evidence. Current release status and later gate results
> are recorded in [`final-release-closure.md`](final-release-closure.md).

Date: 2026-07-12

## Verdict

**READY FOR PHASE 5 IMPLEMENTATION, NOT READY FOR RELEASE ACCEPTANCE.**

B2 is implemented and browser-validated with explicit relevance limits. Full
A3 spectral-only detection is **NO-GO**; the safe fallback is implemented,
tested, frozen, and exercised from the packaged macOS app. The fallback never
turns an ambiguous cutoff into a keeper penalty.

## Implemented behavior

### A3

- analysis remains local, read-only, exact-path, TCC-safe, non-persistent, and
  outside `_mutate`;
- missing, unreadable, undecodable, silent, and very short inputs remain
  neutral `ok` failures;
- full-spectrum 320/V0 and lossless cases remain `ok`;
- every decoded sub-threshold cutoff is now `incertain` with reason
  `spectral_cutoff_ambiguous`;
- `incertain` remains neutral in D6; the spectral fallback emits no
  `lossy_source_probable` verdict;
- stereo channels are analyzed by averaging per-channel FFT power, avoiding
  cancellation on anti-phase material;
- a narrow `--quality-analyze PATH` CLI runs before app composition. It exists
  only to exercise the exact production code from frozen and embedded
  binaries and creates no database, logs, secrets, or app-data directory;
- `poc/run_a3_audio_quality.py` creates and removes its labeled corpus in a
  temporary directory and can target source, onedir, or packaged analyzers.

The preserved `lossy_source_probable` vocabulary and D6 branch remain tested
for a future trusted signal, but the current spectral heuristic does not emit
that signal.

### B2

- the production implementation already satisfied the contract and required
  no source change;
- Beatport and Bandcamp remain a fixed build-time catalog using
  `urllib.parse.quote` and shared D19 normalization;
- the sidecar performs zero store network access;
- the UI delegates purchase clicks to Tauri's external URL opener;
- At this Phase 4 checkpoint, `acquisition_failed` remained excluded because
  B1 was not implemented. This statement is superseded by the Phase 5 `GO` and
  Phase 7 integration: failed acquisitions now retain B2 purchase links.
- fully non-ASCII metadata that D19 reduces to an empty string emits no links.

## POC verdicts

### POC #6 — A3

The 12-case temporary corpus ran identically in source mode, a fresh
PyInstaller onedir, and the fresh app-embedded sidecar:

- exact displayed verdicts: 9/12;
- keeper-penalty confusion after fallback: TP=0, FP=0, TN=9, FN=3;
- false negatives: genuine 192 CBR, genuine 128 CBR, and 192-to-FLAC;
- legitimate band-limited FLAC and 320 CBR are `incertain`, never penalized;
- full A3 verdict: **NO-GO**;
- fallback verdict: **READY** as an intentionally conservative diagnostic.

Fresh bundle evidence:

- onedir: 52 MiB;
- app: 73 MiB;
- shell, sidecar, `_miniaudio`, `_cffi_backend`, and NumPy PocketFFT are arm64
  Mach-O binaries;
- the onedir and app copies of the three A3 native modules have identical
  SHA-256 values;
- the packaged shell spawned one embedded sidecar, reached `/health`, rejected
  the second app instance, shut down cleanly, and released port 8765.

Detailed evidence: [`poc/06-a3-audio-quality.md`](../../poc/06-a3-audio-quality.md).

### POC #7 — B2

Eight representative queries were tested against both stores:

- all 16 pages loaded and retained the intended query;
- Beatport showed the correct original for 3/7 real tracks and ranked it first
  for 2/7;
- Bandcamp showed and ranked the correct original first for 1/7 within the
  inspected first three results; other first results were commonly edits,
  bootlegs, remixes, or covers;
- the unavailable sentinel produced unrelated token matches on Beatport and
  an empty Bandcamp result;
- B2 verdict: **GO with documented relevance/non-ASCII limits**.

Detailed evidence: [`poc/07-b2-purchase-links.md`](../../poc/07-b2-purchase-links.md).

## Exact verification

```sh
cd sidecar
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -rs \
  -p no:cacheprovider tests/test_quality.py tests/test_purchase_links.py \
  tests/test_dedup.py tests/test_main.py tests/test_api.py
# 112 passed

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -rs \
  -p no:cacheprovider
# 463 passed, 11 skipped

cd ../ui
pnpm test
# 19 files, 66 tests passed
pnpm typecheck
# passed

cd ../shell/src-tauri
cargo test
# passed, 0 Rust unit tests
cargo check
# passed

cd ../..
PYTHONDONTWRITEBYTECODE=1 sidecar/.venv/bin/python poc/run_a3_audio_quality.py
cd sidecar && .venv/bin/pyinstaller --noconfirm --clean sidecar.spec && cd ..
PYTHONDONTWRITEBYTECODE=1 sidecar/.venv/bin/python \
  poc/run_a3_audio_quality.py \
  --analyzer sidecar/dist/syncbox-sidecar/syncbox-sidecar
pnpm --dir shell tauri build --bundles app
PYTHONDONTWRITEBYTECODE=1 sidecar/.venv/bin/python \
  poc/run_a3_audio_quality.py \
  --analyzer shell/src-tauri/target/release/bundle/macos/Syncbox.app/Contents/Resources/sidecar/syncbox-sidecar
SYNCBOX_SHELL_BIN=shell/src-tauri/target/release/bundle/macos/Syncbox.app/Contents/MacOS/syncbox-shell \
  sidecar/.venv/bin/python shell/harness/test_single_instance.py
# passed
```

The Tauri build also ran the production UI build successfully with 194 modules
transformed.

The 11 Python skips are unchanged release gates: ten private real-Rekordbox
nodes and the retained-event migration manifest node. No skip was added for
Phase 4.

The release-gate preflights were also rerun:

```sh
PYTHONDONTWRITEBYTECODE=1 sidecar/.venv/bin/python \
  poc/run_real_rekordbox_tests.py --check
# exit 2: poc/testdata/master.db is missing

PYTHONDONTWRITEBYTECODE=1 sidecar/.venv/bin/python \
  poc/run_event_migration_tests.py --check
# exit 2: poc/testdata/event-migration.json is missing
```

These are expected external-fixture blockers, not Phase 4 failures.

## Files changed

- `sidecar/src/syncbox/quality.py`
- `sidecar/src/syncbox/__main__.py`
- `sidecar/sidecar.spec`
- `sidecar/tests/test_quality.py`
- `sidecar/tests/test_purchase_links.py`
- `sidecar/tests/test_main.py`
- `ui/src/i18n/en.ts`
- `ui/src/i18n/fr.ts`
- `ui/src/screens/__tests__/missing-center.spec.ts`
- `poc/run_a3_audio_quality.py`
- `poc/06-a3-audio-quality.md`
- `poc/07-b2-purchase-links.md`
- `poc/README.md`
- `README.md`
- `docs/_handoffs/phase-04-a3-b2.md`

## Sources and missing historical research

Current primary sources used before implementation:

- [pyminiaudio](https://github.com/irmen/pyminiaudio);
- [NumPy FFT](https://numpy.org/doc/stable/reference/generated/numpy.fft.rfft.html);
- [FFmpeg libmp3lame](https://ffmpeg.org/ffmpeg-codecs.html#libmp3lame);
- [PyInstaller](https://pyinstaller.org/en/stable/operating-mode.html);
- [Apple file access](https://developer.apple.com/documentation/security/accessing-files-from-the-macos-app-sandbox);
- [Python URL parsing](https://docs.python.org/3/library/urllib.parse.html);
- [Tauri opener](https://v2.tauri.app/plugin/opener/).

`docs/_research/12_FFT-faux-320.md` and
`docs/_research/13_Achat-legal-ISRC.md` are absent from the pushed checkpoint.
They were not fabricated or silently recreated.

## Remaining release gates and exclusions

- Supply the private copied-Rekordbox fixture and run the ten real mutation
  nodes with zero skips.
- Supply the retained-event migration manifest/audio/ANLZ fixtures and run its
  real POC.
- Supply the Smart Fixes private fixture and reopen the copied result in
  Rekordbox 7.x.
- Phase 6 must resolve the effective minimum macOS mismatch, resource-seal
  acceptance, repeated cold-start measurement, unsigned distribution, and
  final package validation. Current `LSMinimumSystemVersion` is lower than
  some bundled native modules require.
- A real labeled music corpus would be required before re-enabling any A3
  penalty. The current safe fallback does not make release depend on such a
  corpus.
- B1, Windows, signing, notarization, Keychain, acquisition, transcoding, and
  event/Smart Fix behavior remain untouched.

No commit was created. The local untracked `.idea/` directory was not touched
and must remain uncommitted.
