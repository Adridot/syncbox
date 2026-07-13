# Phase 5 Handoff — Conditional B1 Deezer Acquisition

Date: 2026-07-13

## Verdict

**B1 GATE: BLOCKED.**

**READY FOR PHASE 6 IMPLEMENTATION, NOT READY FOR RELEASE ACCEPTANCE.**

No Premium Deezer ARL is available from the authorized local application state
or dedicated environment variables. A real full-track POC therefore could not
run. This is not evidence that streamrip fails, so the verdict is not NO-GO.
The Phase 9 gate forbids speculative B1 implementation in this state.

B1 is deferred from macOS v1 to v1.1 unless the owner later supplies a Premium
ARL locally and the complete gate is rerun. The ARL must never be pasted into a
chat, committed, logged, exported, placed in a fixture, or written to a
streamrip configuration file.

B2 remains the only v1 missing-track acquisition path. Its Beatport and
Bandcamp links remain browser-only and visually primary.

## Credential availability check

The check was deliberately limited to presence and never displayed a value:

- `DEEZER_ARL`, `SYNCBOX_DEEZER_ARL`, and `ARL` were absent from the current
  process environment;
- the existing encrypted SQLCipher store was opened with
  `mode=ro&immutable=1` and `PRAGMA query_only = ON`;
- the store contained no non-empty secret whose name included `deezer` or
  `arl`;
- no credential file exists in the repository;
- no secret value was read into output, copied, logged, or written.

The local result was:

```text
deezer_or_arl_secret_present=no
```

This check does not claim that no ARL exists elsewhere on the machine. It
establishes only that no ARL, and therefore no verifiable Premium entitlement,
was available to this task through the authorized Syncbox state.

## Current upstream verification

