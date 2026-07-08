# Syncbox — M5 Plan (packaging: PyInstaller onedir + Tauri bundle, macOS)

> **Role.** A distilled map + increment sequence, same status as M4-PLAN: *a map, not an
> authority*. If anything here seems to contradict [SPEC-UNIFIED.md](SPEC-UNIFIED.md), the
> spec wins. Baseline: `build/front-fable` after bugfix round 5 (`196bfe6`), 396 pytest +
> 57 vitest + cargo check green. The app runs from source only (`pnpm tauri dev` spawns the
> venv python); M5 makes the packaged `.app` the acceptance surface.

## 0. Owner arbitrations (settled 2026-07-07 — do not re-open)

1. **Signing: NO — package unsigned.** `security find-identity -v -p codesigning` still
   returns 0 identities (re-checked 2026-07-07, unchanged since POC #1). Consequences:
   keep the sqlcipher `SecretsStore` (§6.7 unsigned path), no keyring migration, no
   notarization. The readme ships the "app is damaged / right-click → Open" caveat.
   Signing + keyring migrate-and-purge become a post-M5 follow-up; the POC #1 exit
   criteria stay the recipe for that day.
2. **Windows scope: macOS-only.** Windows becomes **M5.W** once a Windows host exists.
   The OS seams stay visible and documented (as M4 did); no speculative Windows code.

## 1. Facts from the kit (read once, 2026-07-07)

### 1.1 Proven freeze recipe (POC #3, GO)

- **onedir**, `hiddenimports=['_cffi_backend']`, `optimize=0`, no upx/strip, console exe
  ([sidecar_poc.spec](../poc/03-bundle-size-coldstart/sidecar_poc.spec)). Measured on the
  full lawful dependency surface: **51 MB**, **0.44 s** warm spawn→HTTP 200.
- Caveat: **~15 s first-ever run** (macOS first-exec scan) on the dev machine. Re-measure
  on a clean account in M5.4 **before** building any first-run splash.
- Nuitka excluded (§6.11: no decisive gap); onefile rejected (cold-start + unstable
  extraction path harms secrets). Do not re-open either.

### 1.2 The three M4 seams M5 replaces

- [`sidecar/src/syncbox/__main__.py`](../sidecar/src/syncbox/__main__.py) — composition
  root, honors `SYNCBOX_DATA_DIR`; this module is the PyInstaller entrypoint
  (`pathex=['src']`; the sidecar has no build backend by design — add nothing unless the
  freeze itself demands it).
- [`shell/src-tauri/src/main.rs`](../shell/src-tauri/src/main.rs) `sidecar_command()` —
  the dev seam (venv python + `PYTHONPATH`). M5: **debug → venv (kept working), release →
  bundled binary resolved from the app resources.** Everything around it (process_group(0),
  output consumption, handshake, supervisor) is proven and must not change.
- [`sidecar/src/syncbox/secrets.py`](../sidecar/src/syncbox/secrets.py) — sqlcipher store.
  **Unchanged in M5** (arbitration 1 = unsigned).

### 1.3 Version skew T13 — the 6 hardcoded spots (§6.11: one canonical source)

`sidecar/pyproject.toml` (0.0.1) · `shell/src-tauri/Cargo.toml` (0.1.0) ·
`shell/src-tauri/tauri.conf.json` (0.1.0) · `ui/package.json` (0.1.0) ·
`ui/src/components/AppSidebar.vue` ("v0.1") · `ui/src/screens/SettingsScreen.vue` ("v0.1.0").
(A 7th spot surfaced during M5: `shell/package.json` — pinned with the others.)

### 1.4 Harnesses to retarget (M4.3, currently spawn `VENV_PY -m syncbox`)

`shell/harness/driver_lifecycle.py` (T1–T6: topology, tree-kill, port release, production
shutdown handshake, crash-vs-intent) · `test_single_instance.py` ·
`test_supervisor_restart.py`. After M5 they must pass against the **frozen binary** —
tree-kill must kill the PyInstaller bootstrap **and** its worker, port 8765 freed.

### 1.5 Legal bundle surface (invariant)

Allowed: pyrekordbox / sqlcipher3 / sqlalchemy / numpy / miniaudio+cffi / mutagen /
rapidfuzz / psutil (+ starlette/sse-starlette/uvicorn). If the freeze collects anything
download-shaped (streamrip, deemix, ffmpeg media path, ARL/provider tooling) → **stop**.
Only secret: the Spotify OAuth token. The bundle audit is a hard check in M5.1, not a
manual glance.

### 1.6 Unchanged by design

Transport/CSP (§6.3 incl. the `tauri://localhost` amendment already in `server.py`) —
re-verify on the packaged app, no code expected. Supervisor/lifecycle logic (§6.6).
Secrets (§6.7 unsigned path).

## 2. Increments (each ends green: 396 pytest + 57 vitest + cargo check; no watch modes)

### M5.1 — Freeze the sidecar (onedir)

- `sidecar/sidecar.spec` adapted from the POC recipe: entrypoint
  `src/syncbox/__main__.py`, `pathex=['src']`, `hiddenimports=['_cffi_backend']`,
  `optimize=0`, onedir, name `syncbox-sidecar`. PyInstaller is a dev-only tool (venv),
  never a runtime dependency.
- **Check (failing-if-broken):** a harness script that builds nothing but *verifies* the
  built dist — spawns the frozen binary with a temp `SYNCBOX_DATA_DIR`, asserts `/health`
  200 on 8765, asserts clean shutdown via `POST /shutdown`, and **audits the collected
  bundle for forbidden names** (§1.5). Lives in `shell/harness/`.

### M5.2 — Version single-source (closes T13)

- One canonical source; the five others are injected/derived at build, or read at runtime
  from an injected constant (UI: a Vite `define` from `package.json`; the two Vue
  hardcodes become reads of that constant). Exact mechanism decided in-increment — the
  invariant is: **editing one file bumps everywhere**.
- **Check (failing-if-broken):** a small test that fails when any of the 6 spots disagree
  with the canonical source.

### M5.3 — Bundle as `externalBin` + shell resolution

- Known friction (§6.11 ponytail note): `externalBin` wants one file per target-triple;
  onedir is `exe + _internal/`. Resolve **without re-opening onefile** — candidates:
  externalBin = the triple-suffixed exe with `_internal/` shipped adjacently via
  `bundle.resources`, or the whole onedir under `bundle.resources` with the exe spawned
  by path. Decide at build on what Tauri 2.11 actually does with adjacency.
- `sidecar_command()` branches: `debug_assertions` → venv seam unchanged; release →
  resolve the bundled binary from the resource dir. Spawn semantics identical
  (own process group, piped output).
- **Check:** cargo check green; `pnpm tauri dev` still spawns the venv (dev loop intact);
  the resolution logic carries its smallest test or harness assertion.

### M5.4 — Packaged-app acceptance (the acceptance surface)

- `pnpm tauri build` (unsigned) → the `.app` launches on a **clean macOS account**;
  sidecar spawns from resources and answers `/health` on 8765; SSE + fetch alive from the
  real webview origin (`tauri://localhost`).
- Measure the first-ever-run penalty on the clean account. **Splash only if the ~15 s
  reproduces** — measure before building UI for it.
- Faithful reporting: cold-start regression, origin failure, or forbidden dep = said
  plainly, never masked.

### M5.5 — Retarget the M4.3 harnesses at the frozen binary

- The three harnesses accept the packaged binary as target (env override, venv default
  stays for dev). Tree-kill, port freed, single-instance, shutdown handshake, crash-vs-
  intent: all must hold against the PyInstaller process tree.

### M5.S — Signing + notarization + keyring (OUT OF SCOPE, arbitration 1)

Deferred until a Developer ID exists. Recipe on that day: POC #1 exit criteria (sign each
sidecar binary post-bundle, hardened runtime + entitlements → Tauri signs the bundle →
`notarytool`), then §6.7 keyring switch with migrate-and-purge in `secrets.py`.

### M5.W — Windows (OUT OF SCOPE, arbitration 2)

Deferred until a Windows host exists: taskkill /T + named-mutex single-instance,
`http://tauri.localhost` origin re-verify, `master.db` path formats, size/cold-start.

## 3. Close protocol

Three-lens adversarial review — sequential, high effort, single agent: **packaging
correctness** / **failure modes** (clean-account launch, tree-kill on the packaged binary,
secrets at rest, first-run) / **test & harness adequacy** → fix pass → **one closing
commit** for the milestone on `build/front-fable`.
