## Why

The README is a 202-line technical specification dump. A DJ who lands on the
repo has to read a six-point guarded-write pipeline, an ASCII architecture
diagram, and a `uv sync --locked` build recipe before learning whether Syncbox
solves a problem they have. There is no badge row, one screenshot, no
navigation, and end-user value is interleaved with contributor-only material.
The repo is public and the app is user-facing: the README is the product page,
and right now it reads like `docs/SPEC-UNIFIED.md`.

## What Changes

- **Rewrite `README.md` as a landing page**, English only, structured to the
  convention of large public GitHub repos: hero + tagline, badge row, hero
  screenshot, "who it's for / the problem", feature sections with per-feature
  screenshots, quick start, safety summary, FAQ, then links out to docs.
- **Lead with value, not architecture.** Every feature section states the DJ
  problem in plain language first, the Syncbox answer second. Jargon
  (`ISRC`, `MyTag`, `master.db`, sidecar, PKCE) is either dropped or defined
  inline on first use.
- **Add a badge row**: CI status, latest release, license, platform
  (macOS Apple Silicon).
- **Reserve per-feature screenshot slots** for Spotify matching, Events,
  Duplicates, and Performance history, as HTML comment placeholders plus a
  documented drop location, so Adrien can add captures without touching prose.
- **Move contributor-only content out of the README**: build-from-source,
  dev loop, test commands, packaging harnesses, and the repository layout
  table go to a new `CONTRIBUTING.md`. The full component architecture
  diagram goes to `docs/SPEC-UNIFIED.md`'s existing architecture material,
  referenced by link.
- **Add `SUPPORT.md`** — where to ask a question vs. where to file a bug vs.
  where to report a vulnerability (`.github/SECURITY.md` already exists).
- **Condense the safety model** to a short reassurance block in the README
  with the six-point pipeline preserved verbatim in
  [docs/USER_GUIDE.md](../../../docs/USER_GUIDE.md) ("Rekordbox write safety"),
  which already covers it.
- **Keep the version-pinned install instructions accurate** — the current
  release asset name and tag stay in sync with `0.7.2`.

Not in scope: issue and PR templates, a logo/banner redesign, translating the
README to French, and capturing the screenshots themselves.

## Capabilities

### New Capabilities

None. This change only rewrites documentation; no application behavior
changes, so no capability spec is created or modified.

### Modified Capabilities

None.

`skip_specs: true` is set in this change's `.openspec.yaml`.

## Impact

- `README.md` — full rewrite.
- `CONTRIBUTING.md` — new file (build, dev loop, tests, repo layout).
- `SUPPORT.md` — new file (question / bug / vulnerability routing).
- `docs/` — no content moves in; the README links to the existing
  `USER_GUIDE.md`, `SPEC-UNIFIED.md`, `DISTRIBUTION.md`, `PRIVACY.md`, and
  `POC-EVIDENCE.md` instead of duplicating them.
- No code, no dependencies, no CI changes. `.github/SECURITY.md` unchanged.
- Release process: the README install section still quotes a version and an
  asset filename, so the existing release-prep recipe keeps its README bump
  step.
