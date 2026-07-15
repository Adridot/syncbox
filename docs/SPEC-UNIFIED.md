# Syncbox — Unified Specification (SPEC-UNIFIED)

> **Purpose.** Current product and architecture specification for Syncbox v1. It consolidates the historical functional spec ([SPEC-01-syncbox.md](SPEC-01-syncbox.md)), architecture review ([SPEC-02-architecture.md](SPEC-02-architecture.md)), owner decisions, completed POCs, and the release contract in PROMPT-05-implementation.md. The exact release evidence and material official sources are maintained in _handoffs/final-release-closure.md. These historical pipeline documents were removed from the working tree on 2026-07-15 and remain available in git history.
>
> **Source of truth.** For architecture and product behavior, **this document is authoritative**, subject to the later owner override in §3.0 and the release gates in PROMPT-05. SPEC-01 and SPEC-02 are historical evidence and motivation only. The current source, tests, POC reports, and final release handoff decide any implementation or evidence question.
>
> **Scope/value.** OVERHAUL-01-valeur-features.md (2026-06-16, archived in git history) is the **record of value and product-scope decisions** (feature audit, candidates, journal). Its **target v1 scope is folded in here** (§4 domain model, §5.11–§5.13 invariants, §6.5/§6.12 architecture, §7.4 journal, §8 POC), arbitrated by two additional gates (2026-06-16, see §0). **SPEC-UNIFIED remains the consolidated architecture+product source of truth**; OVERHAUL-01 is authoritative only on the *what/value*, and is corrected where §10 research disproved it (Chromaprint license, cues/ANLZ attribution). Its v1/v2 split is **refined by Gates 1/2 (2026-06-16)**: **§7.4 below is authoritative on v1 scope** (the pre-Gate-2 lists in OVERHAUL-01 §1/§6/§7.2/§8 are historical).
>
> **Language.** English. The product keeps parallel English and French user-facing locales.

---

## 0. Decision Status

| Block | Status |
|---|---|
| Project magnitude | **Decided** — rewrite *from scratch* |
| Forks A, B, C, D | **Resolved** (§7.1). Tauri and the separate streamrip component are validated for local macOS Apple Silicon artifacts. Developer ID signing and notarization are explicitly deferred; they are not v1 POC gates. |
| Questions §10.1–§10.8 | **Decided** (§7.2), sourced + verified (Phase 2 adversarial review) |
| Questions §10.9 (UI/UX) & §10.10 (configurable matching) | **Implemented and tested** (§9): six routed destinations, deep-linked Health/Missing views, guided onboarding, and bounded advanced matching settings |
| Decisions D1–D25 | **Integrated** (§7.3) |
| SPEC-01 §9 non-negotiables | **Preserved** (§3), with reframing of the test contract |
| Product scope (OVERHAUL-01, 2026-06-16) | **Integrated** (§4, §5.11–§5.13, §6.5, §6.12, §7.4, §8). macOS v1 includes A1 Smart Fixes, the conservative A3 spectral fallback, optional B1 Deezer/streamrip acquisition, and B2 legal Track Matcher. Full A3 classification is `NO-GO`: the fallback reports `ok` or `incertain` and never penalizes keeper selection. B1 returned `GO` on 2026-07-13 after a real full-track Deezer POC. A2/Chromaprint and SoundCloud/ffmpeg remain deferred to v2. |

---

## 1. Product Identity & Summary

Syncbox v1 is a **macOS 14+ Apple Silicon** desktop app with bundle identifier `io.github.adridot.syncbox`. Windows is deferred to v2 and Linux is out of scope. It maintains a DJ's **Rekordbox** collection, synchronizes read-only Spotify playlists, provides collection-health tools, keeps legal Beatport/Bandcamp purchase links primary, and can optionally run the separately distributed Deezer component after explicit enablement.

The guiding principle is safety: no `master.db` write while Rekordbox is running, a timestamped backup before every mutation, and reversible soft deletion. Ordinary library files are not moved. The sole v1 move is the explicit retained-event-track migration to `<storage_root>/rekordbox/Collection/` before event cleanup.

**Core value**: writing **in place** to `master.db` — MyTags + **smart playlists** (the “Event Imports” and the tagged library *are* Syncbox’s value). Without it, Syncbox would only be yet another Deezer downloader (see Fork A).

**What the rewrite fixes** vs the current app: paths hardcoded to the developer’s machine, double Spotify auth stack, double data layer + double settings store, fragile downloaded filename reconstruction, French-language cleanup heuristics, migrations that overwrite user edits. The **business core** (safety, ISRC/fuzzy matching, dedup, soft-delete, path resolution) is solid and is carried here as an **invariant contract** (§5).

---

## 2. Priorities & Drafting Principle

**Priorities, in order**: **(1) robustness/safety** (zero Rekordbox corruption) > **(2) light footprint** (small binary, low RAM, fast startup) > **(3) performance/responsiveness**, **with maintainability reintroduced as an equal guardrail** (explicit correction of SPEC-02, which set it aside). Concretely: a “chosen complexity” is retained only if it serves these axes **and** survives the question *“vs what already works, should this change happen?”*.

**Altitude principle (owner request).** This spec is **exhaustive on the WHAT** (invariants, domain model, non-negotiables, resolved forks, behavior contract) and **permissive on the HOW**: technical recommendations marked `reco` are **recommended, sourced defaults**, not mandates — the construction model remains free to choose better within the constraints. Only the **non-negotiables** (§3) and the **resolved forks** (§7.1) are binding.

**Minimal-design lens.** For each building block: (1) must it exist? (2) does the stdlib do it? (3) a native OS/platform feature? (4) an already installed dependency? (5) one line? (6) the minimum that works. Deliberate simplifications carry a `Minimal-design note` stating what is excluded and when to reconsider it.

---

## 3. Non-Negotiables (to respect no matter what)

### 3.0 — Syncbox v1 macOS owner override (2026-07-11)

This subsection is authoritative for Syncbox v1 and overrides conflicting text in sections 3–8.

- v1 targets macOS on Apple Silicon. Windows is deferred to v2, Linux remains out of scope, and v1 must not add unused Windows infrastructure.
- v1 is delivered without Developer ID signing or notarization. Apple Silicon executables retain the ad-hoc signatures required to run locally. Developer ID signing, notarization, stapling, auto-update, and Keychain integration are deferred. The encrypted local secret store remains the v1 storage path.
- The universal track-level `protected` rule is removed. File ownership is classified as `app_managed` (Syncbox working directories), `permanent_library` (`<storage_root>/rekordbox/`), or `external` (all other user-owned locations).
- Safety follows the operation: event deletion may remove app-managed event artifacts; `permanent_library` and `external` audio survive event deletion; duplicate resolution may operate on any ownership class after exact per-group confirmation; keeper selection is path-neutral; untagged removal remains a reversible Rekordbox soft-delete and never deletes audio; missing-file removal may soft-delete the Rekordbox row regardless of its former location; Smart Fixes do not filter by file location.
- When an event is deleted, an app-managed staging track with another active MyTag other than the event MyTag is migrated to `<storage_root>/rekordbox/Collection/` before event cleanup. This is the only intentional v1 file-move exception.
- Windows validation, Developer ID signing, notarization, and Chromaprint are deferred rather than failed POCs. The authoritative nine-item v1 POC index is maintained in `docs/POC-EVIDENCE.md`.
- B1 Deezer/streamrip acquisition is included in macOS v1 after the 2026-07-13 Phase 5 `GO`. It is optional, OFF by default, Deezer-only, subordinate to B2 purchase links, and installed as a separate pinned component after explicit enablement. Artwork support and Pillow exist only in this component. The base artifact must remain fully functional without any Deezer runtime and must not import or bundle streamrip at application boot.
- SoundCloud acquisition, ffmpeg bundling, AcoustID/MusicBrainz enrichment, automatic cues, beatgrid editing, a cloud backend, and a mobile app are deferred beyond v1.
- Ponytail remains an implementation discipline, not an annotation system. No new Ponytail rationale markers may be added, and executable source must have zero such markers at overall completion.

