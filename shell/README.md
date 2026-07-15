# shell — Tauri v2 shell & process supervisor

The native wrapper: one window, and the supervision of the Python sidecar
(SPEC-UNIFIED §6.6). Order is load-bearing in
[src-tauri/src/main.rs](src-tauri/src/main.rs): single-instance first, sidecar
spawned in its own process group, output always consumed, bounded restarts
(3× backoff) then a `backend-down` event, shutdown handshake
(`POST /shutdown` → SIGTERM group → SIGKILL group).

Dev spawns the sidecar from `sidecar/.venv`; the release build resolves the
bundled PyInstaller binary from the app resources (`Resources/sidecar/`).
The permanent REST/SSE server uses `127.0.0.1:8766`. Spotify authorization
temporarily opens only the exact `http://127.0.0.1:8765/callback` listener and
releases it after the attempt.

```sh
pnpm install --frozen-lockfile
pnpm tauri dev                    # dev loop (Vite + source sidecar)
pnpm bundle:macos                 # locked arm64 .app + frozen onedir sidecar
cd src-tauri
cargo test --locked
cargo check --locked --target aarch64-apple-darwin
```

The release application is written to
`src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app`.
It targets macOS 14+ on Apple Silicon and is ad-hoc signed; no Developer ID,
notarization, Windows bundle, or auto-update is part of v1.

Regression harnesses in [harness/](harness/) (run with the sidecar venv
python; docstrings give the exact commands):

- `driver_lifecycle.py` — tree-kill, port release, shutdown handshake,
  crash-vs-intent; retarget at the frozen binary with `SYNCBOX_SIDECAR_BIN`.
- `test_lifecycle_edges.py` — foreign port collision, exact stale-sidecar
  cleanup, and immediate-exit cleanup.
- `test_single_instance.py` / `test_supervisor_restart.py` — full shell
  behavior; retarget at the packaged app with `SYNCBOX_SHELL_BIN`.

Run the source and frozen sidecar lanes from the repository root:

```sh
sidecar/.venv/bin/python shell/harness/driver_lifecycle.py
SYNCBOX_SIDECAR_BIN=sidecar/dist/syncbox-sidecar/syncbox-sidecar \
  sidecar/.venv/bin/python shell/harness/driver_lifecycle.py
```

Run all shell-level checks against the exact packaged executable:

```sh
SYNCBOX_SHELL_BIN=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app/Contents/MacOS/syncbox-shell \
  sidecar/.venv/bin/python shell/harness/test_single_instance.py
SYNCBOX_SHELL_BIN=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app/Contents/MacOS/syncbox-shell \
  sidecar/.venv/bin/python shell/harness/test_supervisor_restart.py
SYNCBOX_SHELL_BIN=shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app/Contents/MacOS/syncbox-shell \
  sidecar/.venv/bin/python shell/harness/test_lifecycle_edges.py
```
