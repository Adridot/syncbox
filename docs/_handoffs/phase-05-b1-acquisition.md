# Phase 5 Handoff — B1 Deezer Acquisition

Date: 2026-07-13

## Verdict

**B1 GATE: GO.**

**READY FOR PHASE 6 RERUN. NOT READY FOR RELEASE ACCEPTANCE.**

Phase 6 superseded the source-only venv installer described below with the
owner-approved separate self-contained PyInstaller onedir component. The final
packaged boundary, hash, measurements, and remaining publication gates are in
[`final-release-closure.md`](final-release-closure.md). This Phase 5 handoff
remains the historical full-track acquisition evidence; the Phase 6 handoff is
also historical.

The real Deezer full-track gate was rerun with a local one-shot Premium ARL.
The ARL was never printed, logged, committed, copied into fixtures, or written
to a streamrip configuration file. The credential file was consumed and
deleted by the POC harness.

B1 is now implemented for macOS v1 as an optional, explicitly enabled,
Deezer-only path. B2 purchase links remain the primary and visually first
missing-track path.

## POC evidence

Root executed the POC outside the repository and outside the base sidecar
environment:

- POC venv: `/tmp/syncbox-b1-poc-venv`;
- Python: 3.14.5 arm64;
- streamrip: 2.2.0 at commit
  `189acda489927719aa8591f6acdd7d67aecf929b`;
- certifi: 2026.6.17;
- representative ISRC: `USQX91300105`;
- Deezer track id: `67238732`;
- API duration: 337 s;
- measured downloaded duration: 337.56 s;
- file size: 13,520,081 bytes;
- output filename:
  `05. Daft Punk - Instant Crush (feat. Julian Casablancas).mp3`;
- output path source: `track.download_path`;
- POC output cleanup: verified;
- `/tmp/syncbox-premium-arl`: absent after POC;
- `/tmp/syncbox-b1-*`: absent after POC.

The POC auto-check returned:

```json
{"certifi_version":"2026.6.17","check":"passed","credential_io":"one_shot_file_removed","global_config_dir":"untouched","platform":"macOS-arm64","result":"CHECK_PASSED","streamrip_commit":"189acda489927719aa8591f6acdd7d67aecf929b","streamrip_version":"2.2.0","tls_verification":"certifi_required"}
```

The full-track run returned:

```json
{"api_duration_seconds":337,"deezer_track_id":67238732,"file_size_bytes":13520081,"format":"mp3","measured_duration_seconds":337.56,"output_filename":"05. Daft Punk - Instant Crush (feat. Julian Casablancas).mp3","output_path_source":"track.download_path","quality":1,"result":"FULL_TRACK_DOWNLOADED"}
```

## Phase 5 source implementation at handoff

- `deezer_acquisition_enabled` setting, default `false`.
- Deezer ARL endpoints backed only by the encrypted `SecretsStore`.
- Settings export remains plaintext-safe: it includes the enablement flag but
  never includes the ARL.
- Optional streamrip component installer:
  - app-data venv under `optional/streamrip-deezer/<commit>`;
  - exact streamrip commit pin;
  - explicit certifi pin;
  - POC check before writing the component marker.
- Unified `acquisition_jobs` table with `library`, `event`, and `collection`
  scopes.
- Acquisition job API and status API.
- Canonical `/events` job progress and completion events.
- Missing center entries expose B1 only as a secondary action when enabled,
  ARL-backed, component-installed, and ISRC-backed.
- Library/event jobs store the downloaded file path as `staging_file_path` and
  move the row to `ready`.
- Collection jobs can request relink; if relink is blocked, the downloaded file
  is retained and the job is marked `relink_blocked`.
- The base sidecar dependency graph and PyInstaller spec still do not include
  streamrip.
- SoundCloud, ffmpeg, Windows, Developer ID signing, notarization, and Keychain
  remain out of v1 scope.

## Phase 5 security and distribution boundary

streamrip is not imported by the base Syncbox process. Runtime interaction goes
through a short-lived subprocess using the optional component's Python
environment. The ARL is passed through a one-shot owner-only credential file and
removed immediately; it is never passed as a command-line argument.

The current implementation intentionally keeps streamrip absent from:

- `sidecar/pyproject.toml`;
- `sidecar/uv.lock`;
- `sidecar/sidecar.spec`;
- the base sidecar import graph at application boot.

Phase 6 must rerun packaging checks and verify that the packaged base artifact
does not contain streamrip or a Deezer ARL. It must also validate that the POC
runner path used by the optional subprocess is available in the packaged app or
adapt the packaging to provide an equivalent non-GPL runner resource.

The source implementation currently creates the optional environment through
the running Python interpreter. In a frozen PyInstaller application,
`sys.executable` points to the bootloader executable rather than a reusable
Python interpreter. Phase 6 must therefore wire and validate a packaged-safe
optional component installer before release. Choosing between a separately
downloaded component runner, an approved managed Python/uv runtime, or a system
Python dependency is a distribution decision and must not be made implicitly.

## Primary sources

- [streamrip v2.2.0 release](https://github.com/nathom/streamrip/releases/tag/v2.2.0)
- [streamrip package metadata at the pinned commit](https://github.com/nathom/streamrip/blob/189acda489927719aa8591f6acdd7d67aecf929b/pyproject.toml)
- [streamrip GPLv3 license](https://github.com/nathom/streamrip/blob/189acda489927719aa8591f6acdd7d67aecf929b/LICENSE)
- [Tauri v2 sidecar documentation](https://v2.tauri.app/develop/sidecar/)
- [PyInstaller runtime information](https://pyinstaller.org/en/stable/runtime-information.html)
- [Python virtual environment documentation](https://docs.python.org/3/library/venv.html)
- [uv Python version management](https://docs.astral.sh/uv/concepts/python-versions/)
- [uv dependency management documentation](https://docs.astral.sh/uv/concepts/projects/dependencies/)
- [uv locking and syncing documentation](https://docs.astral.sh/uv/concepts/projects/sync/)

## Verification

Focused Python checks:

```sh
cd sidecar
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q \
  tests/test_settings.py tests/test_acquisition.py
# 12 passed
```

UI checks:

```sh
cd ui
pnpm test -- src/screens/__tests__/settings.spec.ts \
  src/screens/__tests__/missing-center.spec.ts
# Vitest ran the current suite: 20 files, 70 tests passed
```

## Remaining Phase 6 rerun requirements

- Re-run base artifact checks and prove streamrip remains absent.
- Validate packaged optional component installation or replace the source-tree
  POC runner lookup with a packaged runner resource.
- Replace the source-only `sys.executable -m venv` assumption with a
  packaged-safe installer path, and request an explicit distribution decision
  before selecting a runtime strategy.
- Re-run macOS sidecar lifecycle checks after the new endpoints are present.
- Verify settings/data export artifacts do not expose the ARL.
- Update release documentation to explain that Deezer acquisition is optional,
  explicit, and subordinate to purchase links.