### 3.1 — Rekordbox Safety

Block **any** mutation if `rekordbox` **or** `rekordboxAgent` is running (strict detection, anti-false-positive, “friendly” message **without PID, without `/Applications/` path, without `--type=` flag**). Mutation unit of work: assert RB closed + DB exists → **timestamped backup** → open → mutate → commit + invalidate snapshot cache; rollback + close on exception. Deletions = **reversible soft-delete**. **Load-bearing status integers** (256 = active, 258 = deleted, `rb_data_status`/`rb_local_*`) to reproduce **identically** (Rekordbox 6/7 sync semantics), otherwise the user’s sync may be corrupted. Restore snapshots the current DB first (itself reversible). All reads filter soft-deleted rows. **Every bulk write (Smart Fixes, §5.11) uses this same `_mutate` unit of work — no escape hatch.** **ANLZ boundary:** ordinary mutations and manual missing-file relinks do not edit ANLZ payloads; manual relink therefore requires explicit consent because cues, beatgrid, and waveform may desynchronize outside the `master.db` backup. Retained-event-track migration is the sole v1 exception: it enumerates and backs up every affected ANLZ file, changes only the PPTH path tag, verifies the non-PPTH payload, and rolls back on failure. Its copied private fixture gate passes with zero skips and unchanged sources, and Rekordbox 7.2.16 passed the required reopen, playback, cue, beatgrid, analysis, MyTag, playlist, Smart Fix, path, and ANLZ PPTH checks on disposable copies.

### 3.2 — Path Resolution (load-bearing)

A file **under `<storage_root>/rekordbox/…`** is stored **volume-relative** (`/<VolumeName>/…`); **everything else** is stored as **absolute** — otherwise Rekordbox displays “file could not be found”. Volume-relative and absolute are treated as **equal and hash-equal** (see memory `rekordbox-path-resolution`).

### 3.3 — Exact-path access and the retained-track exception

Handle the macOS TCC cloud-folder quirk through exact-path `Path.exists()` checks without parent-directory enumeration. Do not move ordinary library files. A retained app-managed event track carrying another active MyTag is the only v1 exception and must be migrated to `<storage_root>/rekordbox/Collection/` before event cleanup.

### 3.4 — Required Dependencies

`pyrekordbox` plus the inventoried local `sqlcipher3-wheels` CommonCrypto build for `master.db` (**writes `master.db`, cannot generally write ANLZ** — bounds reversibility, see §3.1/§5.1); Spotify Web API **OAuth PKCE** (read-only); `mutagen` (tags); and `rapidfuzz` (similarity). B1 uses streamrip, deezer-py, and Pillow only in the separate optional component; the base app must not depend on any Deezer acquisition package.

**v1 additions (OVERHAUL-01 scope)**: `miniaudio` + direct `numpy` for the conservative, read-only A3 spectral diagnostic (§5.12); `urllib.parse` **stdlib** for B2 purchase links (§5.13, zero dependency and zero network on the app side); and Pillow 10.4.0 only in the optional component for artwork embedding. `fpcalc`/Chromaprint remains deferred to v2.

The owner accepted the inventoried non-permissive redistribution boundaries: mutagen GPL-2.0-or-later in the base; streamrip GPL-3.0-only and deezer-py GPL-3.0-or-later only in the optional component; the PyInstaller bootloader under GPL-2.0-or-later with its Bootloader exception; and the exact reviewed MPL-2.0 packages. Generated notices, exact versions, source locations, and license texts are mandatory in each artifact. Any additional unlisted copyleft dependency fails closed.

### 3.5 — Local-first

No cloud backend; all application state in **local SQLite**; settings in a folder that survives updates. **Outgoing HTTPS** calls (Spotify/Deezer) preserved → embedded **CA bundle (`certifi`)** remains non-negotiable (≠ “no inbound server”).

### 3.6 — Protected Secrets at Rest

Spotify OAuth tokens **never in plaintext** (incompatible with open source). See §6.7 (two documented paths). Deezer ARL follows the same rule when optional B1 is enabled; no acquisition library may serialize it to disk.

### 3.7 — macOS v1 boundary

The validated v1 target is macOS 14+ on Apple Silicon. Keep platform boundaries clean, but do not add Windows implementation or packaging before v2. In the base artifact, A3 (`miniaudio` + `cffi`) is the only v1 feature adding a new native runtime; B1/streamrip remains a separate optional component installed only after explicit enablement. A2/`fpcalc` remains outside v1.

### 3.8 — FR/EN i18n

Maintained (structured, parallel locales; see memory `i18n-fr-en`).

### 3.9 — Behavior Contract = Invariants, Not Test Code

Observable guarantees (safety, matching, dedup, path resolution, soft-delete, and status transitions) are the reference and are enumerated in **§5**. The implementation tests these invariants in `sidecar/tests/`, the UI tests, Rust tests, lifecycle harnesses, and private real-Rekordbox harnesses; no historical test layout constrains the architecture.

---

## 4. Domain Model (Reusable, Tech-Agnostic Foundation)

Entities that survive regardless of the technology (details SPEC-01 §6):

- **Library source** — Spotify playlist followed *permanently*. Attributes: `spotify_playlist_id` (identity), name, `snapshot_id` (change detection), `tags` (default MyTags), `enabled`, `status` (`pending → synced`). Historical runs.
- **Library track** — 1 row per (source, spotify_track_id). Statuses: `new → matched|conflict|ready|imported`, plus `missing`, `removed_from_source`, `ignored`, `acquisition_failed`. Carries the Rekordbox link, `match_method`, `confidence`, `staging_file_path`, tags. A `missing`/`acquisition_failed` status exposes derived **purchase links** (B2, §5.13) — not persisted, computed at display time.
- **Event** — temporary import (wedding, party). Attributes: name, slug, `default_tag` (= name, **“Situation”** category), `spotify_playlist_id` (or `manual:<slug>`), folders, `status` (`pending → applied|partially_applied`). Tracks (`matched/ambiguous/missing/ready/applied/ignored/acquisition_failed`) + staging files.
- **B1 acquisition job** — optional macOS v1 Deezer acquisition after the Phase 5 `GO`. It covers all three scopes in one table. The implemented job lifecycle is `queued → running → downloaded|relinked|relink_blocked|relink_failed|failed`; repeated same-state updates are idempotent and every other transition is rejected. A successful library or event download also moves the track row to `ready`; a failed one moves it to `acquisition_failed`. B2 purchase links remain primary and available when B1 is disabled or fails.
- **Smart Fixes job** (A1, v1) — bulk metadata cleanup (extract artist/remixer from title, casing, stray characters/URLs, encoding). Cycle **`dry-run` (exact preview, no write) → `confirm` → `mutate`**. Writes `master.db` via `_mutate` (§3.1/§5.11). Reuses the **single D19 normalization** (§5.3) — which in turn improves fuzzy matching accuracy.
- **Rekordbox track** (non-persistent snapshot) — `content_id`, title, artist, isrc, durationMs, filePath, fileType, bitRate/sampleRate/bitDepth/fileSize, bpm, rating, analysed, cueCount, playlistCount, tagCount, `ownership`, `fileMissing`, and dateCreated. Ownership is informational and does not affect keeper choice or filter Smart Fixes. The snapshot is cached on the `(mtime,size)` fingerprint of `master.db(+wal)`. The v1 A3 fallback exposes only non-persistent `ok` or `incertain`; `lossy_source_probable` remains reserved vocabulary and is never emitted by the conservative classifier.
- **MyTag** — Rekordbox tag system (categories → tags). “Situation” for events, “Genre” by default otherwise.
- **Duplicate group** — ≥2 identical (ISRC) or close (fuzzy) contents, with a *keeper*. Group identity = sorted set of contentIds. *(A2 dedup by audio fingerprint is deferred to v2; no integration is planned in v1 and the group key is unchanged.)*
- **Rekordbox backup** — timestamped folder under `_rekordbox_sync/backups/`, contains `master.db(+wal/shm)`. N rotation (default 15, 0 = unlimited).
- **Settings** — Spotify credentials, 4 paths, `backup_retention`, OAuth tokens (encrypted, §6.7), and the optional `deezer_acquisition_enabled` flag. The Deezer ARL is never a setting; it is stored only in encrypted secrets.

