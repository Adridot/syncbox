# PROMPT-03 — Building Syncbox (from scratch)

> Historical construction prompt. Superseded for the current macOS v1 release
> by PROMPT-05, SPEC-UNIFIED, and the final-release closure handoff.

> **How to use it.** Paste this prompt into a Claude Code session **at the root of a fresh repository** (or the current repository if you are starting over from scratch inside it). The word **`ultracode`** activates multi-agent orchestration if you want it. The **ponytail** module must remain active (`/ponytail full`) — it is an **implementation constraint**, not an option. The authoritative spec is [SPEC-UNIFIED.md](SPEC-UNIFIED.md): **do not re-debate it**, **execute it**.

---

ultracode — `/ponytail full`

## Mission

Build **Syncbox** — an open-source **macOS + Windows** desktop app that syncs Spotify playlists to a DJ's **Rekordbox** collection, **maintains the collection** (duplicates, missing files, tags, **Smart Fixes**, **fake-320/FLAC detection**), offers a **legal purchase path** (Beatport/Bandcamp links), and an **optional download module OFF by default** (Deezer via streamrip) — **from scratch**, following [SPEC-UNIFIED.md](SPEC-UNIFIED.md).

**The goal**: the **cleanest, most functional, and most streamlined** code that implements the spec, without inherited debt. This rewrite is deliberately *from scratch*: the existing test code (`service/tests/`) is **not** an architecture constraint — only the **behavioral invariants** matter ([SPEC-UNIFIED §5](SPEC-UNIFIED.md)). You write **your own tests**.

## Clean-room Build — Isolation Rule

You build in a **NEW and EMPTY** repository. The old Syncbox implementation **does not exist here, deliberately**. You must **NEVER** search for it, clone it, import it, or port its code — neither the original `service/`, nor `electron/`, nor `src/`, nor `docs/_analysis/`. The `file:line` references and bug identifiers (`Bx`/`Fx`/`Tx`/`Dx`) you encounter in the specs are **simple traceability labels**: the correct behavior is **described explicitly** in [SPEC-UNIFIED §5](SPEC-UNIFIED.md) — you **reproduce the invariant, you do not open the old code**. If information is missing, you **ask for it** (`AskUserQuestion`); you **never** infer it from an existing repository.

## Inputs (Authority Hierarchy)

1. **[SPEC-UNIFIED.md](SPEC-UNIFIED.md)** — **authoritative** for every architecture/product decision: resolved forks (§7.1), §10 answers (§7.2), D1–D25 (§7.3), non-negotiables (§3), domain model (§4), behavioral invariants (§5), architecture (§6), de-risking order (§8).
2. **`docs/_research/00–14`** — the **sourced and dated state of the art** behind each choice. Re-read before implementing an infrastructure block (signing, transport, secrets, multi-OS, migrations, supervision, acquisition) or a v1 addition (Chromaprint/11, fake-320/12, legal purchase/13, streamrip/14). External research — reference no existing code.
3. **[SPEC-01-syncbox.md](SPEC-01-syncbox.md)** — **constants appendix ONLY** (weights, thresholds, buckets). Consult only to **settle a constant** when §5 is not enough. ⚠️ The `file:line` references it cites **are NOT in this repository**: **do not search for them**, do not attempt to read the cited code.

In case of conflict: SPEC-UNIFIED > SPEC-01 (constants) > research. (`docs/_analysis/` is **outside the kit** — see the isolation rule.)

## Implementation Principles (Non-Negotiable)

1. **Ponytail for every block.** Climb the ladder: (1) should it exist? (2) stdlib? (3) native OS/platform feature? (4) already installed dependency? (5) one line? (6) the minimum that works. The shortest diff that passes the tests wins. Mark each deliberate simplification with `# ponytail:` (what is deferred + when to add it back).
2. **Altitude: exhaustive on the WHAT, free on the HOW.** The spec fixes the invariants, forks, and non-negotiables; **the rest is your freedom** — choose the best implementation within these boundaries. The spec's `reco` recommendations are sourced defaults, not mandates: you can do better, with justification.
3. **Safety first.** The non-negotiables [§3](SPEC-UNIFIED.md) are **hard guards**, never simplifiable: “RB/rekordboxAgent closed” guard before any mutation, `_mutate` (assert → backup → mutate → commit → invalidate cache; rollback on exception), reversible soft-delete, **load-bearing status integers** (256/258, `rb_data_status`) reproduced identically, volume-relative/absolute path resolution, **never move files** + TCC quirk, secrets never in plaintext.
4. **No simplification without its test.** Any non-trivial logic (branch, loop, parser, safety/money path) leaves **one** runnable check that fails if the logic breaks. No heavy framework, no unnecessary fixtures.
5. **Faithful reporting.** If a POC fails or reveals that a spec choice does not hold up, **say it** and escalate the decision — do not hide a blocker.

## Decided Stack (Forks A–D — [SPEC-UNIFIED §7.1](SPEC-UNIFIED.md))

