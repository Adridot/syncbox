# POC #3 — Sidecar bundle size + cold-start (PyInstaller onedir)

**Status: GO — 2026-07-02.**

## Setup

`app.py`: minimal Starlette app importing the full lawful v1 dependency surface
(pyrekordbox, sqlcipher3, sqlalchemy, numpy, miniaudio+cffi, mutagen, rapidfuzz, psutil)
served by uvicorn 1 worker in the main asyncio loop (SPEC-UNIFIED §6.3). Built with
`sidecar_poc.spec`: onedir, `hiddenimports=['_cffi_backend']`, `optimize=0` (§6.12).
Python 3.14.5, PyInstaller 6.21, macOS arm64.

## Measurements

| Metric | Value | Spec expectation |
|---|---|---|
| Uncompressed onedir size | **51 MB** (50.84 MB) | ~95–120 MB feared (§6.1) |
| Cold-start, median spawn→HTTP 200 | **0.444 s** | ≤ ~3 s |
| Cold-start, first-ever run | 15.0 s (one-time; macOS first-exec scan / cold page cache) | — |
| In-process import→ready | 0.28–0.31 s warm | — |
| SSE route | streams 3 events through curl -N | must stream |

## Verdict

GO. The bundle is **half** the spec's feared floor (numpy 2.5 + Python 3.14 are leaner
than the research-era measurements) and warm cold-start is ~0.4 s. Onedir confirmed; no
need to evaluate Nuitka (§6.11: only if the measurement showed a decisive gap — it
does not).

## Caveats

- First-ever launch after install paid a one-time ~15 s penalty on this machine
  (first-exec scan). Subsequent launches are sub-second. Re-check on a clean account
  during M5 packaging; if it reproduces on end-user installs, show a first-run splash.
- Windows size/cold-start still to be measured before M5 (macOS-first decision,
  Phase 0 owner call).