**Storage layout**: `<storage_root>/rekordbox/{Collection, Collection manuelle}` is `permanent_library`; only audio under the Syncbox `events` and `inbox` working directories is `app_managed`; every other location is `external`. The application database lives in the OS application-data directory (§6.9).

---

## 5. Behavior Contract — Invariants to Reproduce

> These are the business rules, invariants, and edge cases that **must survive** regardless of technology. SPEC-01 §3 preserves historical detail; the current source and executable tests are authoritative evidence.
>
> The **numeric constants** cited below (weights, buckets, thresholds) are the
> defaults carried over from SPEC-01 §3. Advanced Settings exposes the
> confidence threshold, ambiguity margin, weights, and guarded ISRC policy with
> bounded controls and reset-to-default behavior. ISRC-first ordering, D19
> normalization, and duration buckets remain locked invariants (§9).

**5.1 Rekordbox safety** — see §3.1. The mutation guard strictly re-filters the process (path contains `/rekordbox.app/`·`/rekordboxagent.app/` or ends with `/rekordbox`·`/rekordboxagent` on macOS; `rekordbox.exe`·`rekordboxAgent.exe` on Windows). `rekordboxAgent` survives window closure → always checked. Backup before mutation, N rotation, same-second collision → suffix. Restore validates name (rejects paths outside backups root), snapshots first, requires RB closed.

**5.2 Path resolution** — see §3.2. `path_lookup_keys` emits raw / volume-resolved / expanduser / `.resolve()` / volume-relative forms so an absolute staging path matches a volume-relative DB row.

**5.3 Spotify → Rekordbox matching.** Order: **exact ISRC first**, then fuzzy. ISRC uppercase → `confidence=100`, `status="matched"`. **ISRC collision guard**: an ISRC match is rejected **only if** `|duration Δ| > 15000 ms` **AND** title similarity `< 82` (missing duration = blind trust in ISRC). Fuzzy: `confidence = title*0.52 + artist*0.36 + duration*0.12`, default threshold **82**; below → `missing`. **Ambiguity**: if `(best − second) < 6` → `ambiguous` (still returns the best `content_id`). Duration buckets: ≤1500 ms→100, ≤5000→80, ≤12000→55, otherwise 0. Normalization: NFKD→ASCII, lowercase, parentheses/brackets removed, `&`→`and`, `fuzz.token_sort_ratio`. **D19: a single shared normalization pipeline** for matching/dedup (fixes the two currently divergent normalizations).

**5.4 Duplicates & keeper.** ISRC: bucket by strip+upper ISRC. All-ISRC + coherent titles → **99**; all-ISRC + divergent titles → **60 + warning** (excluded from bulk). Fuzzy: threshold 0.87, duration tolerance 2000 ms (rises to 0.93 if duration unknown); signature = `artist_norm + " " + title_norm`; **fuzzy group → confidence 80** (SPEC-01 canonical, `dedup.py`), eligible for bulk via D5 (per-group confirmation) like ISRC groups. Group key = sorted set of contentIds. **“Not a duplicate”** persisted (idempotent dismiss).
- **D5**: **suggested** keeper but **confirmation per group**; **remove 1-click bulk auto-resolve**.
- **D6**: use an explicit ordered keeper scale with a displayed reason. Criteria are, in order: (1) present file over `fileMissing`; (2) discrete bitrate bucket; (3) stable creation-date and content-ID tie-breaks. Ownership never affects keeper priority. The conservative v1 A3 fallback emits no penalizing verdict, so both `ok` and `incertain` are keeper-neutral.
- **File safety**: never delete the keeper; **order** = relink memberships → soft-delete losers (in the txn) → file deletion **only AFTER successful commit** (see §6.9 trash). Relink reassigns playlists+MyTags from loser to keeper.
- **UX safety (fixes B10)**: the confirmation text for a destructive action reflects **exactly** the executed payload (never the opposite of the action).
- **A3 × keeper (D6)**: the full penalizing classifier is `NO-GO` for v1 because a spectral cutoff alone cannot distinguish a transcode from a legitimate band-limited master. The retained fallback reports only `ok` or `incertain`; both are neutral and bitrate remains the active D6 quality criterion. The dormant `lossy_source_probable` ordering hook is tested but receives no v1 classifier output.

**5.5 Acquisition.** The optional runner resolves one normalized ISRC to a numeric Deezer track ID and reports the real `track.download_path`; it does not implement metadata search or an ambiguity threshold. The job lifecycle is the bounded transition set in §4. Every output must be a regular file inside its per-job directory. Library and event downloads become `ready` staged rows that the existing guarded apply flow imports; failures become `acquisition_failed` and retain B2 links. Collection downloads remain in the acquisition directory and are offered by manual relink discovery. An immediate collection relink is attempted only when explicitly requested, uses the normal Rekordbox-running guard and ANLZ consent, and retains the output on `relink_blocked` or `relink_failed`.
- **D18**: use only the downloader's real output path; never reconstruct a filename.
- **Engine (B1, §6.5)**: **streamrip** is installed only as a separate optional component (git pin **v2.2.0** + exact commit), then invoked via a short-lived JSON runner. The base sidecar never imports streamrip. The runner reads the **real output path** from `track.download_path` (D18), carries ARL + folder per job, deletes the one-shot ARL file, and never writes `config.toml`. **v1 = Deezer only** (direct-served FLAC/MP3, **no ffmpeg**); SoundCloud → v2/B4 (HLS, requires ffmpeg).
- **D20**: **never** use the `barcode` tag as ISRC (absent → `None`) (fixes B6).
- **Concurrency (fixes F2/F3)**: download→track correlation by **explicit identity** (resolved `track_id`), **never by list index**; **no shared mutable acquisition state** between concurrent jobs — ARL and `downloadPath` carried by **job/request**, not in process global.
- **Real progress (fixes F16)**: displayed progress derives from the **job SSE stream**, never from tone/status.