- **A — Rekordbox Writes**: `master.db` **in place, without XML mode**, via **pyrekordbox** (Python, MIT). Product core = MyTags + smart playlists.
- **B — Shell**: **Tauri v2** (native webview), Python sidecar in `externalBin`. Electron fallback **only** if POC #1 (signing) blocks.
- **C — Transport**: **HTTP REST + SSE on localhost** (sidecar = **Starlette + `sse-starlette`**, uvicorn 1 worker in the main asyncio loop). **No** JSON-RPC stdio. Server bound to `127.0.0.1`, origins restricted to loopback.
- **D — Acquisition**: **OPTIONAL module, OFF by default**; **legal B2 path highlighted** (Beatport/Bandcamp purchase links, **stdlib `urllib`, zero network on the app side**). Download = **streamrip imported as a lib** (git pin **v2.2.0**, pinned SHA, **Deezer-only v1**), thin interface `DeezerAcquirer.download(track_id) -> Path`, **never on the critical `master.db` path**; **GPL-3 code not embedded in the base artifact** (separate component). **deemix-fork = documented fallback**; SoundCloud → v2 (ffmpeg). full-track = **POC #6**, lib choice **decided (streamrip)**.

**v1 additions (OVERHAUL-01 scope, [§7.4](SPEC-UNIFIED.md))**: A1 Smart Fixes, A3 fake-320/FLAC, B2 Legal Track Matcher (+ D7 untagged). **Deferred to v2**: A2 Chromaprint fingerprint dedup (LGPL binary, POC), SoundCloud (B4, ffmpeg), A5 AcoustID.

