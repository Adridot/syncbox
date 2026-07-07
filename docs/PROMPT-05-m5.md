# PROMPT-05 — M5 : packaging (PyInstaller onedir + Tauri bundle, macOS d'abord)

> **How to use.** Paste into a **fresh** Claude Code (Fable) session at the repo root, branch
> `build/front-fable` (the accepted M4: front redone by Fable + bugfix rounds 1–4, latest
> commit `edddec1`). **Single-agent session by design**: this prompt deliberately omits the
> multi-agent keyword; do not launch workflows or agent fan-outs. `/ponytail full` stays
> active. Interaction in **French**; all repository content in **English**.

## Mission

Execute milestone **M5 — packaging**: freeze the sidecar as a PyInstaller **onedir** binary,
bundle it into the Tauri app as an `externalBin`, wire the shell to spawn the bundled binary
(replacing the dev seam), single-source the app version, and — **only if a Developer ID
exists** — sign + notarize and switch secrets to `keyring`. macOS first (Phase 0 owner
decision). M1–M4 are closed; the front was redone on `build/front-fable` and hardened over
four bugfix rounds from live owner testing (**396 pytest + 57 vitest green**, typecheck + vite
build + cargo check green). The app runs today only from source (`pnpm tauri dev` spawns
`sidecar/.venv/bin/python -m syncbox` with `PYTHONPATH=src`, no packaging yet).

There is **no M5-PLAN yet**. Your **first increment** is to read the kit once, produce
`docs/M5-PLAN.md` (a distilled map + increment sequence, same role as M4-PLAN: *a map, not an
authority*), and **settle the two owner arbitrations below via `AskUserQuestion`** before
writing any packaging code.

## Owner arbitrations to settle first (do NOT guess — `AskUserQuestion`, ponytail reco first)

1. **Signing.** POC #1 is DEFERRED because the dev machine had **no Apple Developer ID**
   ([poc/01-sidecar-signing/VERDICT.md](../poc/01-sidecar-signing/VERDICT.md)). Ask whether a
   Developer ID is now available.
   - **Yes** → run the POC #1 exit criteria (sign each sidecar binary post-bundle: hardened
     runtime + entitlements, then Tauri signs the bundle, then `notarytool`); on GO, switch
     secrets from the sqlcipher store to **`keyring`** with a migrate-and-purge (SPEC-UNIFIED
     §6.7). NO-GO → documented Electron fallback (§6.2) is an owner call, not a default.
   - **No** → stay **unsigned**: keep the sqlcipher secrets store, package unsigned, ship the
     "app is damaged / right-click-open" caveat in the readme. Signing becomes a follow-up.
2. **Windows scope.** M4 kept the OS seams visible but implemented **macOS only**. The Windows
   halves of POC #2/#3/#4/#5 are still unrun (tree-kill via `taskkill /T` + named-mutex
   single-instance; WebView2 `http://tauri.localhost` origin re-verify; `master.db` path
   format letter/UNC/volume-relative; Windows size/cold-start). Ask: **this milestone =
   macOS-only packaging**, or **mac + Windows** (and is a Windows machine available to run the
   harnesses)? Ponytail reco: macOS-only now, Windows as M5.W once a Windows host exists.

## Authority hierarchy

1. [SPEC-UNIFIED.md](SPEC-UNIFIED.md) — QUOI/architecture. Packaging is **§6.11** (PyInstaller
   onedir, single-source version, `sqlcipher3-wheels` vendored), secrets **§6.7** (signed →
   keyring / unsigned → encrypted store), lifecycle **§6.6**, transport **§6.3**, de-risk
   order + hard POC conditions **§8**, owner answers **§7.2**.
2. [M4-PLAN.md](M4-PLAN.md) §1.2/§3 — the shell recipe and the seams M5 must replace.
3. `docs/M5-PLAN.md` — the map you produce in increment 1. If it seems to contradict a spec,
   the spec wins and you say so.

## Read first — token discipline

Read **once**, in this order, then build from memory + targeted lookups:

1. `poc/03-bundle-size-coldstart/VERDICT.md` + `poc/03-bundle-size-coldstart/sidecar_poc.spec`
   — the proven onedir recipe (onedir, `hiddenimports=['_cffi_backend']`, `optimize=0`;
   measured **51 MB / ~0.44 s** warm cold-start; **~15 s first-ever run** caveat).
2. `poc/01-sidecar-signing/VERDICT.md` — why signing is deferred + the exit criteria.
3. `poc/02-lifecycle-treekill/VERDICT.md` — the Windows caveats (only if Windows is in scope).
4. `SPEC-UNIFIED.md` — **only** §6.3, §6.6, §6.7, §6.11, §7.2, §8.
5. The three M4 seams M5 replaces, read once:
   - `sidecar/src/syncbox/__main__.py` — the composition root; the PyInstaller entrypoint is
     this module (`python -m syncbox` frozen). It honors `SYNCBOX_DATA_DIR` (harnesses).
   - `shell/src-tauri/src/main.rs` — `sidecar_command()` carries the **dev seam** comment
     (spawns the venv python via `PYTHONPATH`); M5 makes it resolve the bundled binary from
     the app resources **while keeping the dev path working** (e.g. a debug-vs-release branch).
   - `sidecar/src/syncbox/secrets.py` — the sqlcipher `SecretsStore` (unsigned path); the
     keyring switch (if signing GO) lives here + a migration.