**5.6 Library sync.** Diffing by track: duplicate Spotify in a playlist → `ignored`; `ignored`/`ready` carried over unchanged; `imported`/`matched` reconciled; fresh match → `matched`/`conflict` (if ambiguous)/`new`; absent from playlist → `removed_from_source`. Default tags inherited from `source.tags`. Spotify snapshot (`snapshot_id`) detects changes. Apply: only `matched`/`ready` imported/tagged (otherwise 409); **library MyTags must pre-exist**. Removing a source = stop following only (RB tracks + MyTags preserved). **D9**: remove legacy `tag_rules` table (cause of B4); concept preserved via `source.tags`.

**5.7 Events.** 3 modes (from playlist / empty / by link). Unique atomic folder (`mkdir(exist_ok=False)`, slug collision → `-2`…). `default_tag` = event name (“Situation” category). Event matching: `ambiguous`→`ambiguous` (not `conflict`), no default tags. Staging/claim: one file shared only between two tracks with the **same non-empty ISRC**. Apply: creates/repairs a **smart playlist** under “Event Imports”, restores the XML after commit. **Smart playlist**: `SmartList = "<playlistId>:<tagId>"` (operator 8 = contains); IDs > 2³¹ converted to **signed 32-bit** — **load-bearing**. RB write: new rows with **string ID** (mixed int+string PKs crash SQLAlchemy on flush); self-heal of a soft-deleted artist. Delete preview read **inside** the mutation session. **D10**: remove Live Import M3U8 (UI + `live_import.py` + route); always require RB closed and write the collection directly (eliminates B12). **D11/D23**: delete event **always with exact preview** + **guarded on `mutationAllowed`** like apply (fixes B11). **Cleanup (fixes T8/T12)**: event deletion removes its **disk artifacts** (staging folder, audio, `.xml.bak` snapshots) — no orphans.

**5.8 Untagged & Missing Files.** Untagged: 4 sorted categories **junk < dup_of_tagged < alt_version < review**. **D7**: replace personal-language junk patterns with **universal structural rules** (`spotify:track:` stub, empty title, `rekordbox` artist) **+ user-configurable patterns**; fix B5 (1-token artist, `song_key` must keep the full artist) and B7 (greedy `feat.` regex). **D15 owner override**: `delete_untagged` is ownership-neutral, performs only a reversible Rekordbox soft-delete, and never deletes audio. Missing Files: re-download (collection job) / re-link (ISRC score→100 then title/name ≥70, cap candidates, **bounded `rglob`** — fixes F11) / remove (soft-delete); re-link preserves cues/tags/playlists (cues in `master.db`; ANLZ limit §3.1).

**5.9 Spotify (auth and reads).** **D3: PKCE OAuth only** (S256), with the read-only `playlist-read-private` and `playlist-read-collaborative` scopes. No app-only mode, client secret, username flow, or Basic-auth branch exists. Refresh preserves the stored `refresh_token` when Spotify omits a replacement. Retry is bounded to four attempts: 429 waits `Retry-After + attempt`; 401 forces one refresh only on the first attempt; 204 returns `{}`; errors preserve the upstream status. A private or inaccessible playlist returns an actionable connection message. **Callback:** see §6.10; the exact `127.0.0.1:8765` listener is temporary, while API/SSE remains on 8766. No deprecated audio-features or recommendations endpoint is required. Playlist access remains a monitored platform risk, not a claim of permanent Spotify availability.

**5.10 Settings, persistence, and backup/restore.** Settings are persisted in SQLite and are **never re-saved at startup**; defaults are applied when reading so stored credentials cannot be blanked. **Blank protection:** a credential update with an empty value preserves the stored value. Rekordbox and storage paths are validated. Settings JSON exports and all-data SQLite exports **exclude OAuth tokens entirely**; encryption at rest does not make a readable export safe. All-data export uses `VACUUM INTO` for one coherent file, and import validates and migrates a staged copy before atomic replacement while preserving a safety backup of the current database. The UI reads one canonical settings store.
- **Doctor (F9, KEEP v1)**: diagnostics center exposing the **list / restore / N rotation of backups** (§4, §5.1) and access to **logs**. The mechanics live here (§5.1/§5.10); the implemented UI surface is the Backups tab in the Collection Health hub (§9). No collection analysis (orphans/never-played) in v1 — deferred to v2 (§7.4).

**Decided cross-cutting bug fixes** (D14–D25, already integrated above or below): **D16** bulk tags as **delta add/remove** (never overwrite by union, fixes B3); **D17** distinct “applied with warnings” state (not red/error, fixes B8); **D22** restore `unignore` restores the **previous status** (not `new`, fixes B9); **D24** no auto-update (consistent with memory `no-auto-build-release`); **D25** remove dead tables/fields (`event_playlists`, `ProposalType.*_to_spotify`, unused tones); **D21** global reversibility preserved (soft-delete + backups + restore), **extended** to file trash (§6.9).

---

### Invariants of v1 Additions (OVERHAUL-01 scope)

> Same rules as above: observable behavior to reproduce, covered by new tests. Constants/thresholds to **calibrate in POC** (§8), not frozen here. Each addition carries a `Minimal-design note`.

**5.11 Smart Fixes (A1).** Use the strict `dry-run → confirm → mutate` cycle. Dry-run reads the cached snapshot without opening `master.db` for writing and remains available while Rekordbox is open. Execution revalidates the complete payload and the snapshot fingerprint, then uses the shared `_mutate` unit of work for the Rekordbox-running guard, timestamped backup, commit, cache invalidation, and rollback. Rules compose in a fixed order, omit no-ops, and reach a fixpoint. File ownership never filters metadata fixes. The exact preview and backup are the safeguards against overwriting user edits. The catalog remains fixed in v1; do not add a user rule engine.

**5.12 Fake-320 / fake-FLAC detection (A3) — conservative spectral fallback, read-only.** Full source classification is `NO-GO` for v1: the measured cutoff cannot safely distinguish a lossy transcode from a legitimate band-limited master, so the implementation never emits `lossy_source_probable`. It decodes PCM through `miniaudio` on the exact resolved path after `Path.exists()`/`stat`, never enumerates the parent, never moves or copies a file, never enters `_mutate`, and performs no network call. Direct `numpy.fft` computes a Hann-windowed average spectrum over at most 60 one-second frames. The calibrated full-spectrum boundaries are 19.8 kHz for lossy containers and 20.8 kHz for lossless containers: at or above the relevant boundary the verdict is `ok`; every lower cutoff is `incertain`, never an accusation or keeper penalty. Unknown decoded containers, missing files, silence/short files, undecodable AAC/m4a/opus, I/O failures, and cloud-read failures degrade to neutral `ok` without an exception. The cutoff and verdict are not persisted. `ok` and `incertain` are equivalent for D6; bitrate remains the active quality criterion. The three-label UI vocabulary retains `lossy_source_probable` only as a dormant future-compatible value. No ffmpeg, ML model, AcoustID, or network enrichment is included. Reopening a penalizing classifier requires new evidence that resolves band-limited-master false positives and a new owner decision.