**Hard conditions to respect** (sourced, [§6](SPEC-UNIFIED.md)): macOS sidecar signing in **POST-bundle step** (#11992 open); OAuth `redirect_uri` **hardcoded** to `http://127.0.0.1:8765/callback` + response independent of Host; PyInstaller worker **tree-kill** (otherwise orphaned port 8765); migrations **`PRAGMA user_version` + stdlib scripts** (seed = migration `0001`); secrets **`keyring` if signed / encrypted store if unsigned** (Spotify tokens **AND** Deezer ARL); cloud/exFAT file deletion = OS trash **otherwise permanent deletion with prior consent**. **v1 additions**: Smart Fixes (A1) writes `master.db` **only via `_mutate`** (dry-run→confirm→mutate, snapshot freshness guard, `protected` excluded by default); fake-320 (A3) **read-only** (`miniaudio`+`numpy.fft`, never in `_mutate`); Track Matcher (B2) = **zero network on the app side**; acquisition lib forces the **`certifi` bundle** (TLS never disabled) and **never writes the ARL in plaintext** (no `config.toml`).

## Work Order — POC First (De-Risking Before Any Commitment)

> **Phase 0 = GATE.** Do not build the complete app before having resolved the 9 risks of [SPEC-UNIFIED §8](SPEC-UNIFIED.md) (6 infra + 3 v1 additions). Each POC is minimal, disposable, and concludes with a GO/NO-GO verdict escalated to the owner.

**Phase 0 — De-Risking POCs** (in order):
1. **Signing + notarization of the PyInstaller sidecar under Tauri macOS** (#11992, POST-bundle `codesign`+`notarytool` step). NO-GO → Electron fallback (Fork B).
2. **Process lifecycle**: spawn + supervision + **tree-kill** (mac process-group **and** Windows `taskkill /T`) + clean SQLCipher shutdown + release of port 8765 + single-instance.
3. **Bundle size + cold-start** measured (PyInstaller `--onedir`, real venv numpy+sqlcipher3+pyrekordbox+**miniaudio/cffi (A3)**+downloader; `fpcalc`/A2 outside v1).
4. **`EventSource`/SSE in real WKWebView + WebView2** (Starlette+sse-starlette over HTTP localhost), not in Chromium/Electron.
5. **pyrekordbox write fidelity on RB 7.x** (smart playlists/MyTags, bug #110) — non-regression harness on the `master.db` schema.
6. **Acquisition (B1) — blocking gate**: full-track **Deezer** with real **Premium ARL** (vs 30 s preview) via **streamrip lib** (git pin v2.2.0, pinned SHA), by **numeric ID resolved from the ISRC**; `DeezerAcquirer` wrapper via `PendingSingle.resolve()→track.download_path` (D18, ARL **in memory**, `Config`/job, F2/F3); packaging `pycryptodomex`(Blowfish)/`mutagen` mac+Win. **Switch to deemix-fork** if aiohttp cost / API fragility is blocking. NO-GO → **B1 deferred to v1.1, B2 (legal) remains the missing-tracks path, the rest deliverable**.
7. **Fake-320/FLAC (A3)**: real bundle delta `miniaudio`+`cffi`+`pycparser` mac+Win (`hiddenimport _cffi_backend`, **`optimize=0`**, numpy as a direct dependency); rolloff calibration (320/V0 boundary = `uncertain` zone) + false positives on band-limited masters; A3→D6 wiring (quality criterion downgrade, never in `_mutate`). NO-GO/non-calibratable → fallback **A3-lite** (snapshot fields, 0 native dependency) or v2.
8. **Legal Track Matcher (B2)**: Beatport/Bandcamp URL on 5-10 real tracks (correct first-result rate); “shop disappeared” fallback (entry removed from the catalog at build → absent button). **Zero network on the app side.**
9. **Smart Fixes (A1)**: `dry-run` == payload actually written; deterministic order + **idempotence** (re-run = no-op); `protected` guard excluded by default (named non-memorized opt-in); **freshness guard** (re-validation `(mtime,size)` at `_mutate` entry, ABORT if the DB changed); exclusive passage through `_mutate`.

**Phase 1 — Safety Core** (the most valuable): `pyrekordbox` + the §3.1/§5.1 backbone (RB closed guard, `_mutate`, backup, soft-delete, restore, path resolution §3.2/§5.2). **Tests first** on these invariants — this is the contract that protects the user's collection.

**Phase 2 — Domain Model & Service**: §4 entities, app SQLite + `user_version` migrations, Starlette HTTP+SSE transport, secrets at rest (§6.7), supervision (§6.6), fixed-port OAuth PKCE (§6.10), multi-OS abstraction (§6.9).

**Phase 3 — Business Logic**: ISRC/fuzzy matching (§5.3, single normalization D19), dedup + explicit keeper (§5.4, D5/D6 **discrete ordered scale**), **Smart Fixes (A1, §5.11 — dry-run→confirm→mutate via `_mutate`, FIXED structural catalog, `protected` excluded, freshness guard)**, **fake-320/FLAC detection (A3, §5.12 — read-only `miniaudio`+`numpy.fft`, verdict → keeper downgrade D6)**, library sync (§5.6), events + smart playlists (§5.7), untagged/missing (§5.8), **Legal Track Matcher (B2, §5.13 — Beatport/Bandcamp URL with stdlib `urllib`, zero network on the app side)**, acquisition (§5.5, **streamrip Deezer-only**, real output path D18, concurrency without global F2/F3) — **optional module OFF by default**.

**Phase 4 — Shell & UI**: Tauri v2, Vue 3 UI (FR/EN i18n), **one single** cache layer + one canonical job SSE stream, single-instance, “backend unavailable” state.

**Phase 5 — Packaging**: PyInstaller `--onedir`, signing/notarization (per POC #1), single-source version; **`miniaudio`/`cffi`/`pycparser` bundled (A3, `optimize=0`, numpy as direct dependency)**; GPL-3 acquisition module **delivered separately** (outside the base artifact); **no auto-update** (consistent with `no-auto-build-release` memo).

> The detailed UI/UX (§10.9) and configurable matching (§10.10) are **delegated to the design phase** (SPEC-UNIFIED §9) — do not lock them here; design the flows once the rest holds.

## Test Contract

The contract is the set of **behavioral invariants** ([SPEC-UNIFIED §5](SPEC-UNIFIED.md)), not the inherited pytest suite. **Write your own tests**, covering first: the RB guard + `_mutate` + backup (safety), the 256/258 status integers, volume-relative/absolute path resolution, the TCC quirk (`Path.exists()`), the ISRC collision guard, status transitions (sync/event/acquisition), the explicit keeper (ordered D6 scale + A3 downgrade taking precedence over the declared bitRate), reversible deletion. **v1 additions**: Smart Fixes (dry-run == mutate, idempotence, deterministic order, `protected` excluded, freshness guard, `_mutate` passage); fake-320 (verdict, never in `_mutate`, `ok`/neutral by default if not analyzed); Track Matcher (URLs built correctly, **zero network call on the app side**). No heavy fixtures; one runnable check per non-trivial invariant.

## Definition of “Done”

- The 9 Phase 0 POCs are GO (or their NO-GO is escalated with the fallback applied: B1→v1.1, A3→A3-lite/v2).
- All §3 non-negotiables are upheld and **tested**.
- The §5 invariants (including §5.11–§5.13) are reproduced and covered by new tests.
- **The 4 v1 additions are delivered and tested**: A1 Smart Fixes (via `_mutate`), A3 fake-320/FLAC (read-only), B2 Legal Track Matcher (zero network on the app side), B1 streamrip Deezer-only **if POC #6 GO** (otherwise deferred to v1.1 without blocking the release — B2 covers missing tracks). **A2 fingerprint dedup and SoundCloud are outside v1** (deferred to v2).
- The app runs on macOS **and** Windows; the sidecar starts/stops cleanly (tree-kill, no orphan, port released).
- Zero plaintext secrets (Spotify tokens + Deezer ARL encrypted, no streamrip `config.toml`); zero hardcoded path; single source of truth (data + settings); GPL-3 acquisition code **not embedded in the base artifact**.
- Each ponytail simplification has its `# ponytail:` (what is deferred + when to add it back).

## Interaction Rules

- **Any structuring choice not covered by the spec → ask** (`AskUserQuestion`), ponytail reco first.
- Ponytail active: deliverable first, short explanation afterward; the simplification is justified by its brevity.
- Language: **French**.
