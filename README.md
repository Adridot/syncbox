# Syncbox

**Keep your Rekordbox collection clean, matched, and gig-ready — without ever
putting it at risk.**

Syncbox is a macOS desktop app for DJs who prepare sets with Spotify and
perform with [Rekordbox](https://rekordbox.com). It bridges the two: it reads
your Spotify playlists, matches them against your Rekordbox collection, writes
MyTags and smart playlists straight into Rekordbox, and keeps the collection
itself healthy — duplicates, missing files, untagged tracks, suspicious audio
quality — all behind a safety model designed so that **no operation can lose
your library**.

## What it does

- **Spotify → Rekordbox matching** — connect your own Spotify account
  (read-only API, PKCE, no password stored), follow playlists as sources, and
  let Syncbox match every track against your collection by ISRC first, fuzzy
  title/artist second. Review and apply the matches as MyTags in Rekordbox.
- **Events** — build a set for a gig from a Spotify playlist (or link). Each
  event becomes a MyTag + smart playlist inside Rekordbox. Tracks you don't
  own yet are listed as *missing* with purchase links; drop the file you
  bought into the event's staging folder and Syncbox picks it up. Events stay
  open after applying: add tracks later and re-apply just the delta —
  idempotent, never duplicated.
- **Collection health** —
  - *Duplicates*: groups duplicate tracks, ranks the best copy (file presence,
    bitrate bucket, trusted audio-quality verdict), moves the losers' playlist and tag
    memberships onto the keeper, and sends losing files to the macOS Trash.
  - *Missing files*: finds tracks whose audio file is gone; relink them to a
    file you own or soft-remove them.
  - *Untagged*: surfaces tracks that slipped through your tagging workflow,
    with structural rules plus your own patterns.
- **Smart Fixes** — conservative bulk metadata cleanup for trailing site
  junk, Unicode whitespace/NFC, exact encoded entities, selected reversible
  mojibake signatures,
  explicit featured credits, and fill-only known remixers. Stylized casing
  and ambiguous patterns stay unchanged. The complete ordered before/after
  preview is revalidated field-for-field before anything is written.
- **Audio quality diagnostics** — a local, read-only spectral analysis reports
  a clearly full spectrum as consistent and a lower cutoff as uncertain. A
  cutoff alone cannot distinguish a lossy transcode from a legitimate
  band-limited master, so the current fallback never penalizes a duplicate
  keeper from this heuristic alone.
- **Doctor** — timestamped backups of the Rekordbox database with rotation,
  diagnostics, and application logs in one place.
- **French / English** UI.

## The safety model

Rekordbox's `master.db` is the one file a DJ cannot afford to corrupt. Every
Syncbox write goes through a single guarded pipeline:

1. **Rekordbox must be closed** — writes are refused while it runs.
2. **Timestamped backup** of the database before every mutation (rotated,
   restorable from Doctor).
3. **Exact-payload confirmation** — the dry-run you approve is exactly what
   is written, re-validated server-side.
4. **Freshness guard** — if the database changed since the preview was
   computed, the write aborts instead of applying stale plans.
5. **Reversible by construction** — deletions are soft-deletes in the
   database; audio files go to the macOS Trash. Where a volume has no
   working trash (some cloud/exFAT setups), Syncbox asks for explicit
   consent *before* anything irreversible.
6. **Files are never moved or renamed** — your folder structure is yours.

## Install (macOS, Apple Silicon)

1. Download `Syncbox-<version>-macos-arm64.zip` from
   [Releases](https://github.com/Adridot/syncbox/releases) and unzip.
2. The current app is ad-hoc signed, not signed with an Apple Developer ID and
   not notarized. On first launch macOS may say it "is damaged" or "cannot be
   verified". Either:
   - **Right-click the app → Open → Open** (once; macOS remembers), or
   - `xattr -dr com.apple.quarantine /path/to/Syncbox.app`
3. Launch. The onboarding walks you through the three things it needs: your
   Rekordbox database (one click fills the default
   `~/Library/Pioneer/rekordbox/master.db`), a storage root, and — for
   Spotify features — a free Spotify developer client ID (guided, ~2 min).

Tested with Rekordbox 7 on Apple Silicon. App data lives in
`~/Library/Application Support/Syncbox`; database backups under
`<storage root>/_syncbox/backups`.

## Architecture

```
┌───────────────────────────  Syncbox.app  ───────────────────────────┐
│  shell/   Tauri v2 (Rust) — window, process supervisor, tray of     │
│           safety plumbing: single instance, bounded restarts,        │
│           tree-kill + shutdown handshake                             │
│  ui/      Vue 3 + TypeScript — screens, guarded mutations, i18n      │
│  sidecar/ Python 3.14 (Starlette) — all domain logic, served on      │
│           127.0.0.1:8765 (REST + SSE), packaged as a PyInstaller     │
│           onedir binary inside the app bundle                        │
└──────────────────────────────────────────────────────────────────────┘
             reads/writes master.db via pyrekordbox, guarded
```

The full functional specification lives in
[docs/SPEC-UNIFIED.md](docs/SPEC-UNIFIED.md). See the
[user guide](docs/USER_GUIDE.md), [distribution contract](docs/DISTRIBUTION.md),
and [POC evidence index](poc/README.md) for the current implementation state.

## Build from source

Prerequisites: [pnpm](https://pnpm.io), [Rust](https://rustup.rs),
[uv](https://docs.astral.sh/uv/) (Python 3.14).

```sh
pnpm install --frozen-lockfile
cd sidecar && uv sync --locked --managed-python
cd ../shell && pnpm bundle:macos
# → shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app
```

Dev loop and tests:

```sh
cd shell && pnpm tauri dev                       # app against the source tree
cd sidecar && uv run --locked pytest -q -rs      # sidecar suite
cd ui && pnpm test && pnpm typecheck             # UI suite
cd shell/src-tauri && cargo check --locked --target aarch64-apple-darwin
```

Packaging regression harnesses (lifecycle, single-instance, supervisor,
frozen bundle) live in [shell/harness/](shell/harness/) — each file's
docstring says how to run it.

## Repository layout

| Path | What |
|---|---|
| `sidecar/` | Python sidecar — domain logic, HTTP+SSE API, Rekordbox writes |
| `ui/` | Vue 3 front end |
| `shell/` | Tauri shell (Rust supervisor) + packaging harnesses |
| `docs/` | Specification, plans, owner decisions, dated research |
| `poc/` | De-risking proofs-of-concept with their verdicts |
| `syncbox-ui-ux-design/` | Design kit and reference mockup |

## Status & roadmap

Current release: **0.2.1** — macOS 14+ (Apple Silicon), ad-hoc signed without a Developer ID.

- **Signing, notarization, and Keychain** — deferred; the current release uses
  a per-install encrypted SQLCipher secret store and never exports OAuth
  tokens.
- **Windows** — deferred to v2; the v1 build and validation contract is macOS
  Apple Silicon only.
- **Updates** — no in-app auto-update is implemented.
- **Later** — in-app audio preview, fingerprint-based duplicate detection
  (Chromaprint), ISRC enrichment.

## License

[MIT](LICENSE). The packaged app bundles third-party components under their
own licenses, including [mutagen](https://github.com/quodlibet/mutagen)
(GPL-2.0-or-later). A consolidated third-party notice and redistribution
review remain release gates before public binary distribution.
