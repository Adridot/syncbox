# shell — Tauri v2 shell & process supervisor

The native wrapper: one window, and the supervision of the Python sidecar
(SPEC-UNIFIED §6.6). Order is load-bearing in
[src-tauri/src/main.rs](src-tauri/src/main.rs): single-instance first, sidecar
spawned in its own process group, output always consumed, bounded restarts
(3× backoff) then a `backend-down` event, shutdown handshake
(`POST /shutdown` → SIGTERM group → SIGKILL group).

Dev spawns the sidecar from `sidecar/.venv`; the release build resolves the
bundled PyInstaller binary from the app resources (`Resources/sidecar/`).

```sh
pnpm install
pnpm tauri dev                    # dev loop (vite + shell + venv sidecar)
pnpm tauri build --bundles app    # packaged .app (also freezes the sidecar)
cd src-tauri && cargo check       # fast typecheck
```

Regression harnesses in [harness/](harness/) (run with the sidecar venv
python; docstrings give the exact commands):

- `driver_lifecycle.py` — tree-kill, port release, shutdown handshake,
  crash-vs-intent; retarget at the frozen binary with `SYNCBOX_SIDECAR_BIN`.
- `test_single_instance.py` / `test_supervisor_restart.py` — full shell
  behavior; retarget at the packaged app with `SYNCBOX_SHELL_BIN`.
