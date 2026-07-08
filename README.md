# Syncbox

Lawful Rekordbox collection maintenance for DJs — Tauri v2 shell, Vue 3 UI,
Python sidecar (Starlette HTTP+SSE on `127.0.0.1:8765`). See
[docs/SPEC-UNIFIED.md](docs/SPEC-UNIFIED.md) for what it does and why.

## Build the packaged app (macOS)

```sh
cd shell && pnpm tauri build --bundles app
```

This builds the UI, freezes the sidecar (PyInstaller onedir, `sidecar/sidecar.spec`)
and bundles everything into
`shell/src-tauri/target/release/bundle/macos/Syncbox.app`.

Prerequisites: `pnpm install` in `ui/` and `shell/`, plus the sidecar venv
(`uv sync` in `sidecar/`, Python 3.14).

## Unsigned build caveat

The app is currently **not code-signed or notarized** (no Apple Developer ID —
owner decision 2026-07-07, see `docs/M5-PLAN.md` §0). On another Mac, Gatekeeper
will refuse the first launch with *"Syncbox is damaged and can't be opened"* or
*"cannot be opened because the developer cannot be verified"*. To run it anyway:

- **Right-click the app → Open → Open** (once; macOS remembers), or
- `xattr -dr com.apple.quarantine /path/to/Syncbox.app`.

Secrets at rest use the encrypted sqlcipher store (SPEC-UNIFIED §6.7, unsigned
path). Signing + notarization + Keychain migration is a documented follow-up
(POC #1 exit criteria) for the day a Developer ID exists.

## Dev loop

```sh
cd shell && pnpm tauri dev   # spawns the sidecar from sidecar/.venv
```

Tests: `cd sidecar && .venv/bin/python -m pytest -q` · `cd ui && pnpm test` ·
`cd shell/src-tauri && cargo check`. Packaging harnesses live in
`shell/harness/` (see each file's docstring).
