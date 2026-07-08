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
  - *Duplicates*: groups duplicate tracks, ranks the best copy (format,
    bitrate, audio-quality verdict), moves the losers' playlist and tag
    memberships onto the keeper, and sends losing files to the macOS Trash.
  - *Missing files*: finds tracks whose audio file is gone; relink them to a
    file you own or soft-remove them.
  - *Untagged*: surfaces tracks that slipped through your tagging workflow,
    with structural rules plus your own patterns.
- **Smart Fixes** — bulk metadata cleanup (casing, junk suffixes, remix
  normalization…) with an exact before/after preview; what you confirm is
  byte-for-byte what gets written.
- **Audio quality verdicts** — a read-only spectral analysis flags files that
  claim 320 kbps / lossless but were transcoded from a lossy source; verdicts
  demote a file's rank when picking duplicate keepers.
- **Doctor** — timestamped backups of the Rekordbox database with rotation,
  diagnostics, and application logs in one place.
- **French / English** UI.

## What it deliberately does NOT do

Syncbox contains **no downloading of any kind**. No stream ripping, no
provider credentials, no DRM circumvention — from Spotify it reads *metadata
only*. Missing tracks are handled lawfully: search links to stores
(Beatport, Bandcamp) and manual relinking to audio files you already own.
The only secret the app ever stores is your own Spotify OAuth token,
encrypted at rest.

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
2. The app is **not yet code-signed** (see roadmap), so on first launch macOS
   will say it "is damaged" or "cannot be verified". Either:
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
[docs/SPEC-UNIFIED.md](docs/SPEC-UNIFIED.md); [docs/](docs/README.md) indexes
the plans, design spec, and dated research behind every decision.

## Build from source

Prerequisites: [pnpm](https://pnpm.io), [Rust](https://rustup.rs),
[uv](https://docs.astral.sh/uv/) (Python 3.14).

```sh
pnpm install                 # workspace: ui + shell
cd sidecar && uv sync        # python venv + deps
cd ../shell && pnpm tauri build --bundles app
# → shell/src-tauri/target/release/bundle/macos/Syncbox.app
```

Dev loop and tests:

```sh
cd shell && pnpm tauri dev                       # app against the source tree
cd sidecar && .venv/bin/python -m pytest -q      # sidecar suite
cd ui && pnpm test && pnpm typecheck             # UI suite
cd shell/src-tauri && cargo check                # shell
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

Current release: **0.1.0** — macOS (Apple Silicon), unsigned.

- **Signing & notarization** — planned as soon as an Apple Developer ID
  exists; secrets then migrate from the encrypted store to the macOS
  Keychain.
- **Windows** — the OS seams are in place (process kill, WebView origin,
  path formats); implementation waits on a Windows host to run the
  validation harnesses.
- **Later** — in-app audio preview, fingerprint-based duplicate detection
  (Chromaprint), ISRC enrichment.

## License

[MIT](LICENSE). The packaged app bundles third-party components under their
own licenses — among them [mutagen](https://github.com/quodlibet/mutagen)
(GPL-2.0-or-later), whose source-availability terms this public repository
satisfies.
