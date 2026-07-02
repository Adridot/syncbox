# POC #2 — Sidecar process lifecycle / tree-kill (macOS) — VERDICT: GO

Date: 2026-07-02 · macOS (Darwin 25.5.0, arm64) · sidecar = PyInstaller 6.21 **onedir**
binary from POC #3 (`poc/03-bundle-size-coldstart/build/dist/syncbox-sidecar-poc/`,
binds 127.0.0.1:8899) · shell = Tauri v2 debug build (`shell/src-tauri`), single-instance
plugin registered first. Scope: SPEC-UNIFIED §8 item 2 (macOS half) + §6.6 hard
conditions + research 09.

## How to reproduce

```
sidecar/.venv/bin/python poc/02-lifecycle-treekill/driver_lifecycle.py       # T1–T4, T6
(cd poc/02-lifecycle-treekill/shell/src-tauri && cargo build)                # needs ~/.cargo/bin in PATH
sidecar/.venv/bin/python poc/02-lifecycle-treekill/test_single_instance.py  # T5
```

Both scripts are assert-based and exited 0; the full driver was run twice with
consistent numbers. Log artifact: `build/single-instance.log` (gitignored).

## Measured evidence

| # | Test | Result |
|---|---|---|
| T1 | Real topology (psutil) | **Single process, 0 children**, 1 thread. The onedir bootstrap `exec`s in place on macOS — no separate worker child. Listener on :8899 is the spawned pid itself. Default spawn **inherits the parent's pgid**. |
| T2 | Naive `child.kill()` on direct pid only | No surviving descendants, `lsof -iTCP:8899 -sTCP:LISTEN` empty. The orphaned-worker failure mode (Tauri #11686) is **one-file/Windows-shaped; theoretical for macOS onedir**. Tree-kill stays mandatory per §6.6 (Windows + defense in depth). |
| T3 | Tree-kill done right | Spawn with `start_new_session=True` (setsid ⇒ pgid==pid), `killpg(SIGKILL)`: 0 survivors, **port released <1 ms** after group death (killpg+reap ≈ 39 ms total), **immediate re-spawn on :8899 healthy in 0.40–0.46 s**. |
| T4 | Shutdown handshake order | SIGTERM to group → uvicorn exits gracefully (rc −15), **port released ~196–240 ms after SIGTERM**; forced SIGKILL-fallback path also releases the port (~6 ms). Production order maps to: HTTP shutdown command (close SQLCipher) → bounded wait → SIGTERM group → SIGKILL group. This POC binary has **no shutdown route**, so step 1 was exercised as SIGTERM; acceptable per gate instructions. |
| T5 | Single-instance | Second launch of the shell binary **self-exits rc=0 in 0.20 s before reaching setup**; `SINGLE_INSTANCE_CALLBACK` fires **in the first instance's pid** and spawns nothing. Log shows exactly 1 `SIDECAR_SPAWNED`, 1 `PRIMARY_INSTANCE_STARTED`; during the overlap window exactly **one** :8899 listener / one sidecar process. Primary's timed shutdown then releases the port with nothing left behind. |
| T6 | Crash vs intentional exit | External SIGKILL (crash sim) and intent-flagged shutdown both end with **identical rc −9** ⇒ exit codes/signals cannot discriminate (confirms research 09 hard condition #2). An internal `intent_shutdown` flag set **before** the kill classifies both cases correctly (Python `Supervisor` class + Rust `AtomicBool INTENT_SHUTDOWN` in the shell). |

Live confirmation of the hazard: the first driver version called `killpg` on the
T1 child that had inherited the driver's pgid — it **killed the driver and its bash
shell**. Group isolation at spawn (`setsid` / `process_group(0)`) is load-bearing, not
hygiene.

## GO criteria check

- Tree-kill + port release + immediate re-spawn on :8899: **reliable** (2 consistent runs, sub-ms port release, re-spawn healthy <0.5 s). ✅
- Single-instance prevents double sidecar: **proven** (callback in primary, second process exits pre-setup, exactly one spawn/listener). ✅

## Caveats (not NO-GO)

1. **Windows half deferred to pre-M5** per gate scope: `taskkill /T /F` (or Job
   Objects), named-mutex single-instance behavior, and Windows port-release timing are
   untested. On Windows the PyInstaller topology may genuinely be two processes — T2's
   "theoretical" finding is macOS-onedir-only and must be re-verified there.
2. This POC sidecar has **no HTTP shutdown route**; production §6.6 step 1 (shutdown
   command → SQLCipher close) was mapped to SIGTERM (uvicorn graceful). The real
   handshake with an open SQLCipher connection must be validated when the production
   sidecar exists.
3. The Rust shell spawns via `std::process::Command.process_group(0)`, not
   `tauri-plugin-shell`'s `sidecar()` API. `shell().sidecar()` does not expose group
   control; production either keeps the std spawn (recommended; bundler still ships the
   binary via `externalBin`) or adds group handling around the plugin. Also unexercised
   here: the rx-consuming supervisor loop (research 09 invariant, issue #2152) and
   bounded restart/backoff — build-phase work, not gate scope.
4. Timings are from a warm dev machine (debug shell build); cold-start under load is
   POC #3's ledger, not this one's.