**5.13 Legal Track Matcher (B2) — purchase links, pure read/display.** Consumes the already computed missing list (statuses `missing`/`acquisition_failed` only — `removed_from_source` excluded, §4); **writes nothing** (no `_mutate` txn, no backup required). Builds **deep search URLs** to **Beatport** and **Bandcamp** by **pure templating** (`urllib.parse.quote`, stdlib) from `artist+title` **normalized via D19/§5.3** (no ad-hoc normalization). **No network call from the app**: the user’s browser opens the URL → **§3.5/certifi not involved, §3.6/secrets not involved**. **Explicit ban** on any fetch/scraping/URL resolution on sidecar side (would reactivate §3.5 and run into Beatport anti-bot 403). **FIXED catalog** (build constant, **not a §4 model entity**): literal list `{name, template_url}` (Beatport, Bandcamp) — **no user editor** in v1, **no network probe** (consistent with §3.5: the app contacts no store). Two failure modes, **both boundary-safe** (B2 = pure read, never corruption): (a) **store disappears** ⇒ **remove its entry** in the next build ⇒ button **absent** (*Juno Download closed on 2026-06-01*); (b) **URL format stale but store alive** ⇒ URL lands at worst on a generic page. Maintaining the catalog = **edit the build list**, not the code. Button labels in parallel `en.ts`/`fr.ts` (§3.8). Template robustness validated in POC #7 (§8). *(Minimal-design note: stdlib is enough (~5 lines); **fixed 2-store catalog, no user editor in v1** — adding a store = adding an entry if a DJ asks for it; no Beatport v4 API (de facto closed portal) and no third-party aggregator; **iTunes Search API upgrade = out of v1 / v2 only** (would reactivate §3.5, non-negotiable network re-validation required), marked “AAC 256k” if exact price+link is ever required. **In v1, B2 makes STRICTLY no network call.**)*

---

## 6. Target Architecture (Decided)

Optimized for safety first, then footprint and responsiveness, with maintainability as a guardrail. The v1 runtime and release target is macOS 14+ on Apple Silicon; Windows remains a v2 concern. Material current sources are recorded in the phase and final-release handoffs.

### 6.1 Overview

```
┌──────────────────────────────────────────────────────────────┐
│  SHELL: Tauri v2 (Rust, native WKWebView on macOS)            │   Fork B
│   • hosts the web UI (Vue 3)                                  │
│   • spawns + SUPERVISES the Python sidecar (bounded restart,  │
│     tree-kill, single-instance)                               │
│   • signs the sidecar binary (POC #1, macOS)                  │
└───────────────┬───────────────────────────┬──────────────────┘
                │ HTTP REST + SSE            │ spawn + lifecycle
                │ (127.0.0.1, loopback)      │ (clean shutdown → tree-kill)
                ▼                            ▼
   ┌────────────────────────┐   ┌────────────────────────────────────┐
   │ UI: Vue 3 (retained)   │   │ Python SIDECAR (minimal HTTP+SSE)   │   Fork C
   │  • ONE reactive cache  │   │  • Starlette + sse-starlette        │
   │    layer (converged)   │   │    (NOT FastAPI/Pydantic v2)        │
   │  • 1 canonical jobs    │   │  • pyrekordbox → master.db (MIT)    │   Fork A
   │    SSE stream          │   │  • SQLite app + user_ver migrations │
   │  • FR/EN i18n          │   │  • Spotify OAuth PKCE (fixed port)  │
   └────────────────────────┘   │  • [opt., default OFF] Deezer       │   Fork D
                                  │    acquisition (pinned, isolated lib)│
                                  └────────────────────────────────────┘
   Safety (non-negotiable): “RB closed” guard, backup before mutation,
   soft-delete, OS trash (fallback §6.9), path resolution.
```

**What changes vs the current app**: Electron→**Tauri** (shell ~3–10 MB vs 100–150 MB); FastAPI/uvicorn→minimal **Starlette+sse-starlette**; external Deemix process→**optional embedded lib**; double data layer→**one only**; double settings store→**one source**; filename reconstruction→**real path**; ad-hoc migrations→**versioned**; plaintext tokens→**encrypted**.
**What does not change**: Python + pyrekordbox for Rekordbox; Vue UI; **localhost HTTP + SSE**; the safety backbone; the domain model.