The current streamrip release is
[`v2.2.0`](https://github.com/nathom/streamrip/releases/tag/v2.2.0), published
on 2026-03-12. The exact tag revision is:

```text
189acda489927719aa8591f6acdd7d67aecf929b
```

The release includes a Deezer URL parsing fix, but a later open report still
documents Deezer ARL authentication failures on v2.2.0. Full-track viability
must therefore be demonstrated with the owner's real account rather than
inferred from a release note or another user's report.

The source at that exact revision confirms the intended resolution flow:

1. `Config.defaults()` reads the packaged blank template;
2. job-specific values can be assigned to `config.session`, including the ARL,
   output directory, disabled download databases, disabled conversion, and
   enabled TLS verification;
3. `DeezerClient.login()` authenticates through the job's session ARL;
4. `PendingSingle.resolve()` obtains metadata and a `Track` for a numeric
   Deezer ID;
5. `Track.rip()` downloads and post-processes the file;
6. `track.download_path` is the downloader's actual resulting path and must be
   checked on disk.

These classes are streamrip CLI internals, not a documented stable embedding
API. The exact revision and an integration test must therefore guard every
future use.

Relevant primary source files:

- [release and exact tag](https://github.com/nathom/streamrip/releases/tag/v2.2.0);
- [package metadata and GPL-3.0-only declaration](https://github.com/nathom/streamrip/blob/189acda489927719aa8591f6acdd7d67aecf929b/pyproject.toml);
- [`Config.defaults()` and configuration persistence](https://github.com/nathom/streamrip/blob/189acda489927719aa8591f6acdd7d67aecf929b/streamrip/config.py);
- [Deezer login and downloadable resolution](https://github.com/nathom/streamrip/blob/189acda489927719aa8591f6acdd7d67aecf929b/streamrip/client/deezer.py);
- [`PendingSingle`, `Track.rip()`, and `download_path`](https://github.com/nathom/streamrip/blob/189acda489927719aa8591f6acdd7d67aecf929b/streamrip/media/track.py);
- [library orchestration](https://github.com/nathom/streamrip/blob/189acda489927719aa8591f6acdd7d67aecf929b/streamrip/rip/main.py);
- [TLS and certifi selection](https://github.com/nathom/streamrip/blob/189acda489927719aa8591f6acdd7d67aecf929b/streamrip/utils/ssl_utils.py);
- [process-global download semaphore](https://github.com/nathom/streamrip/blob/189acda489927719aa8591f6acdd7d67aecf929b/streamrip/media/semaphore.py);
- [process-global progress manager](https://github.com/nathom/streamrip/blob/189acda489927719aa8591f6acdd7d67aecf929b/streamrip/progress.py);
- [open Deezer authentication failure report](https://github.com/nathom/streamrip/issues/969).

## Upstream constraints requiring proof on a future rerun

No architecture choice was made for these items because the credential gate
failed before implementation:

- importing `streamrip.config` immediately creates streamrip's application
  directory through `os.makedirs`; a future optional component must neutralize
  and test this side effect without writing an ARL or `config.toml`;
- `Track.download()` uses a mutable process-global semaphore, and streamrip's
  progress layer owns a process-global manager; a future implementation must
  prove that concurrent job-local configuration cannot exchange state or bind
  a semaphore to the wrong event loop;
- certifi is an optional streamrip extra, while Phase 9 requires the embedded
  CA bundle and forbids disabling TLS verification; the optional component must
  install and freeze certifi explicitly and test the effective SSL context;
- streamrip v2.2.0 declares `Pillow >=9,<11` while Syncbox uses Python 3.14;
  dependency resolution and Apple Silicon packaging remain POC evidence, not an
  assumption;
- the public streamrip source does not resolve an ISRC itself. The POC must
  resolve the ISRC to one numeric Deezer track ID before invoking
  `PendingSingle` and must reject missing or ambiguous results;
- the open authentication report means a valid-looking ARL is insufficient
  evidence. The POC must verify actual login and a complete file longer than a
  preview.

## Licensing and distribution boundary

streamrip v2.2.0 declares `GPL-3.0-only` and ships the GPLv3 license. The base
Syncbox artifact must remain fully functional without it and must contain no
streamrip code or dependency. The current base environment satisfies that
boundary: streamrip is not importable, is absent from the sidecar dependency
list and PyInstaller spec, and no streamrip- or Deezer-named file is present in
the existing onedir or macOS application bundle.

Any future in-process optional component needs a dedicated distribution and
license review. The GNU GPL distinguishes a separate aggregate from modules
combined into one program, and its FAQ treats shared-address-space function
calls as strong evidence of a combined work. This legal boundary must not be
represented as solved merely because installation is optional.

Primary licensing sources:

- [streamrip GPL-3.0-only metadata](https://github.com/nathom/streamrip/blob/189acda489927719aa8591f6acdd7d67aecf929b/pyproject.toml);
- [streamrip GPLv3 license](https://github.com/nathom/streamrip/blob/189acda489927719aa8591f6acdd7d67aecf929b/LICENSE);
- [GNU GPLv3, sections 5 and 6](https://www.gnu.org/licenses/gpl-3.0.en.html);
- [GNU GPL FAQ on aggregation and plug-ins](https://www.gnu.org/licenses/gpl-faq.en.html#MereAggregation).

Deezer's current terms expressly prohibit downloading, ripping, and bypassing
technical protection measures. This reinforces the Phase 9 decision to keep
B1 optional, separate, disabled by default, and subordinate to the legal B2
path. This note records product risk and is not legal advice.

Source: [Deezer Terms and Conditions, article 6](https://www.deezer.com/legal/cgu).

## Workspace state and intentionally absent implementation

The current workspace has no B1 domain model, service, API, UI, or tests:

- the missing center supports purchase links and local relink only;
- settings contain no acquisition flag or ARL field;
- the encrypted store is generic but is currently wired only for Spotify;
- the canonical `/events` SSE bus exists, but acquisition jobs do not;
- migration `0004_event_delete_state.sql` is the latest app migration;
- streamrip is absent from `sidecar/pyproject.toml`, `sidecar/sidecar.spec`, the
  frozen sidecar, and the macOS application bundle;
- the UI exposes no acquisition controls or provider placeholder;
- `acquisition_failed` remains excluded from purchase-link statuses because B1
  is not delivered.

No application source, migration, dependency, lockfile, API, UI, test, POC
evidence directory, or packaging file was added or changed in Phase 5. The
repository changes are this handoff and `poc/run_b1_deezer_acquisition.py`, a
one-shot future gate runner that remains outside the application and optional
component.

## Verification commands and results

```sh
git ls-remote https://github.com/nathom/streamrip.git \
  refs/tags/v2.2.0 refs/tags/v2.2.0^{}
# 189acda489927719aa8591f6acdd7d67aecf929b refs/tags/v2.2.0

git clone --depth 1 --branch v2.2.0 \
  https://github.com/nathom/streamrip.git \
  /tmp/syncbox-streamrip-v2.2.0-189acda
# detached at 189acda489927719aa8591f6acdd7d67aecf929b

PYTHONDONTWRITEBYTECODE=1 sidecar/.venv/bin/python -c \
  'import importlib.util; print("streamrip_importable=" + ("yes" if importlib.util.find_spec("streamrip") else "no"))'
# streamrip_importable=no

PYTHONDONTWRITEBYTECODE=1 sidecar/.venv/bin/python -m py_compile \
  poc/run_b1_deezer_acquisition.py
# passed

find sidecar/dist shell/src-tauri/target/release/bundle/macos -type f \
  \( -iname '*streamrip*' -o -iname '*deezer*' \) -print
# no output

cd sidecar
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -rs \
  -p no:cacheprovider tests/test_purchase_links.py tests/test_settings.py
# 14 passed

cd ../ui
pnpm test -- src/screens/__tests__/missing-center.spec.ts \
  src/screens/__tests__/settings.spec.ts
# Vitest ran the complete suite: 19 files, 66 tests passed
```

The encrypted-store check used the existing key only to open the existing
database read-only. It queried only a count of matching secret names and
printed only the boolean result shown above.

No full-track POC, dependency installation, network download, audio scan,
relink, or Rekordbox mutation was attempted. The accepted Phase 4 baseline was
not reclassified: Python had 463 passes and 11 private-fixture skips; UI
typecheck and production build had passed; Cargo test and check had passed.
Phase 5 reran the focused Python settings and purchase-link tests and the full
UI suite with the results shown above. No full Python suite, typecheck, build,
or Cargo command was rerun because no executable or dependency file changed.
The future POC runner was syntax-checked only; it cannot run without the
separate pinned streamrip component and a local Premium ARL file.

## Release and Phase 6 impact

Phase 6 implementation may proceed because Phase 9 explicitly makes B1
conditional and B2 remains available. Phase 6 must package and document the
actual B2-only v1 product; it must not add streamrip, an ARL setting, an empty
acquisition screen, or a claim that full-track acquisition is supported.

Release acceptance remains blocked by the private Rekordbox and retained-event
fixtures from earlier phases, final unsigned macOS packaging validation, and
truthful user documentation. In particular, the legacy user guide still
describes Deemix/ARL download behavior that does not exist in the current
application and must be corrected before release.

## Future B1 gate restart

When a Premium ARL is available locally, restart Phase 5 from the POC rather
than from implementation. The minimum admissible evidence is:

1. inject the ARL from a local non-exported secret channel without printing it;
2. resolve a representative ISRC to exactly one numeric Deezer ID;
3. configure one isolated job in memory with TLS verification and certifi;
4. leave file-backed streamrip databases and conversion disabled;
5. execute the supported resolution and download flow on Apple Silicon;
6. prove the result is a complete track, record the real `download_path`, scan
   it successfully, and delete the POC output after evidence capture;
7. prove no config file, ARL log, plaintext export, or cross-job state exists;
8. decide GO or NO-GO before changing Syncbox application code.

Only a GO result authorizes the Phase 9 migration, secrets wiring, unified job
service, API, canonical SSE integration, UI, tests, and separate optional
component packaging.

The helper entry point is `poc/run_b1_deezer_acquisition.py`. It expects the
ARL in `/tmp/syncbox-premium-arl` with owner-only permissions, deletes that
file after reading it, and prints only structured non-secret results.
