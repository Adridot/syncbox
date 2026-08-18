# Contributing to Syncbox

Thanks for taking a look. Syncbox writes to the one file a DJ cannot afford to
lose — their Rekordbox database — so the bar for changes that touch the write
path is high. Everything else is ordinary open-source work.

## Build from source

You need an Apple Silicon Mac on macOS 14 or later, plus
[pnpm](https://pnpm.io), [Rust](https://rustup.rs), and
[uv](https://docs.astral.sh/uv/). The build uses separate locked Python
projects: Python 3.14 for the base sidecar and Python 3.13 for the optional
component.

```sh
pnpm install --frozen-lockfile
(cd sidecar && uv sync --locked --managed-python)
pnpm --dir shell bundle:macos
```

The bundle lands at:

```text
shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app
```

The full release contract — reproducible builds, the optional component, asset
naming, and signing posture — is in [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md).

## Dev loop and tests

```sh
pnpm --dir shell tauri dev                       # app against the source tree
(cd sidecar && uv run --locked pytest -q -rs)    # sidecar suite
pnpm --dir ui test                               # UI suite
pnpm --dir ui typecheck
mkdir -p sidecar/dist/syncbox-sidecar            # resource required by Tauri
cargo check --locked --manifest-path shell/src-tauri/Cargo.toml \
  --target aarch64-apple-darwin
```

Packaging regression harnesses — lifecycle, single-instance, supervisor, frozen
bundle — live in [shell/harness/](shell/harness/). Each file's docstring says
how to run it.

## Repository layout

| Path | What |
|---|---|
| `sidecar/` | Python sidecar — domain logic, HTTP+SSE API, Rekordbox writes |
| `optional-component/` | Separately distributed pinned Deezer/streamrip runner |
| `ui/` | Vue 3 front end |
| `shell/` | Tauri shell (Rust supervisor) + packaging harnesses |
| `docs/` | Specification, user guide, distribution contract, privacy, POC evidence |
| `openspec/` | Change proposals and capability specs |
| `scripts/` | Release build, packaging, license generation, and fixture tooling |
| `release/` | License inventories and notice bundles shipped with the released apps |

The current product and architecture specification is
[docs/SPEC-UNIFIED.md](docs/SPEC-UNIFIED.md). Read it before changing behaviour;
the spec wins over any mockup or convenience.

## Proposing a change

Non-trivial work is planned before it is coded. Change proposals live in
[openspec/changes/](openspec/) — each one carries a proposal, a capability
spec delta where behaviour changes, a design note, and a task list. Open an
issue first if you are unsure whether an idea fits.

## Pull requests

- Branch from `master`; keep the branch up to date with it — `master` requires
  it before merging.
- CI must be green. It runs the sidecar suite, UI typecheck, the UI suite, and
  `cargo check`.
- **Squash merge only.** This repository keeps a linear history.
- If you add or change a UI or Python dependency, regenerate the licence
  inventories under `release/` — `sidecar/tests/test_release_licenses.py`
  fails otherwise, which fails CI.
- Anything touching the Rekordbox write path needs a test and a note in the PR
  describing what a failed write would leave behind.

## Reporting problems

Bugs and questions go through [SUPPORT.md](SUPPORT.md). Suspected
vulnerabilities go through [.github/SECURITY.md](.github/SECURITY.md) — never
a public issue.