> Minimal-design note: final size is **dominated by the Python sidecar** (non-excludable numpy + sqlcipher3 ≈ 95–120 MB), not by the shell. Tauri’s shell gain (~140 MB) is real but secondary; the **real size lever** is the sidecar (measure POC #2). Do not oversell the “−140 MB”.
>
> Minimal-design note: **v1 additions budget**: A1 Smart Fixes and B2 Track Matcher = **0 MB** (pyrekordbox/stdlib already there); A3 fake-320 = **~2-3 MB** (`miniaudio`+`cffi`+`pycparser`; numpy FFT is free); **A2 fingerprint dedup = 0 MB in v1 because deferred** (otherwise `fpcalc` +~1.8-2.6 MB **LGPL 2.1** to notarize). We deliberately avoid heavy bars: **bundled ffmpeg** (+40-80 MB, rejected → SoundCloud in v2) and ML (rejected). Uncompressed measurement to confirm in POC #2.

### 6.2 Shell — Tauri v2 (Fork B)

Tauri v2 (MIT/Apache-2.0) is the validated v1 shell. It packages the frozen sidecar as an application resource and serves SSE over loopback HTTP in WKWebView, never through the `tauri://` custom protocol. Source, frozen, embedded, packaged, and public-download lifecycle tests pass on 0.2.2, including the split 8766 API/SSE and temporary 8765 OAuth callback ports. The packaged WKWebView walkthrough and SSE behavior also pass. Electron is not an active fallback.

The v1 distribution contract uses ad-hoc signing only. Developer ID signing, hardened-runtime entitlements, notarization, stapling, and any post-bundle signing pipeline are deferred to v2 and are not implemented or claimed by the current build.

### 6.3 Python Sidecar & HTTP+SSE Transport (Fork C)

`reco` **Starlette + `sse-starlette`**, served by **uvicorn 1 worker launched programmatically in the main asyncio loop**. We **keep localhost HTTP REST + SSE** (decided decision) and **reject JSON-RPC stdio**. We **remove FastAPI/Pydantic v2** (documented cause of cold start; uvicorn multi-worker bug under PyInstaller is avoided with 1 worker).

**Transport requirements.** The permanent API/SSE server binds only `127.0.0.1:8766` and restricts origins to the loopback regex `http://(127.0.0.1|localhost):\d+` plus the measured Tauri origins, with `allow_credentials=False`. The OAuth callback is not exposed by that server; §6.10 owns a separate temporary `127.0.0.1:8765` listener. SSE generators must close cleanly under a bounded graceful timeout.

**Transport conditions.** Launch uvicorn **in the main asyncio loop** so `sse-starlette` shutdown remains correct. Use a single reactive UI cache layer and one **canonical jobs SSE stream**.

> Minimal-design note: Starlette is sufficient for the loopback routes and one SSE stream. The v1 POC covers PyInstaller cold start and EventSource in the packaged macOS WKWebView. WebView2 validation belongs to deferred Windows v2.

### 6.4 Rekordbox Write (Fork A)

**Write `master.db` in place, without XML mode.** (SPEC-02’s “A2” label was ambiguous and is abandoned.) MyTags, smart playlists, and in-place update are preserved. Safety relies entirely on the §3.1/§5.1 backbone. pyrekordbox is the current mature implementation path; Rekordbox's SQLCipher key is a public constant, not an access-control secret.

> Minimal-design note: no optional “XML export” mode (XML carries neither MyTags nor smart playlists, RB import is additive/buggy — it would amputate the product core). Add only if a non-destructive “bridge” use case emerges.

### 6.5 Acquisition — B2 primary, optional B1 in macOS v1

**Current macOS v1 default path:** **Legal path (B2, default, §5.13)** — Track Matcher: lists missing tracks + **purchase links** Beatport/Bandcamp (search URLs, **stdlib, zero network on app side**). Highlighted as ToS-clean alternative. The UI exposes a single purchase action per missing track; when several providers are available, that action opens the provider choices.

**Optional B1 path:** Phase 5 returned `GO` on 2026-07-13 after a real full-track Deezer POC with a local one-shot Premium ARL. B1 is included for macOS v1 only as an optional, Deezer-only module that is OFF by default and requires explicit enablement plus ARL entry. It is never on the critical `master.db` write path; collection relink failures retain the downloaded file and surface a blocked state instead of deleting the output.
   - **GPL confinement — hard, testable clause**: streamrip is **GPL-3.0-only**. The base sidecar **NEVER imports streamrip at boot** and the base distribution artifact must not include streamrip or deemix-fork code. streamrip is installed as a separate, pinned optional component after explicit enablement and is invoked through a short-lived subprocess runner with JSON output. The base distributed app remains functional without the component; only the optional component loads GPL code after activation. Same rule for deemix-fork if ever used as a fallback.

**Acquisition library = streamrip, Deezer-only.** The exact upstream source and commit are recorded in the component inventory and Phase 5 handoff.
- **streamrip component**: pin git **v2.2.0** at exact commit `189acda489927719aa8591f6acdd7d67aecf929b` — **NOT PyPI 2.1.0**. The dedicated runner uses the proven API path `Config.defaults()` per job → `client.login()` → `PendingSingle.resolve()` → `track.rip()` → **`track.download_path`** (D18 without filename reconstruction). `Config` per job ⇒ **zero global state** (fixes F2/F3). ARL is passed through an encrypted secret to a one-shot `0600` temp file consumed by the runner, then cleared from memory as soon as practical. **Hard TLS clause (testable, mirror §3.6)**: certifi is pinned and TLS verification must remain enabled.
- **Artwork**: Pillow 10.4.0 is pinned to its official CPython 3.13 macOS arm64 wheel and packaged only with the optional component. The component enables streamrip artwork handling and verifies that cover art is embedded in the resulting audio metadata. A real one-shot-credential rerun passed in the source, exact frozen component, installed-component, and packaged-host lanes; each lane verified the embedded JPEG through Mutagen and Pillow.
- **Generic streamrip CLI remains excluded**: Syncbox does not call the human CLI output. It calls the dedicated JSON runner so the real output path comes from streamrip internals instead of reconstructed filenames.
- **deemix-fork (vietsman) = documented fallback only if streamrip breaks later**: no v1 implementation unless streamrip becomes unmaintainable or fails a future bump POC. **Dominant risk**: the streamrip internal API is fragile to upgrades → **strict commit pin + integration tests surviving a bump** (maintainability guardrail §2).

**SoundCloud → v2/B4**: it serves HLS MP3 and **requires external ffmpeg** (+40-80 MB/platform, cross-OS packaging §3.7), which would almost double the sidecar (§2 lightness). Deezer (direct-served FLAC/MP3) **does not require ffmpeg** → v1 stays light. SoundCloud should ideally return as a **downloadable plugin outside the base sidecar**.

**Validated gate (POC #5).** The Phase 5 rerun proved a full-track Deezer download on macOS Apple Silicon with a real Premium ARL. The final-artifact rerun resolved ISRC `USQX91300105` to Deezer track id `67238732`, matched the `337 s` catalogue duration with a measured duration of `337.56 s`, used the real `track.download_path`, produced a `13,540,687`-byte MP3, and verified an embedded 500x500 JPEG cover in every source/frozen/installed/Tauri-host lane before cleanup. The byte-identical public optional asset then passed scanner and packaged installation/runtime checks. B1 downloads by numeric Deezer ID resolved from ISRC, never by short URL (#865). The base contains no streamrip distribution, Deezer runtime, Pillow, or real ARL.

### 6.6 Lifecycle & Supervision (§10.8)

`reco` **homegrown supervisor in the Tauri process**: loop on sidecar exit events (Shell plugin + `async_runtime`), **bounded restart** (~N=3, backoff 1/2/4 s), then emit a **`backend-down`** event to the UI (fixes F13/F14: counter exhaustion **is** the “backend unavailable” signal). Manual “Restart” button after exhaustion. **Anti-double-instance** via the official single-instance plugin.

**Lifecycle requirements.** Tree termination remains critical: killing only the PyInstaller bootstrap can orphan the worker and its permanent port 8766. The shell uses the macOS process group, a graceful `/shutdown` handshake, then bounded TERM/KILL fallbacks. Intent is an internal flag, never inferred from an exit code. Child output is always consumed. Shutdown must release permanent port 8766 and any active temporary callback on 8765; single-instance callbacks never spawn a second sidecar.

### 6.7 Secrets at Rest (§10.4)

The owner selected the unsigned-v1 path: a dedicated SQLCipher secret store built against Apple CommonCrypto. Spotify access and refresh tokens and the optional Deezer ARL use this encrypted store. Its separate key file is created with mode `0600`; blank credential updates preserve existing encrypted values. Secrets never appear in settings JSON, SQLite exports, logs, screenshots, fixtures, command-line arguments, or streamrip `config.toml`. The ARL is exposed to the optional runner only through a one-shot `0600` file that is deleted after use. The application data directory remains `~/Library/Application Support/Syncbox`, so the bundle-identifier change does not relocate the store. Keychain integration remains deferred with Developer ID signing and notarization.

### 6.8 Schema Migrations (§10.5)

`reco` native **`PRAGMA user_version` + ordered SQL scripts** (`0001_*.sql`…) applied via stdlib `sqlite3`, **zero dependency**. Each migration in an **explicit transaction** (`BEGIN`/`COMMIT` driven — **never** `executescript` combined with `autocommit=False`). **The seed becomes migration `0001`** → mechanically removes re-seeding at every boot (fixes **B4**). Replaces the current application table `schema_migrations` with the native slot.

> Minimal-design note: ~18 tables, single user, local-first → yoyo/Alembic do not justify their dependency and packaging cost. There is no rollback/downgrade path; the timestamped backup is the safety net. The migrated application database is separate from the encrypted secret store and from `master.db`.

### 6.9 Multi-OS Abstraction (§10.6, D2, D12)

`reco` **`psutil`** (already bundled via pyrekordbox) for RB process detection + **`send2trash`** for trash + **stdlib** (`os`/`pathlib`/`sys`) for paths. RB detection: reimplement the **strict §5.1 filter** on top of `psutil` (catch `NoSuchProcess`/`AccessDenied`/`ZombieProcess`), not pyrekordbox’s lax function. System paths: app data folder `~/Library/Application Support/Syncbox` (macOS) vs `%APPDATA%/Syncbox` (Windows); Rekordbox DB location per OS; volume resolution (`/Volumes` macOS vs Windows letters) for the volume-relative/absolute rule.

**File deletion — owner decision (sourced, send2trash #80/#2).** On **cloud folders (Dropbox) and exFAT**, OS trash fails (~50% `OSError`) or deletes permanently. **Selected behavior: try OS trash; on failure, permanent deletion — preceded by a UI WARNING requiring prior EXPLICIT CONSENT** (audio will be irreversibly lost on this volume). No after-the-fact notification: consent is requested **before** unlink. The **DB always remains reversible** (backup + soft-delete); only **audio** is irreversibly lost on these volumes. File deletion **only after successful commit** (§5.4).

> Minimal-design note: no Tauri trash plugin (Rust crate on shell side → breaks the Python sidecar “delete-after-commit” ordering); no application `.trash` (moving a file on cloud can also fail TCC **and** contradicts “never move files”). Add application trash **only** if a multi-volume **non-cloud** use case emerges where `send2trash` fails **and** intra-volume move is safe (TCC OK). POC: exact `master.db` path formats on Windows (letter/UNC/Pioneer volume-relative).

### 6.10 Spotify OAuth Callback (§10.7)

Register exactly `http://127.0.0.1:8765/callback` in the Spotify dashboard. Authorization Code with PKCE S256 is the only flow and never uses a client secret. The authorize and token requests both use the same hard-coded redirect URI; neither Host nor any incoming header may derive it.

The long-lived API/SSE server stays on `127.0.0.1:8766`. Starting authorization synchronously pre-binds an access-log-free Starlette/Uvicorn listener on `127.0.0.1:8765` before the URL is returned. A forged or missing state is rejected without cancelling the valid attempt. Success, correct-state denial, another terminal error, timeout, explicit disconnect, or process shutdown closes the listener and releases 8765. A foreign listener on 8765 causes only an actionable authorization error; Syncbox never probes, stops, or replaces it, and the permanent API remains healthy.

The callback port never rotates because Spotify requires the registered URI to match exactly. Re-authorizing renews state, verifier, and timeout while reusing an already active callback listener. Callback query strings are never access-logged, and every callback response is `no-store`.

### 6.11 Sidecar Packaging

`reco` **PyInstaller `--onedir`** (not `--onefile`: re-extraction at each startup → slow cold start, and unstable extraction path harmful to secrets). **Empirically measure** (POC #2) size + cold start on the real venv (numpy + sqlcipher3 + pyrekordbox + downloader); **Nuitka** only if measurement shows a decisive gain. `sqlcipher3-wheels` is built from the inventoried local source fork against Apple CommonCrypto; the distributed app requires no external compiler or crypto library. **Single-source** application version (one canonical source injected at build — closes T13 skew).

> Minimal-design note: Nuitka remains unnecessary after measurement. PyInstaller `onedir` is the validated path, with deterministic packaging around its output. The stable bundle resource path supports the CommonCrypto secret store. PyOxidizer and packager replacement are out of scope.

### 6.12 Advanced Hygiene — Place of v1 Additions A1/A3/B2 (B1 acquisition/sourcing is handled in §6.5)

Three v1 additions live **in the Python sidecar**, without a new shell or service. Placement and isolation:
- **A1 Smart Fixes (§5.11)** — business module on **pyrekordbox** (already there). Bulk write **only** through the `_mutate` unit of work (§3.1); no new dependency. filter→dry-run→confirm→mutate pattern (ref. `rekordbox-bulk-edit`).
- **A3 fake-320/FLAC (§5.12)** — **read-only conservative diagnostic** module: `miniaudio` decodes PCM and direct `numpy.fft` computes rolloff. It never enters `_mutate`. Full classification is `NO-GO`; the v1 fallback emits only keeper-neutral `ok` or `incertain`.
- **B2 Legal Track Matcher (§5.13)** — pure **stdlib URL builder** (`urllib.parse`), with no app-side network call, dependency, or secret. The UI exposes purchase buttons for missing tracks.
- **A2 fingerprint dedup — deferred to v2**: any future `fpcalc` integration first requires a measured residual missed by ISRC+fuzzy and a complete native-binary distribution review.

> Minimal-design note: none of these additions introduces a shell, inbound network service, or generic rule engine. A1/B2 = 0 MB; A3 = ~2-3 MB (miniaudio, not ffmpeg); **A2 = 0 MB (deferred to v2 — no integration planned in v1)**.

---

## 7. Consolidated Decision Journal (Traceable)

### 7.1 Forks A–D — Decided, Single Wording

| Fork | Decision (single, unambiguous) | Status | Ref. |
|---|---|---|---|
| **A — RB write** | **`master.db` in place, without XML mode** (the former double-meaning “A2” is abandoned) | **Decided** | §6.4 |
| **B — Shell** | **Tauri v2** for macOS Apple Silicon; Electron is not an active fallback | **Validated locally**; Developer ID/notarization deferred | §6.2 |
| **C — Transport** | **Keep localhost HTTP + SSE** (Starlette+sse-starlette, uvicorn 1 worker); **reject JSON-RPC stdio** | **Decided** | §6.3 |
| **D — Acquisition** | **Optional module, OFF by default**, with B2 purchase links kept primary. streamrip is a separately distributed component pinned to v2.2.0 and an exact commit; the Syncbox interface is Deezer-only. Deemix remains a documented fallback only; SoundCloud and ffmpeg are deferred beyond v1. | **Resolved** (full-track, artwork, packaged-boundary, notice, publication, and public download-back gates pass) | §6.5 |

### 7.2 Answers to the 10 §10 Questions

| § | Question | Decided answer |
|---|---|---|
| 10.1 | Target stack | Tauri v2 + Vue UI + Python sidecar (Starlette HTTP+SSE) + pyrekordbox. §6 |
| 10.2 | Deezer acquisition | Optional module, **OFF by default**; streamrip is a separate self-contained component pinned to v2.2.0 and the exact commit. Full-track, source/frozen/installed/packaged artwork, lifecycle, base-exclusion, license, controlled local archive/scanner, exact two-root equality, publication, and public download-back gates pass. §6.5 |
| 10.3 | Data layer / source of truth | **Convergence**: one UI cache layer + one canonical SSE stream + one settings store. §6.3, §5.10 |
| 10.4 | Secrets at rest | Owner-selected SQLCipher store using Apple CommonCrypto for unsigned v1; Keychain deferred. §6.7 |
| 10.5 | Schema migration | `PRAGMA user_version` + stdlib SQL scripts; seed = migration 0001. §6.8 |
| 10.6 | Multi-OS abstraction | `psutil` (process) + `send2trash` (trash, deletion+warning fallback) + stdlib (paths). §6.9 |
| 10.7 | OAuth callback | Exact temporary `127.0.0.1:8765/callback`, hard-coded redirect URI, PKCE; permanent API/SSE on 8766. §6.10 |
| 10.8 | Robustness / supervision | Homegrown Tauri supervisor (bounded restart + `backend-down`), critical tree-kill, single-instance. §6.6 |
| 10.9 | UI/UX | **Implemented and tested**: six hash-routed destinations, deep-linked Health/Missing views, dashboard-first fallback, five Health tabs, and ten-step onboarding. §9 |
| 10.10 | Configurable matching | **Implemented and tested**: bounded threshold, ambiguity-margin, weight, and ISRC-policy controls with reset; ISRC-first ordering, D19 normalization, and duration buckets stay locked. §9 |

### 7.3 Decisions D1–D25 — Integration

| # | Status | Integrated in |
|---|---|---|
| D1 open-source / remove personal paths | CHANGE | §1, §2 (configurable, secrets hygiene) |
| D2 macOS+Windows | CHANGE | §6.9 |
| D3 Spotify PKCE only | SIMPLIFY | §5.9, §6.10 |
| D4 acquisition | RESOLVED (= Fork D) | §6.5 |
| D5 dedup confirmation per group | CHANGE | §5.4 |
| D6 keeper explicit scale, quality=bitrate | CHANGE | §5.4 |
| D7 untagged structural + configurable rules | KEEP-BUT-FIX | §5.8 |
| D8 remove cleanup CLI script | REMOVE | (covered by Duplicates+Untagged) |
| D9 remove `tag_rules` | REMOVE | §5.6 |
| D10 remove Live Import M3U8 | REMOVE | §5.7 |
| D11 delete event with preview | CHANGE | §5.7 |
| D12 OS trash | CHANGE | §6.9 |
| D13 FR/EN i18n | KEEP | §3.8 |
| D14 re-download threshold 70/85 | KEEP-BUT-FIX | §5.5 |
| D15 `delete_untagged` protection | OWNER OVERRIDE: ownership-neutral soft-delete, audio untouched | §3.0, §5.8 |
| D16 bulk tags delta | KEEP-BUT-FIX | §5.10 |
| D17 apply with warnings | KEEP-BUT-FIX | §5.10 |
| D18 real output path | CHANGE | §5.5, §6.5 |
| D19 single normalization | SIMPLIFY | §5.3 |
| D20 ISRC fallback barcode | REMOVE | §5.5 |
| D21 global reversibility (+trash) | KEEP | §5.10, §6.9 |
| D22 restore unignore | KEEP-BUT-FIX | §5.10 |
| D23 RB guard on delete event | KEEP-BUT-FIX | §5.7 |
| D24 remove auto-update | REMOVE | §5.10 |
| D25 dead tables/fields | REMOVE | §5.10 |

### 7.4 OVERHAUL-01 Scope — v1 Additions & Deferred Items (Gate 1/2, 2026-06-16)

| # | Status | Integrated in |
|---|---|---|
| A1 Smart Fixes (metadata cleanup) | **ADD v1** | §4 (Smart Fixes job), §5.11, §6.12 |
| A2 fingerprint dedup (Chromaprint) | **DEFERRED to v2** (narrow residual + native binary, no v1 integration) | §4, §6.12 |
| A3 fake-320/FLAC detection | **CONSERVATIVE FALLBACK v1**; full classification `NO-GO`, only keeper-neutral `ok`/`incertain` | §4, §5.12, §6.12 |
| B1 streamrip backend (Deezer-only) | **ADD v1** after Phase 5 `GO`: optional OFF by default, exact pinned component, artwork support, encrypted one-shot ARL, and no Deezer runtime in the base. SoundCloud → v2/B4 | §5.5, §6.5, §7.1, _handoffs/phase-05-b1-acquisition.md (archived) |
| B2 Legal Track Matcher (ISRC purchase links) | **ADD v1** | §4, §5.13, §6.5/§6.12, POC evidence archived in git history, indexed in [POC-EVIDENCE.md](POC-EVIDENCE.md) |
| D7 structural + configurable untagged | already decided (KEEP-BUT-FIX) | §5.8 |

> **Unchanged KEEP v1 corpus** (OVERHAUL-01 §7.2: F1 Spotify sync, F2 ISRC+fuzzy Match, F4 simplified Events, F5 Duplicates, F6 Missing Files, F7 Untagged/D7, **F8 Safety/Backup** (OVERHAUL verdict “cover ANLZ” **corrected Gate-1** → documented ANLZ limit, §3.1/§5.1), **F9 Doctor** — diagnostics + backup management/rotation + logs, mechanics §5.1/§5.10, UI surface §9 —, F10 Settings/i18n) — carried by §3/§5, not re-debated here. (**F3 Acquisition = B2 primary + optional B1 Deezer in macOS v1** after the Phase 5 `GO`.)
> OVERHAUL-01 §7.3 exclusions preserved (local energy/key/vocal analysis, harmonic set-prep, ReplayGain, auto-cues, cross-app conversion, mobile/cloud, beatgrid editing, playable streaming). v2/SHOULD: A2 fingerprint, A4 keeper-merge, A5 ISRC enrichment (AcoustID→MusicBrainz), F1 Doctor analytics (orphans/never-played), E1 setlist export, B4 SoundCloud.

---

## 8. De-risking Order (POC Before Any Commitment)

1. **Signing/notarization** — closed by scope: v1 is ad-hoc signed, with no Developer ID, notarization, or Gatekeeper-trust claim.
2. **Process lifecycle** — `GO`: source, frozen, embedded, and packaged lanes validate process-group termination, clean SQLCipher shutdown, 1/2/4-second restart exhaustion, manual recovery, single instance, foreign/stale listeners, no orphan, and release of ports 8766 and 8765.
3. **Real bundle size + cold start** — measured with PyInstaller `onedir`, CommonCrypto SQLCipher, and the complete A3 runtime. Exact final sizes belong to the final release handoff; packager replacement is not justified.
4. **Packaged WKWebView/SSE** — `GO` on the local and publicly downloaded 0.2.2 artifact. WebView2 remains deferred with Windows v2.
5. **Real Rekordbox fidelity** — `GO`: the ten-node private harness, retained-event migration harness, and Smart Fix copied-fixture node pass with zero skips and unchanged sources. The owner-approved Rekordbox 7.2.16 CommonCrypto disposable-copy walkthrough also passed and the untouched live directory was restored exactly.
6. **Acquisition B1** — `GO` for the full-track, artwork, and packaged boundary. Source, exact frozen, installed, and packaged lanes verify the embedded cover. SoundCloud and ffmpeg remain outside v1.
7. **A3** — full classifier `NO-GO`; conservative read-only fallback `GO`, deterministic and keeper-neutral.
8. **B2 purchase links** — `GO` for browser-only Beatport/Bandcamp templates and the removed-store fallback. A2 fingerprint dedup remains deferred to v2.
9. **A1 Smart Fixes** — `GO`: dry-run equals the executed payload, fixed composition is deterministic and idempotent, ownership is neutral, `_mutate` is mandatory, and stale snapshots abort before writing.

---

## 9. Implemented Design Decisions

The design phase closed the two questions that Gate 1 delegated:

- **§10.9 — UI/UX.** Vue uses a hash router with six destinations:
  Dashboard, Library, Events, Collection Health, Missing, and Settings.
  Collection Health deep-links its Duplicates, Missing, Untagged, Smart Fixes,
  and Backups tabs; Missing deep-links library, event, and collection scopes.
  Unknown routes return to Dashboard, and the ten-step onboarding remains
  replayable from Settings. The UI suite covers routing, core screens,
  onboarding, FR/EN parity, and guarded mutation dialogs.
- **§10.10 — Configurable matching.** The collapsed Advanced Settings section
  exposes bounded confidence-threshold, ambiguity-margin, title/artist/duration
  weights, and ISRC-policy controls with validation and reset. ISRC-first
  ordering, shared D19 normalization, duration buckets, and all write-safety
  invariants remain locked. These design choices are implemented behavior, not
  remaining release gates.

---

## 10. Appendices

- **Current implementation and test authority**: PROMPT-05, the Phase 1 report, and the phase handoffs (all archived in git history), plus the executable POCs indexed by [docs/POC-EVIDENCE.md](POC-EVIDENCE.md).
- **Material official and upstream sources**: recorded with URLs and access dates in the phase handoffs and final release closure (archived in git history). Historical `_research` and `_analysis` paths referenced by older prompts are not present in the current workspace and are not release inputs.
- **Release closure**: every applicable macOS v1 gate, including GitHub publication and public download-back, is closed for 0.2.2. Windows packaging and any evidence that could justify A2 belong to v2.
