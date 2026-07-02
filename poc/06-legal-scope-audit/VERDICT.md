# POC/Gate #6 — Legal missing-track scope audit

**Status: GO — 2026-07-02.**

Per SPEC-UNIFIED §8 item 6 and §6.5: verify that no download dependency, route, UI
toggle, setting, job, queue, credential, or POC remains in the implementation plan.

## Checks performed

1. **Repo grep** (`streamrip|deemix|ARL|soundcloud`, case-insensitive) over `poc/`,
   `sidecar/`, `syncbox-ui-ux-design/` — no hits in any code or POC path.
2. **Sidecar venv package audit** — installed set is exactly the lawful v1 dependency
   surface: pyrekordbox, sqlcipher3-wheels, sqlalchemy, rapidfuzz, mutagen, psutil,
   numpy, miniaudio+cffi, starlette, sse-starlette, uvicorn, PyInstaller. No streamrip,
   no deemix, no Deezer/SoundCloud client, no ffmpeg binding, no yt tooling.
3. **Leftover POC #6 directory** — an empty `poc/06-deezer-fulltrack/` folder existed
   (no content, never run). Deleted; this verdict file takes the #6 slot as the legal
   scope audit required by §8.
4. **Mockup** — `Syncbox.dc.html` still contains deprecated download UI markup
   (Deezer/SoundCloud add-track hint, download module + ARL settings block, ~46 lines).
   SPEC-DESIGN and PROMPT-03 already classify these areas as historical and forbidden
   to implement; the build ignores them. Note for the owner: SPEC-DESIGN §11.2 marks
   "Download toggle removed from v1 UI" as applied, but the ARL/download settings block
   is still present in the mockup file — cosmetic inconsistency only, no build impact
   (spec wins over mockup).

## Standing rule for the build

Missing tracks expose **purchase links (B2) and manual relink only**. No download
dependency, route, job, queue, progress state, provider credential, or test may be
added at any milestone. Re-check this audit before M5 packaging.