Do **not** re-read the kit afterwards; grep the specific section when a detail is missing.
Never read `docs/_research/04*`, `10*`, `14*` (deprecated download research). Never read
`docs/SPEC-01-syncbox.md` unless a constant is missing from §6.

## Clean-room (strict)

The old implementation does not exist here, deliberately. Never read the `master` branch, any
other branch, git history of other branches (**including the `opus-m4` attribution branch**),
or any older app on this machine — the current working tree of `build/front-fable` is the
only authority, including for any subagent. In particular, never read `build/clean-room-kit`
or `opus-m4` (Opus's rejected M4 front). Missing info → `AskUserQuestion`, never guess.

## Legal constraints (invariant, verbatim)

- The bundled venv contains **no download/acquisition dependency** (there are none in v1):
  no streamrip, deemix, ARL tooling, ffmpeg media path, or provider-download registry. The
  measured surface is pyrekordbox / sqlcipher3 / sqlalchemy / numpy / miniaudio+cffi / mutagen
  / rapidfuzz / psutil (§6.1/§8 item 3). If the freeze pulls in anything download-shaped, stop.
- The only secret packaged/handled is the **Spotify OAuth token** (§6.5/§6.7). No ARL, no
  provider credential, ever.
- Do not add, prototype, or test any download/extract/DRM-bypass path to "complete" packaging.

## Execution rules

1. Follow the `docs/M5-PLAN.md` increments **in order**; each ends green — the full existing
   suite stays green (`cd sidecar && .venv/bin/python -m pytest -q` = 387; `cd ui && pnpm test`
   = 53; `cargo check`). No watch modes.
2. The **packaged app is the acceptance surface**: a GO increment means the bundled app
   launches on a **clean macOS account** and the sidecar spawns + answers `/health` on 8765.
   Retarget the M4.3 harnesses (`shell/harness/*`) from `python -m syncbox` to the packaged
   binary — tree-kill, port freed, single-instance, shutdown handshake must still pass.
3. Owner arbitrations above are settled once, at the top — do not re-open them. Any **new**
   structural decision the kit does not settle → stop and `AskUserQuestion`, ponytail reco
   first.
4. Ponytail at every brick; deliberate simplifications carry their `ponytail:` marker. No
   dependency or tool beyond what §6.11/§8 name (PyInstaller; **not** Nuitka — POC #3 showed no
   decisive gap) without asking.
5. Non-trivial logic ships its smallest failing-if-broken check (the version single-source, the
   secrets migration if signing GO, the binary-resolution path).
6. Faithful reporting: a bundle that pulls a forbidden dep, a cold-start regression on a clean
   account, a notarization rejection, a Windows seam that does not hold — say it, never mask it.
7. Windows code paths only if arbitration 2 puts Windows in scope **and** a Windows host is
   available; otherwise keep the seams visible and defer (as M4 did).

## Known M5 facts to carry (pointers, not paraphrase)

- **Entrypoint**: freeze `src/syncbox/__main__.py` (`pathex=['src']`); the sidecar has no build
  backend by design (pyproject ponytail note) — decide at build time (spec `pathex` vs adding a
  minimal backend), don't smuggle a packaging framework.
- **Version single-source** (§6.11, closes skew T13): today the version is hardcoded in **6
  places** — `sidecar/pyproject.toml` (0.0.1), `shell/src-tauri/Cargo.toml` (0.1.0),
  `shell/src-tauri/tauri.conf.json` (0.1.0), `ui/package.json` (0.1.0),
  `ui/src/components/AppSidebar.vue` ("v0.1"), `ui/src/screens/SettingsScreen.vue` ("v0.1.0").
  One canonical source injected at build.
- **externalBin**: sidecar binary suffixed with the target triple; the shell resolves it from
  the bundle resources at runtime (release) and from the venv (dev).
- **First-run splash**: only if the ~15 s first-exec penalty reproduces on a clean account
  (POC #3 caveat) — measure before building UI for it.
- **CSP / origins**: unchanged from M4 (§6.3 amendment already in `server.py`); re-verify the
  webview origin on the packaged app (macOS `tauri://localhost`).

## Done means

- Sidecar frozen (onedir), bundled as a Tauri `externalBin`, shell spawns the bundled binary
  in release and the venv in dev; version single-sourced; the packaged `.app` launches on a
  clean macOS account with the sidecar healthy on 8765; retargeted harnesses green.
- Signing path resolved per arbitration 1 (notarized + keyring-migrated **or** documented
  unsigned); Windows per arbitration 2 (done + harnesses green **or** explicitly deferred with
  the seams visible).
- Zero download/acquisition dependency in the bundle; zero cleartext secret.
- Close protocol: **three-lens adversarial review** (sequential, high effort, single agent —
  *packaging correctness* / *failure modes: clean-account launch, tree-kill on the packaged
  binary, secrets at rest, first-run* / *test & harness adequacy*) → fix pass → **one closing
  commit** for the milestone on `build/front-fable`.

## Interaction

Livrable d'abord, explication courte ensuite. Langue d'échange : **français**.
