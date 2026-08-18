# Syncbox

**Keep your Rekordbox collection clean, matched, and gig-ready — with guarded
writes and automatic backups.**

Current source version: **0.7.2**

Syncbox is a macOS desktop app for DJs who prepare sets with Spotify and
perform with [Rekordbox](https://rekordbox.com). It bridges the two: it reads
your Spotify playlists, matches them against your Rekordbox collection, writes
MyTags and smart playlists straight into Rekordbox, and keeps the collection
itself healthy — duplicates, missing files, untagged tracks, suspicious audio
quality — with guarded writes, automatic backups, and exact-payload
confirmation.

## What it does

- **Spotify → Rekordbox matching** — connect your own Spotify account
  (read-only API, PKCE, no password stored), follow playlists as sources, and
  let Syncbox match every track against your collection by ISRC first, fuzzy
  title/artist second. Review and apply the matches as MyTags in Rekordbox.
- **Events** — build a set for a gig from a Spotify playlist (or link). Each
  event becomes a MyTag + smart playlist inside Rekordbox. Tracks you do not
  own yet are listed as *missing* with purchase links first. An optional
  Deezer component can acquire an ISRC-resolved track after explicit setup;
  it is disabled by default and distributed separately from the base app.
  Events stay open after applying: add tracks later and re-apply just the
  delta — idempotent, never duplicated.
- **Performance history** — archives Rekordbox play history locally, groups
  plays into performances across restarts, keeps overlapping sessions
  separate, flags likely USB-import bursts, and shows a live tracklist while
  Rekordbox is running. Performances can be renamed or hidden. Export creates
  an ordered plain playlist under `Historiques` through the guarded Rekordbox
  write pipeline.
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
Syncbox write to Rekordbox goes through a single guarded pipeline:

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
6. **Ordinary library files are never moved or renamed.** The only v1
   exception is a retained event-staging track, which is migrated to
   `<storage root>/rekordbox/Collection/` before the event is removed.

## Install (macOS, Apple Silicon)

1. Download `Syncbox-0.7.2-macos-arm64.zip` from the
   [v0.7.2 GitHub Release](https://github.com/Adridot/syncbox/releases/tag/v0.7.2),
   then unzip it.
2. The current app is ad-hoc signed, not signed with an Apple Developer ID and
   not notarized. Launch it once. If macOS blocks an artifact you trust, open
   **System Settings → Privacy & Security**, select **Open Anyway**, then
   confirm **Open**. Apple documents this exception in
   [Open a Mac app from an unknown developer](https://support.apple.com/guide/mac-help/mh40616/mac).
3. Launch. The onboarding walks you through the three things it needs: your
   Rekordbox database (one click fills the default
   `~/Library/Pioneer/rekordbox/master.db`), a storage root, and — for
   Spotify features — a free Spotify developer client ID (guided, ~2 min).

Release validation and historical v1 evidence for lifecycle, reproducibility,
private Rekordbox fixtures, and disposable-copy manual checks are indexed in
[docs/POC-EVIDENCE.md](docs/POC-EVIDENCE.md). App data lives in
`~/Library/Application Support/Syncbox`; database backups live under
`<storage root>/_syncbox/backups`.

## Architecture

```
┌───────────────────────────  Syncbox.app  ───────────────────────────┐
│  shell/   Tauri v2 (Rust) — window, process supervisor, tray of     │
│           safety plumbing: single instance, bounded restarts,        │
│           tree-kill + shutdown handshake                             │
│  ui/      Vue 3 + TypeScript — screens, guarded mutations, i18n      │
│  sidecar/ Python 3.14 (Starlette) — all domain logic, served on      │
│           127.0.0.1:8766 (REST + SSE), packaged as a PyInstaller     │
│           onedir binary inside the app bundle. Spotify PKCE opens    │
│           127.0.0.1:8765/callback only for the active attempt.       │
└──────────────────────────────────────────────────────────────────────┘
             reads/writes master.db via pyrekordbox, guarded

 optional-component/  Separate pinned PyInstaller onedir download.
                      Deezer-only Syncbox interface; streamrip is never
                      imported or bundled by the base application.
```

The current product and architecture specification lives in
[docs/SPEC-UNIFIED.md](docs/SPEC-UNIFIED.md). Detailed operational and
historical material lives in the [user guide](docs/USER_GUIDE.md),
[distribution contract](docs/DISTRIBUTION.md), and
[POC evidence index](docs/POC-EVIDENCE.md).

## Build from source

Prerequisites: [pnpm](https://pnpm.io), [Rust](https://rustup.rs), and
[uv](https://docs.astral.sh/uv/). The build uses separate locked Python
projects: Python 3.14 for the base sidecar and Python 3.13 for the optional
component.

```sh
pnpm install --frozen-lockfile
(cd sidecar && uv sync --locked --managed-python)
pnpm --dir shell bundle:macos
# → shell/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Syncbox.app
```

Dev loop and tests:

```sh
pnpm --dir shell tauri dev                       # app against the source tree
(cd sidecar && uv run --locked pytest -q -rs)    # sidecar suite
pnpm --dir ui test                               # UI suite
pnpm --dir ui typecheck
mkdir -p sidecar/dist/syncbox-sidecar            # resource required by Tauri
cargo check --locked --manifest-path shell/src-tauri/Cargo.toml \
  --target aarch64-apple-darwin
```

Packaging regression harnesses (lifecycle, single-instance, supervisor,
frozen bundle) live in [shell/harness/](shell/harness/) — each file's
docstring says how to run it.

## Repository layout

| Path | What |
|---|---|
| `sidecar/` | Python sidecar — domain logic, HTTP+SSE API, Rekordbox writes |
| `optional-component/` | Separately distributed pinned Deezer/streamrip runner |
| `ui/` | Vue 3 front end |
| `shell/` | Tauri shell (Rust supervisor) + packaging harnesses |
| `docs/` | Specification, user guide, distribution contract, POC evidence index |
| `scripts/` | Release build, packaging, license generation, and fixture tooling |
| `release/` | License inventories and notice bundles shipped with the released apps |

## Status & roadmap

Current source and release version: **0.7.2**. This patch cleans up legacy
acquisition storage by trashing the complete migrated job directory instead of
its audio file alone, and adds a guarded, fill-only repair for legacy Syncbox
imports whose Rekordbox metadata was left blank.
The macOS 14+ Apple Silicon release workflow keeps the scanner, isolated-root
reproducibility, component-pin, and test gates. The app is ad-hoc signed
without a Developer ID or notarization.

- **Signing, notarization, and Keychain** — deferred; the v1 distribution uses
  a per-install encrypted SQLCipher secret store and never exports OAuth
  tokens.
- **Windows** — deferred to v2; the v1 build and validation contract is macOS
  Apple Silicon only.
- **Updates** — no in-app auto-update is implemented.
- **Optional acquisition** — purchase links remain first. Deezer acquisition
  is explicit, disabled by default, requires a Premium credential stored only
  in the encrypted secret store. Local archive installation is validated; the
  hash-pinned online component path uses the matching `v0.7.2` GitHub Release
  asset. SoundCloud and ffmpeg are not exposed.
- **Later** — local-library audio preview, fingerprint-based duplicate
  detection (Chromaprint), ISRC enrichment.

## License

[MIT](LICENSE). The packaged base app bundles third-party components under
their own licenses, including [mutagen](https://github.com/quodlibet/mutagen)
(GPL-2.0-or-later), MPL-2.0 dependencies, and the PyInstaller bootloader under
its GPL exception. The separately distributed component contains deezer-py
(GPL-3.0-or-later), mutagen, streamrip's exact GPL-3.0-only license, pinned
source revision, source-availability notice, and its own dependency inventory.
The generated base and optional consolidated notices are authoritative; this
summary is not a legal-compliance claim.
