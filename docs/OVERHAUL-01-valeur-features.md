# Syncbox — Product Overhaul Report (Feature Value Analysis)

> **Historical product-analysis record.** This report preserves the evidence
> and decisions available when it was written. Current macOS v1 scope and
> verdicts are authoritative only in [SPEC-UNIFIED.md](SPEC-UNIFIED.md),
> [DISTRIBUTION.md](DISTRIBUTION.md), and the final release handoff.

> **Purpose.** Objective value analysis of **all** Syncbox features, redundancy map vs native Rekordbox and competitors, catalog of candidates from in-depth web/GitHub research, then **product scope overhaul** to arrive at an app “useful to all DJs”.
>
> **Status.** Output from prompt [`PROMPT-01b-analyse-valeur-features-overhaul.md`](PROMPT-01b-analyse-valeur-features-overhaul.md). Read-only, no code modified. Input: the functional inventory from [`SPEC-01-syncbox.md`](SPEC-01-syncbox.md) (`file:line` evidence) + [`SPEC-UNIFIED.md`](SPEC-UNIFIED.md) (architecture already decided: Tauri + Python sidecar, optional acquisition). **This document decides SCOPE and VALUE, not the stack** (golden rule 6).
>
> **Method.** Multi-agent research (8 web/GitHub clusters, adversarial verification, completeness critique — 17 agents, 158 sourced items). Every judgment cites its evidence: `file:line`, URL, or identified native capability. *Fact* / *inference* / *opinion* separated. Taste-based tradeoffs were submitted to the owner (§8).

---

> ⚠️ **CURRENT OVERRIDE.** This report remains the value-analysis record. A2/Chromaprint and SoundCloud/ffmpeg are deferred to v2. The delivered v1 additions are A1 Smart Fixes, optional B1 Deezer-only acquisition, B2 legal purchase links, and the conservative A3 spectral fallback. Full A3 classification is `NO-GO`; the fallback emits only keeper-neutral `ok` or `incertain`. [SPEC-UNIFIED §7.4](SPEC-UNIFIED.md) is authoritative. The older v1/v2 lists below remain unchanged as historical evidence and must not be read as current scope.

## 1. Executive Summary (the Verdict)

Syncbox should position itself as **the free, open-source, local-first Swiss Army knife for Rekordbox DJs** — the one that does two things nobody does both for free and locally:

1. **Turn a Spotify playlist into real owned files, tagged and playable on CDJ/USB.** Native Spotify integration (re-added Sept. 24, 2025) is **streaming-only**: no download, no offline, no USB export, no collection import ([rekordbox.com](https://rekordbox.com/en/2025/09/rekordbox-for-mac-win-spotify-support/), [TechCrunch 2025-09-24](https://techcrunch.com/2025/09/24/spotify-now-integrates-directly-with-dj-software-from-rekordbox-serato-and-djay/)). That is exactly the gap Syncbox fills.
2. **Maintain the collection better than native, without subscription or cloud.** Native dedup is rudimentary (search by title, manual, no fingerprint — [source](https://www.clonefileschecker.com/blog/how-to-remove-duplicate-songs-on-rekordbox-software-playlist/)), native Relocate is filename-only and gives up on homonyms ([rekordbox FAQ](https://rekordbox.com/en/support/faq/v6/)), and native Backup is manual, coarse, and destructive on restore ([deejayplaza](https://www.deejayplaza.com/en/articles/rekordbox-backup)). The tools that do better are **paid** (Lexicon $199–399 lifetime, RCT, Music Library Doctor).

**Structural decisions (validated with the owner, §8):**

| Axis | Decision |
|---|---|
| Scope | **Rekordbox-only companion.** No cross-app conversion (Lexicon already owns that space). Rekordbox depth + sourcing as the angle. |
| Downloading | **Optional module, OFF by default**, **streamrip** engine (deemix is dying, see §5). Highlight the **legal ISRC → lossless purchase** path. |
| Free vs Pro | **Yes**: offer for free and locally what Rekordbox gates (reversible versioned backup — already done, to keep). |
| Differentiation | **Solid hygiene + sync first.** The owner **ruled out** local analysis (energy/key/vocal), harmonic ordering, ReplayGain, and auto-cues. Differentiation comes from the **core done better and free**, not from new analysis layers. |
| Audio analysis | **No local analysis.** Only read key/energy values already provided by Rekordbox or a MIK import. |

**What we KEEP** (solid core, covered by tests): Spotify sync, ISRC+fuzzy Match, Events, Duplicates, Missing Files, Untagged, Safety/Backup, Doctor, Settings, FR/EN i18n.
**What we ADD in v1**: dedup by **audio fingerprint (Chromaprint)** *(→ **deferred to v2** by Gate 2, see banner at top)*, **Smart Fixes** (bulk metadata cleanup), **fake-320/fake-FLAC detection**, **legal Track Matcher** (list missing tracks + ISRC purchase links), switch acquisition to **streamrip** *(Deezer-only in v1; SoundCloud → v2)*.
**What we REMOVE**: Live Import M3U8, legacy `tag_rules`, CLI cleanup script, dormant auto-update (already decided D8/D9/D10/D24).
**What we explicitly EXCLUDE**: local analysis, harmonic set prep, ReplayGain, auto-cues, transition tagging, cross-app conversion, mobile/cloud, beatgrid editing, playable in-app streaming (blocked by licenses).

---

## 2. Personas & Evaluation Framework

### 2.1 DJ Personas (Audience Breadth)

| # | Persona | Workflow | Main Pain Point | What They Value |
|---|---|---|---|---|
| **P1** | **Mobile / open-format DJ** (weddings, private parties) | Large multi-genre catalog, many imports from client playlists (Spotify), Rekordbox + controller/USB | Quickly sourcing requested tracks; library keeps growing and getting messy | Spotify→files sync, per-event organization, hygiene |
| **P2** | **Electronic club DJ / harmonic mixing** | Rekordbox + CDJ, buys on Beatport, key/energy are important | Analysis accuracy, set prep, keeping lossless gear-ready files | Owned lossless files, reliable USB, preserved cues |
| **P3** | **Collector / multi-genre digger** | Very large library, multi-source, external drives | **Duplicates, missing files after drive moves, inconsistent metadata** | Advanced hygiene, fingerprint dedup, robust relocate |
| **P4** | **Beginner DJ** | Rekordbox Free, small budget, not very confident | **Fear of breaking/losing the database**, does not understand “references vs files” | Safety, automatic backup, simplicity |
| **P5** | **Pro multi-device DJ** | Multiple machines, USB/CDJ, play history | Portability, backup, “never played” reliability | Versioned backup, integrity, safe USB export |
| **P6** | **Producer-DJ** | Plays own productions + edits, SoundCloud/Bandcamp, custom tags | Custom metadata, sources outside catalogs (SC/Bandcamp) | Personal tags, flexible sourcing, no overwriting |

**Audience breadth** scale: 0 = one persona, 5 = all. The **market’s #1 pain point is library hygiene** (validated: *“My DJ collection is a complete mess”* is one of the most frequent questions — [Digital DJ Tips](https://www.digitaldjtips.com/dj-library-is-a-mess/); there is an entire paid market around it: Lexicon, RCT, Music Library Doctor).

### 2.2 Scoring Rubric

Each criterion is scored **0–5** (5 = best, including for *Effort*, where 5 = low effort, and *Risk*, where 5 = negligible risk). The **global score** is an explicit weighted judgment, not a blind average (indicative weighting: Utility ×2, Audience ×2, Native Complementarity ×2, Differentiation ×1.5, Effort ×1, Risk ×1.5).

- **Utility** — real value for the targeted DJ.
- **Audience breadth** — how many personas (0–5).
- **Native complementarity** — 5 = fills a real Rekordbox gap; 0 = total duplicate of a free native feature (inverse of redundancy).
- **Differentiation** — vs Lexicon, MIK, DJ.Studio, Mixxx, RCT, Music Library Doctor…
- **Effort** — 5 = low, 0 = very heavy (indicative, without deciding the technology).
- **Risk** — legal / technical / maintenance — 5 = negligible, 0 = blocking.

Verdicts: `KEEP` · `KEEP-BUT-FIX` · `SIMPLIFY` · `MERGE` · `CHANGE` · `REMOVE` · `TO-DECIDE`.

### 2.3 Domain Invariants (True Regardless of Scope)

1. **Rekordbox safety**: no write if Rekordbox/`rekordboxAgent` is running; **timestamped backup before every mutation**; `_mutate` unit-of-work; deletions = reversible soft-delete; restore with prior snapshot (`safety.py:20-80`, `adapter.py:505-534`, [SPEC-01 §3.1](SPEC-01-syncbox.md)).
2. **Path resolution**: volume-relative under `rekordbox/`, absolute elsewhere; both forms equal (`paths.py:58-74`, project memory `rekordbox-path-resolution`).
3. **Never move files** (macOS TCC on cloud folders; listing fails but `Path.exists()` works).
4. **Preserve cues / beatgrids / My Tags on every write.** Cues live in **master.db (`djmdCue`) AND in ANLZ files** ([pyrekordbox docs](https://pyrekordbox.readthedocs.io/en/latest/tutorial/anlz.html), [Deep Symmetry](https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/exports.html)). ⚠️ **CORRECTION (2026-06-16, folded into SPEC-UNIFIED)**: the initial version attributed the sentence “cues live in `DjmdCues`, not in ANLZ” to [SPEC-01 §3.1](SPEC-01-syncbox.md) — **that sentence does not exist in SPEC-01** (zero “ANLZ” occurrences); it was an erroneous paraphrase. **Gate 1 decision (settled)**: pyrekordbox **never writes ANLZ** (see invariant 6) → Syncbox does not modify them, and its mutations remain **fully reversible** through the `master.db` backup. F8 backup **does not cover ANLZ** (**documented** limitation, not extended — see [SPEC-UNIFIED §3.1/§5.1](SPEC-UNIFIED.md)); a restore may desynchronize cues that **Rekordbox itself** wrote on the ANLZ side between two Syncbox operations — accepted edge case.
5. **Local files playable on CDJ/USB** (the reason for existing against streaming).
6. **pyrekordbox write limit**: writes `master.db` (DjmdContent/MyTag/Cues/Playlist/Key/Color) but **does not create ANLZ files** (parse only) — [readthedocs](https://pyrekordbox.readthedocs.io/en/latest/tutorial/anlz.html). Bounds feasibility of any cue/beatgrid writing.

---

## 3. Value Audit of Existing Features

> Source inventory: [SPEC-01 §2](SPEC-01-syncbox.md). Scores according to §2.2. Already decided bug fixes (D1–D25) are not re-litigated; the **value/market dimension** is added.

### F1 — Spotify Playlist Sync (Permanent Sources + Default MyTags)
`library.py:45-263`, `stores/library.ts`, `event_import.py`. Follow a Spotify playlist, track-level diffing (new/matched/ready/imported/missing/removed), source MyTag inheritance on import.
- **Utility / personas**: core intake flow. P1 (mobile, client playlists), P6 (productions/edits), somewhat P2/P3.
- **Redundancy vs native**: **strong complement.** Native Spotify = streaming-only, no collection import, no source-based auto-tagging ([rekordbox.com](https://rekordbox.com/en/2025/09/rekordbox-for-mac-win-spotify-support/)). Native has **no** notion of “follow a playlist and materialize it into tagged files”.
- **Vs competitors**: Lexicon **Track Matcher** is metadata/fuzzy-only, **without ISRC and without download** ([manual](https://www.lexicondj.com/manual/track-matcher)); Music Library Doctor does a similar Spotify→crate import but is paid ([site](https://musiclibrarydoctor.com/)); Trackmatch (OSS) stops at diffing without acquisition ([repo](https://github.com/L3-N0X/Trackmatch)).
- ⚠️ **Platform risk**: Spotify tightened Web API access (restriction wave, Feb. 2026 — [Headphonesty](https://www.headphonesty.com/2026/02/spotify-crackdown-thousands-third-party-music-apps/)); **but basic playlist reading (Syncbox’s scope) remains available**. Minimize dependency on sensitive endpoints.
- **Scores**: Utility 5 · Audience 4 · Complement 5 · Diff 4 · Effort 3 · Risk 3 → **Global: HIGH**.
- **Verdict: KEEP** (OAuth PKCE only, D3). Depends on no deprecated endpoint.

### F2 — Spotify → Rekordbox Matching (Exact ISRC then Fuzzy)
`matching.py:27-132`. ISRC first (confidence 100), then fuzzy `title*0.52+artist*0.36+duration*0.12`, threshold 82, `ambiguous` flag.
- **Utility / personas**: cross-cutting engine (sync, events, dedup, missing). All personas.
- **Redundancy vs native**: **no native equivalent.** Total complement.
- **Vs competitors**: **ISRC-first** is a real edge — Lexicon Track Matcher is fuzzy-only ([manual](https://www.lexicondj.com/manual/track-matcher)). OneTagger does ISRC-first matching but writes file tags, not master.db ([repo](https://github.com/Marekkon5/onetagger)).
- **Scores**: Utility 5 · Audience 5 · Complement 5 · Diff 5 · Effort 3 · Risk 4 → **Global: VERY HIGH** (gem, preserve as-is + D19 unified normalization).
- **Verdict: KEEP.**

### F3 — Acquisition / Downloading (Deezer + Deemix → **streamrip**)
`acquisition.py`, `collection_acquisition.py`, `electron/deemix.ts`. Deezer resolution (ISRC then search, thresholds 85/70), Deemix `:6595` control, SSE jobs.
- **Utility / personas**: high usage value (Spotify→playable file), especially P1. **But**: pros (P2/P5) buy lossless; legal gray zone.
- **Redundancy vs native**: **complement** (native does not download).
- ⚠️ **Feasibility (research, critique)**: **deemix is dying in 2026** — Deezer changed its API/login, ARLs often fail, and Deezer is running an **active DMCA campaign against ARL downloaders** ([TorrentFreak](https://torrentfreak.com/deezer-targets-pirate-apps-maliciously-retrieving-publishing-encryption-keys-210212/)). **streamrip** is better maintained, multi-service (Qobuz/Tidal/Deezer/SoundCloud), with history dedup ([repo](https://github.com/nathom/streamrip)).
- **Vs competitors**: DJ.Studio “legalize” does the Beatport purchase then replaces the streaming version ([help.dj.studio](https://help.dj.studio/en/articles/12332505-beatport-beatsource-streaming-vs-shop-in-dj-studio)); Lexicon Beatport auto-replace ([manual](https://www.lexicondj.com/manual/beatport-integration)). The **legal ISRC→purchase** path is under-exploited and clean with respect to ToS (Beatport API v4 — [docs](https://api.beatport.com/v4/docs/)).
- **Scores**: Utility 4 · Audience 3 · Complement 5 · Diff 4 · Effort 2 · Risk 1 → **Global: MIXED** (high value, high risk).
- **Verdict: CHANGE.** **Optional module, OFF by default**, **streamrip** engine; add the **legal Track Matcher** (list missing tracks + ISRC purchase links) as the highlighted alternative. Read the downloader’s real output path (D18), remove process globals (F3-spec).

### F4 — Events (Temporary DJ Sets + Smart Playlist + MyTag)
`event_import.py`, `EventWorkspace.vue`. 3-mode creation, staging, apply creates a **native Rekordbox smart playlist** + an event MyTag (“Situation” category).
- **Utility / personas**: mostly P1 (one party = one event), somewhat P2.
- **Redundancy vs native**: **complement.** Native smart playlists exist ([deejayplaza](https://www.deejayplaza.com/en/articles/rekordbox-intelligent-playlist)) — and Syncbox **emits** one instead of reimplementing it (good instinct). Syncbox value = Spotify playlist → event → tags + auto smart playlist scaffolding.
- **Vs competitors**: DJ.Studio prepares sets and writes into Rekordbox, but it is a paid set builder ([dj.studio](https://dj.studio/automix)).
- **Scores**: Utility 4 · Audience 3 · Complement 4 · Diff 3 · Effort 3 · Risk 3 → **Global: MEDIUM-HIGH**.
- **Verdict: KEEP-BUT-SIMPLIFY.** Remove **Live Import M3U8** (D10), gate delete on `mutationAllowed` (D23), exact preview before deletion (D11).

### F5 — Duplicates (ISRC + Fuzzy, Keeper, Soft-Delete)
`dedup.py`, `adapter.py:1197-1279`, `DuplicatesView.vue`.
- **Utility / personas**: **#1 pain point**, all personas, especially P3.
- **Redundancy vs native**: **strong complement.** Native dedup = type “duplicate” in the search bar (title-string, manual, no fingerprint, no auto-delete — [source](https://www.clonefileschecker.com/blog/how-to-remove-duplicate-songs-on-rekordbox-software-playlist/)).
- **Vs competitors**: Lexicon “Find Duplicates” and RCT use **audio fingerprints** (cross-format), which Syncbox **does not have** ([Lexicon manual](https://www.lexicondj.com/manual/find-duplicates), [RCT](https://atgr-production-team.sellfy.store/p/rct/)); OSS koraysels/rekordbox-library-fixer does too ([repo](https://github.com/koraysels/rekordbox-library-fixer)). This is the **differentiation gap** → add Chromaprint (see C-B).
- **Scores**: Utility 5 · Audience 5 · Complement 5 · Diff 3 (→4 with fingerprint) · Effort 3 · Risk 3 → **Global: HIGH**.
- **Verdict: KEEP + CHANGE keeper (D5/D6) + ADD fingerprint layer.**

### F6 — Missing Files (Relink / Redownload / Remove)
`maintenance.py`, `adapter.py:1027-1195`.
- **Utility / personas**: major pain point (drive move), P3/P5.
- **Redundancy vs native**: **partial complement.** Native Relocate exists but is **filename-only and gives up on homonyms** ([FAQ](https://rekordbox.com/en/support/faq/v6/); confirmed by [rekordbox-repair](https://github.com/edkennard/rekordbox-repair) behavior). Syncbox’s ISRC/name scoring is better.
- **Vs competitors**: Lexicon “Find Lost Tracks”, RCT relocate, rekordbox-repair (OSS, refuses ambiguous matches — good principle to keep).
- ⚠️ Bug B1 (redownload takes the first hit without threshold) → **D14**.
- **Scores**: Utility 5 · Audience 5 · Complement 4 · Diff 3 · Effort 3 · Risk 3 → **Global: HIGH**.
- **Verdict: KEEP-BUT-FIX** (thresholds + ambiguous like the event flow).

### F7 — Untagged (4-Category Diagnostic)
`maintenance.py`, `adapter.py:561-647`. junk / dup_of_tagged / alt_version / review.
- **Utility / personas**: metadata hygiene, P3/P6.
- **Redundancy vs native**: **no native equivalent** → total complement.
- **Vs competitors**: adjacent to librarydojo/Sensei (smart playlist/tag suggestions for Rekordbox — [librarydojo](https://librarydojo.com/)) and Choon (AI auto-tag → MyTags — [choon.app](https://choon.app/)), but those are paid AI suggesters; Syncbox = deterministic diagnostic.
- ⚠️ **Personal/French** junk heuristics (`discours`, `psg`, `bereal`…) + 1-token artist bug (B5) + greedy `feat` regex (B7) → **D7**.
- **Scores**: Utility 4 · Audience 4 · Complement 5 · Diff 4 · Effort 3 · Risk 2 → **Global: HIGH**.
- **Verdict: KEEP-BUT-FIX.** **Universal structural** rules (stub `spotify:track:`, empty title, artist `rekordbox`) **+ user-configurable patterns**; fix B5/B7.

### F8 — Safety & Backup (RB Guard, Backup Before Mutation, Soft-Delete, Restore)
`safety.py:20-80`, `adapter.py:171-318,505-534`, `DoctorView.vue`.
- **Utility / personas**: **invariant + gem.** Addresses the **#1 fear** (corrupted database / lost cues — recurring Pioneer forum threads: [example](https://community.pioneerdj.com/hc/en-us/community/posts/22979193547545)). All personas, especially P4/P5.
- **Redundancy vs native**: **strong complement.** Native Backup Library is **manual, coarse (whole master.db), and destructive on restore** ([deejayplaza](https://www.deejayplaza.com/en/articles/rekordbox-backup)). Syncbox = automatic, timestamped, before **every** mutation, N rotation, reversible soft-delete, reversible restore.
- **Vs competitors**: Lexicon DB backup is **cloud and paid (Ultimate $399)** ([features](https://www.lexicondj.com/features)); Syncbox’s local versioning is probably **safer and more granular** for the Rekordbox user. **This is the direct application of the decision “offer the Pro equivalent for free”.**
- ⚠️ See correction §2.3-4: cues also in ANLZ — verify backup completeness in Phase 2.
- **Scores**: Utility 5 · Audience 5 · Complement 5 · Diff 4 · Effort 3 · Risk 4 → **Global: VERY HIGH**.
- **Verdict: KEEP** (extend file deletion to **OS trash** D12; cover ANLZ).

### F9 — Doctor (Diagnostics + Backup Management + Logs)
`diagnostics.py`, `DoctorView.vue`.
- **Redundancy vs native**: complement (native has no diagnostic center).
- **Scores**: Utility 3 · Audience 4 · Complement 4 · Diff 2 · Effort 4 · Risk 4 → **Global: MEDIUM**.
- **Verdict: KEEP** + opportunity to host very cheap **collection analytics** (orphans, never played — see C-F, SHOULD).

### F10 — Settings + FR/EN i18n
`SettingsView.vue`, `i18n/index.ts:21-63`.
- **Redundancy**: n/a (infra). **Audience 5.**
- **Scores**: Utility 3 · Audience 5 · Complement n/a · Diff 1 · Effort 4 · Risk 4 → **Global: MEDIUM** (but necessary).
- **Verdict: KEEP** (i18n D13). **Mandatory generalization**: remove hardcoded paths (`config.py:15-19`, D1), validate all paths (F15).

### F11 — Dead / Vestigial Features (Already Decided)
| Feature | Location | Score | Verdict |
|---|---|---|---|
| **Live Import M3U8** | `live_import.py`, `EventsView.vue:66-125` | Audience 1 · Complement 2 | **REMOVE** (D10) — bypasses RB guard, source of B12 |
| **`tag_rules` (legacy table)** | `repositories/tags.py`, `library.ts:23` | superseded | **REMOVE** (D9) — cause of B4 (seed that reverts edits) |
| **CLI script `cleanup_rekordbox.py`** | `service/scripts/` | redundant | **REMOVE** (D8) — covered by Duplicates + Untagged |
| **electron-updater auto-update** | dormant, `DISTRIBUTION.md:119-126` | — | **REMOVE** (D24, consistent with memory `no-auto-build-release`) |
| **`event_playlists`, `ProposalType.*_to_spotify`, StatusBadge tones** | various | dead | **REMOVE** (D25) after confirming no consumer exists |

### 3.bis — Ranking of Existing Features (Most to Least Justified)

1. **F8 Safety/Backup** (VERY HIGH) — invariant + gem + addresses #1 fear, free where competitor is paid.
2. **F2 ISRC+fuzzy Match** (VERY HIGH) — cross-cutting engine, unique ISRC edge.
3. **F5 Duplicates** (HIGH) — market’s #1 pain point.
4. **F1 Spotify sync** (HIGH) — the gap native will never fill.
5. **F6 Missing Files** (HIGH) — major pain point, scoring edge vs native filename-only.
6. **F7 Untagged** (HIGH) — unique diagnostic, needs depersonalization.
7. **F4 Events** (MEDIUM-HIGH) — P1 niche, simplify.
8. **F3 Acquisition** (MIXED) — high value, high risk → optional/streamrip/legal.
9. **F9 Doctor** (MEDIUM) — useful, little differentiation.
10. **F10 Settings/i18n** (MEDIUM) — necessary, generalize.
11. **F11 dead** — REMOVE.

---

## 4. Redundancy Map vs Native Rekordbox (and Competitors)

> `complement` = fills a gap · `partial` = partly overlaps · `total` = duplicate of a free native feature (⇒ do not rebuild). Sources: [rekordbox.com/feature](https://rekordbox.com/en/feature/overview/), [/plan](https://rekordbox.com/en/plan/), [/cloud](https://rekordbox.com/en/feature/cloud/), DJ press.

| Native capability | Free? | Native quality | Related Syncbox feature | Redundancy verdict |
|---|---|---|---|---|
| **My Tag** (4 fixed groups) | ✅ free | Complete but **manual**, no source-based auto-tag | F1/F4/F7 (writes *into* My Tag) | **complement** (auto-application) |
| **Smart/Intelligent Playlists** | ✅ free | Very complete, auto-regenerated | F4 (emits a native smart playlist) | **complement** (we emit, we do not rebuild) |
| **BPM/key/beatgrid/cue analysis** | ✅ free | Native engine owns this territory | (none — we do NOT analyze) | **total — do not build** |
| **Auto hot/memory cues** | ✅ free | Native AI | (auto-cues ruled out) | **total — do not build** |
| **Duplicate search** | ✅ free | **Rudimentary** (title-string, manual, no fingerprint) | F5 Duplicates | **strong complement** |
| **Relocate / Auto Relocate** | ✅ free | **Filename-only**, gives up on homonyms | F6 Missing Files | **partial complement** |
| **Backup Library** | ✅ free | **Manual, coarse, destructive restore** | F8 Safety/Backup | **strong complement** |
| **Cloud Library Sync / CloudDirectPlay** | ❌ **paid** (Pro/cloud; Core/Creative new subscriptions **suspended** since March 2025 — [research correction](https://www.digitaldjtips.com/rekordbox-subs-return-but-youll-pay-more-for-now-at-least/)) | Multi-device cloud replication | (none — Syncbox is local-first) | **n/a** (we do not compete with cloud) |
| **Collection Auto Upload / Device Library Backup** | ❌ paid (Professional) | Cloud backup | F8 (but local) | **n/a / local complement** |
| **Integrated Spotify (Sept. 2025)** | ❌ Premium | **Streaming-only**: no download/offline/USB/import | F1 Spotify sync | **complement** (positioning core) |
| **Native Beatport streaming** | ❌ paid | Play-only, **no USB export**, encrypted cache | F3 (legal path) | legal boundary |
| **Traffic Light / Related Tracks / Radar** | free/freemium | Performance/discovery aids | (out of scope) | n/a |

**Positioning anchor**: everything Syncbox does is either a **complement to a free but rudimentary native feature** (dedup, relocate, backup), or **fills a total native gap** (Spotify→owned file, ISRC match, untagged), or is a **free/local equivalent of a paid native feature** (versioned backup). There is no total duplicate of a **complete** free native feature.

**Vs competitors (summary):**

| Competitor | Model | Overlap | Syncbox edge |
|---|---|---|---|
| **Lexicon DJ** ([pricing](https://www.lexicondj.com/pricing)) | Free conversion; Essential **$199 lifetime / $9.99 mo**; Ultimate **$399 / $19.99 mo** | dedup, missing, smart fixes, Track Matcher, backup — **paid** | Free/OSS, local-first, **ISRC+download**, no cloud lock-in |
| **Music Library Doctor** ([site](https://musiclibrarydoctor.com/)) | freemium | Spotify import, dup, missing, FFT quality scoring | OSS, fingerprint dedup + integrated sourcing |
| **RCT (Rekordbox Collection Tool)** ([sellfy](https://atgr-production-team.sellfy.store/p/rct/)) | paid macOS | fingerprint dedup + relocate + cloud path fix — **same RB 6/7 platform** | free, multi-OS, integrated Spotify sync |
| **koraysels/rekordbox-library-fixer** ([repo](https://github.com/koraysels/rekordbox-library-fixer)) | OSS (XML, master.db on roadmap) | fingerprint dedup + relink + quality keeper | direct master.db write + sourcing |
| **Choon** ([choon.app](https://choon.app/)) | freemium | AI auto-tag → MyTags (Bandcamp/Beatport purchases) | Spotify sourcing + hygiene, deterministic |
| **MIK 11 / Pro** ([shop](https://shop.mixedinkey.com/)) | **$58 / $99** one-time | key + energy + 8 cues | n/a (Syncbox **does not** analyze — reads MIK/RB) |
| **SetFlow / DJ.Studio / Mixgraph** | cheap subscriptions → perpetual | harmonic set prep | **out of scope** (ruled out §8) |

---

## 5. Candidate Feature Catalog (In-Depth Web/GitHub Research)

> From the 8 research clusters. Each candidate: description, who already does it (URL), personas, Syncbox relevance. Scoring/prioritization is in §6. ⚠️ flags a critical feasibility fact.

### A. Advanced Library Hygiene
- **A1 — Smart Fixes / bulk metadata cleanup.** Extract artist/remixer from title, fix casing, remove junk characters/URLs, fix encoding. Done by **Lexicon Smart Fixes** ([features](https://www.lexicondj.com/features)). **Also improves Syncbox fuzzy matching accuracy.** Personas P3/P6/P1. Low effort.
- **A2 — Audio fingerprint dedup (Chromaprint/AcoustID).** Catches duplicates that ISRC+fuzzy misses (re-encodes, different rips, absent/bad ISRC). Done by Lexicon, RCT, koraysels; OSS building block = **Chromaprint/pyacoustid** ([repo](https://github.com/acoustid/chromaprint)), as in **beets** ([repo](https://github.com/beetbox/beets)) and Mixxx. Personas P3/P5. Local comparison without network (verified). ⚠️ **CORRECTION (2026-06-16, research [_research/11](_research/11_Chromaprint-empreinte.md), folded into SPEC-UNIFIED)**: the initial claim “KissFFT keeps Chromaprint permissive” is **false for official `fpcalc` binaries** — they embed static FFmpeg (audio decoding) → **LGPL 2.1**, not permissive ([LICENSE.md](https://github.com/acoustid/chromaprint/blob/master/LICENSE.md): “as a whole … LGPL 2.1”). KissFFT only makes a custom build **without** FFmpeg permissive, which then loses the decoder. **Gate 2 decision: A2 deferred to v2** (narrow residual + LGPL binary to notarize).
- **A3 — Fake-320 / fake-FLAC detection.** Spectral cutoff analysis (FFT) to detect lying bitrates. Done by **Music Library Doctor** ([site](https://musiclibrarydoctor.com/)). Quality hygiene for downloaded files (reinforces F3). Personas P2/P3.
- **A4 — Dedup keeper “merge”.** Merge metadata + hot cues from the loser into the keeper before deletion, instead of discarding. Done by RekordboxFix ([repo](https://github.com/TisTatig/RekordboxFix)). Improves F5.
- **A5 — ISRC enrichment via AcoustID→MusicBrainz** for tracks without reliable ISRC (reinforces match + dedup). Building block: pyacoustid + musicbrainzngs (Picard pattern — [repo](https://github.com/metabrainz/picard)). Note: ⚠️ current B6 incorrectly uses the `barcode` tag as ISRC (D20).

### B. Sourcing / Acquisition
- **B1 — streamrip backend** (multi-service Qobuz/Tidal/Deezer/SoundCloud, history dedup) replacing deemix ([repo](https://github.com/nathom/streamrip)). ⚠️ **deemix is dying** (Deezer API/ARL + DMCA — [TorrentFreak](https://torrentfreak.com/deezer-targets-pirate-apps-maliciously-retrieving-publishing-encryption-keys-210212/)).
- **B2 — Legal Track Matcher + ISRC purchase basket.** List missing tracks from a playlist and generate **lossless purchase links** (Beatport API v4 read-only, ToS-clean — [docs](https://api.beatport.com/v4/docs/); Bandcamp/Juno). DJ.Studio “legalize” pattern ([help](https://help.dj.studio/en/articles/12332505-beatport-beatsource-streaming-vs-shop-in-dj-studio)).
- **B3 — YouTube fallback (yt-dlp)** when ISRC/Deezer fails. spotDL/freyr do it ([spotDL](https://github.com/spotDL/spotify-downloader)). ⚠️ **lossy + gray** — last resort only.
- **B4 — SoundCloud/Bandcamp sources** (edits/bootlegs/productions absent from catalogs) for P6. scdl ([repo](https://github.com/scdl-org/scdl)), Bandcamp via Choon-like.

### C. Set Prep & Harmonic Mixing *(globally RULED OUT §8)*
- **C1 — Harmonic/energy ordering** of a playlist (Camelot+BPM+arc). SetFlow ([site](https://www.setflow.app/)), DJ.Studio Harmonize ([transitions](https://dj.studio/transitions)).
- **C2 — Multi-dimensional transition score** (harmonic/BPM/energy/groove/mood/**vocal-fit**). Mixgraph ([how-it-works](https://www.mixgraph.io/how-it-works)).
- **C3 — Transition tags** (“these two mix well”). Almost nonexistent elsewhere; round-trippable in MyTags. Niche differentiator.
- **C4 — Crates by role/energy** (warm-up/peak) + “never played”. [DJ TechTools](https://djtechtools.com/2022/11/25/controlling-the-dancefloor-a-guide-on-organizing-playlists-by-energy/) taxonomy. ⚠️ Native already has rule-based smart playlists ([vibesdj](https://vibesdj.io/learn/techniques/smart-playlist-creation)).

### D. Metadata / Analysis *(RULED OUT §8 — no local analysis)*
- **D1 — Local energy/key/has-vocals analysis → MyTags.** Essentia ([repo](https://github.com/MTG/essentia)), libkeyfinder ([repo](https://github.com/mixxxdj/libkeyfinder)). Free equivalent of MIK/Choon. ⚠️ **This is now the only path**: Spotify’s `audio-features` API has been **dead since Nov. 27, 2024** ([Spotify blog](https://developer.spotify.com/blog/2024-11-27-changes-to-the-web-api)) — energy/key can no longer be pulled from Spotify. Cost: embedding models ~hundreds of MB.
- **D2 — ReplayGain / loudness normalization** (non-destructive tags, rsgain — [repo](https://github.com/complexlogic/rsgain) / ffmpeg loudnorm). Gap Rekordbox does not expose portably.
- **D3 — Auto-cues written into Rekordbox.** Generation (CUE-DETR [repo](https://github.com/ETH-DISCO/cue-detr), all-in-one, structure) + writing. OSS evidence: djcues ([repo](https://github.com/mcroydon/djcues)), CueGen ([repo](https://github.com/mganss/CueGen)). ⚠️ **Risk**: pyrekordbox **does not write ANLZ**; cues in master.db **AND** ANLZ; **RB7 support unconfirmed** (CueGen issue #25). `rbox` (Rust, same author as pyrekordbox) claims ANLZ writing — future path ([docs.rs](https://docs.rs/rbox)).

### E. Portability / Export *(out of cross-app scope, §8)*
- **E1 — Setlist/playlist export** M3U8/CSV/HTML/PDF. Lexicon ([share](https://www.lexicondj.com/manual/share)), quickCUE ([repo](https://github.com/globalnomad/quickCUE)). Cheap, complements Events.
- **E2 — CDJ/USB export validation**: flag unplayable files (32-bit float, hi-res, unsupported formats) before export, optional conversion to 16-bit AIFF. rekordbox-proof-audio-conversion ([repo](https://github.com/tammohesselink/rekordbox-proof-audio-conversion)). Serves the “playable on CDJ” invariant. *(Declined v1, §8.)*
- **E3 — USB export verification** (parse PDB/ANLZ) to confirm cues/grids survived. rekordcrate ([repo](https://github.com/Holzhaus/rekordcrate)), crate-digger, [Deep Symmetry](https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/exports.html).
- **E4 — Cross-app conversion** RB↔Serato↔Engine↔Traktor. Lexicon (free), DJCU (€24.50), DJ Cue Bridge (free browser — [site](https://djcuebridge.com/)). **Outside Rekordbox-only scope.**

### F. Collection Analytics (Doctor)
- **F1 — Orphan tracks** (in no playlist), **never played** (`DJPlayCount=0`), **playlist occurrence**, unreferenced files. Cheap DB queries. Building blocks: rekordbox-mcp ([repo](https://github.com/davehenke/rekordbox-mcp), `get_unplayed_tracks`), rekordfix ([repo](https://github.com/rzuppur/rekordfix)), PRACT ([repo](https://github.com/LePopal/PRACT)).
- **F2 — USB play history merge** (Device Library Plus) for reliable “never played”. pyrekordbox **reads** `exportLibrary.db` ⚠️ but **does not write** this format ([README](https://github.com/dylanljones/pyrekordbox)) — therefore read-only analytics.

### G. Unexpected Angles (Research)
- **G1 — Recorded set identification → tracklist** (Shazam-like). Setlist.ID ([site](https://setlist.id/)), TrackRadar ([site](https://trackradar.ai/tools/dj-set-analyzer)). ⚠️ Depends on an external fingerprinting service (ACRCloud/AudD) — poor local-first fit; **integrate rather than build**.
- **G2 — Playlists from tag logic** (Boolean algebra → smart playlist). DJ-Tools ([repo](https://github.com/a-rich/DJ-Tools)). Complements the MyTag system.
- **G3 — Smart playlist generation by config** (Situation→Texture→Genre). tseitz/rekordbox-smart-playlist ([repo](https://github.com/tseitz/rekordbox-smart-playlist)) — **same stack** (pyrekordbox + backup-before-write).

---

## 6. Candidate Scoring & Prioritization

> Rubric §2.2. Priority accounts for decisions §8.

### MUST-ADD (v1)
| # | Candidate | Utility · Aud · Compl · Diff · Effort · Risk | Justification |
|---|---|---|---|---|
| **A2** | Audio fingerprint dedup (Chromaprint) | 5·5·5·4·3·4 | Fills F5’s differentiation gap; the feature Lexicon/RCT **charge for**. Validated §8. |
| **A1** | Smart Fixes (metadata cleanup) | 4·5·4·4·4·4 | Low effort, **also improves Syncbox fuzzy matching**. Validated §8. |
| **A3** | Fake-320/fake-FLAC detection | 4·4·5·4·3·4 | Unique quality hygiene in OSS RB space; reinforces trust in F3. Validated §8. |
| **B1** | streamrip backend | 4·3·5·3·3·2 | deemix dying; robustness + multi-source. Validated §8. |
| **B2** | Legal Track Matcher + ISRC purchase links | 4·4·5·3·3·5 | **ToS-clean** path, widens pro audience (P2/P5), defuses legal risk. Validated §8. |
| **(D7)** | Structural + configurable untagged rules | 4·4·5·4·3·3 | Already decided; turns F7 from single-user to multi-DJ product. |

### SHOULD-ADD (v2, Subject to Validation)
| # | Candidate | Score | Justification |
|---|---|---|---|
| **F1** | Doctor analytics (orphans / never played / occurrence) | 4·4·4·2·4·4 | Cheap DB queries, hygiene-adjacent (not set prep). Not submitted to owner → **to validate**. |
| **E1** | M3U8/CSV setlist export | 3·3·3·2·5·5 | Trivial, complements Events. **To validate.** |
| **A4** | Keeper “merge” (loser cues/metadata) | 3·3·4·3·3·3 | Improves F5 without new surface. |
| **A5** | AcoustID→MusicBrainz ISRC enrichment | 3·4·4·3·2·3 | Reinforces match+dedup; moderate cost (MusicBrainz network). |

### NICE-TO-HAVE (Later)
- **E1bis** HTML/PDF setlist export · **F2** USB history read (Device Library Plus) · **G2** playlists by tag logic · **G3** smart playlists by config · **B4** SoundCloud/Bandcamp sources for P6.

### RULE OUT (with Reason)
| Candidate | Reason |
|---|---|
| **D1** Local energy/key/vocal analysis | **Owner decision §8** (“no local analysis”). Objectively: effort + sidecar weight (~hundreds of MB); the *only* path since Spotify audio-features API death, but decided against. |
| **C1/C2** Harmonic ordering / transition score | **Owner decision §8.** SetFlow/DJ.Studio/Mixgraph territory already dense; native has Traffic Light/Radar. |
| **D2** ReplayGain | **Declined §8** (reversible: low effort, real value — noted for record). |
| **D3** Auto-cues | **Declined §8** + objectively risky (ANLZ not writable, RB7 unconfirmed). |
| **C3** Transition tags | **Declined §8**; niche/personal (57% of tags are unique per DJ — [reallychrism](https://reallychrism.substack.com/p/the-library-changes-im-betting-on)). |
| **E2** CDJ/USB export validation | **Declined §8** (reversible; nevertheless serves the invariant — noted). |
| **E4** Cross-app conversion | **Outside Rekordbox-only scope §8**; Lexicon/DJCU cover it well. |
| **G1** Recorded set ID | Depends on external fingerprinting service → anti local-first. **Integrate if ever, do not build.** |
| Mobile / cloud sync | Outside local-first scope; desktop TCC constraint. |
| Beatgrid editing | **Invariant: preserve, not edit**; heavy DSP ([reallychrism](https://reallychrism.substack.com/p/how-to-grid-impossible-tracks)). |
| Playable in-app streaming (Spotify/Beatport) | **Blocked by label licenses** (reserved for RB/Serato/djay partners). Unrealistic for a third-party app. |

---

## 7. Target Overhaul (Selected Scope)

### 7.1 Positioning
> **Syncbox — the free, local-first Rekordbox companion that turns your Spotify playlists into real owned files playable on CDJ, and keeps your collection clean and backed up — no subscription, no cloud, no MIK.**

Two promises, two proofs of non-redundant complementarity: (1) the **sourcing** native Spotify will never do (streaming-only), (2) the **hygiene + safety** native does poorly and competitors charge for.

### 7.2 Waves

**v1 — “Solid Core” (sync + hygiene + safety)**
- KEEP: F1 Spotify sync (PKCE), F2 ISRC+fuzzy Match, F4 Events (simplified), F5 Duplicates, F6 Missing Files, F7 Untagged, F8 Safety/Backup, F9 Doctor, F10 Settings/i18n.
- FIX (D14–D23): thresholded redownload, event delete guard, tag add/remove by delta, restore unignore, apply-with-warnings, etc.
- ADD: **A2** fingerprint dedup · **A1** Smart Fixes · **A3** fake-320/FLAC · **B1** streamrip · **B2** legal Track Matcher · **D7** universal+configurable untagged rules.
- REMOVE: F11 (Live Import, tag_rules, CLI cleanup, auto-update, dead fields).

**v2 — “Hygiene Refinement” (no analysis differentiation)**
- **F1** Doctor analytics (orphans/never played/occurrence) · **E1** setlist export · **A4** keeper merge · **A5** ISRC enrichment. *(All to validate — §8 ruled out the analysis layer, not hygiene.)*

**Later / experimental**
- F2 USB history · G2/G3 playlists by tags/config · B4 SoundCloud/Bandcamp · HTML/PDF export.

### 7.3 Explicit Exclusions (and Why)
Local energy/key/vocal analysis · harmonic set prep · ReplayGain · auto-cues · transition tagging · cross-app conversion · CDJ export validation · mobile/cloud · beatgrid editing · playable streaming. *(Justifications: §6 RULE OUT. Most are taste decisions §8; others are impossible — licenses — or anti-invariant.)*

### 7.4 Required Generalizations (Single-User → Multi-DJ Product)
1. **Remove all hardcoded paths** (`config.py:15-19`, `settings.ts:14-17`, `.env.example`) → everything configurable (D1). *Blocking for “useful to all”.*
2. **Structural + configurable untagged rules** instead of personal/French patterns (D7).
3. **Cross-OS macOS + Windows**: Rekordbox process detection, system paths, trash, file operations (D2).
4. **Secrets hygiene**: no plaintext credential in an open-source repo; encrypted/keychain tokens ([SPEC-UNIFIED §6.7](SPEC-UNIFIED.md)).
5. **Generic onboarding** (connect Spotify → paths → green Doctor) instead of implicit Dropbox setup.

---

## 8. Interactive Decision Log

**Batch 1 — Positioning (Before Research):**
| Question | Selected Answer |
|---|---|
| Scope beyond Rekordbox | **Rekordbox-only companion** (depth + sourcing as the angle). |
| Place of downloading (gray zone) | **Optional module OFF by default + legal ISRC purchase path** highlighted. |
| Offering Pro equivalents for free | **Yes**, where feasible/legal (reversible versioned backup). |
| Appetite for costly/risky differentiation | **Hygiene + sync first (v1), differentiation in v2.** |

**Batch 2 — Candidate Tradeoffs (After Research):**
| Question | Selected Answer |
|---|---|
| v2 differentiators (analysis/ordering/ReplayGain/auto-cues) | **None of those.** → differentiation comes from the core done better/free. |
| Acquisition backend (deemix dying) | **Switch to streamrip** (multi-service), optional module OFF. |
| Weight of local analysis | **No local analysis** — only read RB/MIK. |
| v1 hygiene to add | **Fingerprint dedup (Chromaprint) + Smart Fixes + fake-320/FLAC detection.** (CDJ export validation **not** selected.) |

---

## 9. Open Questions & Reusable Building Blocks (Phase 2)

### 9.1 Open Scope Questions (to Resume in the Architecture Prompt)
1. **Backup completeness vs ANLZ cues.** Factual correction: cues live in **master.db `djmdCue` AND ANLZ** ([pyrekordbox](https://pyrekordbox.readthedocs.io/en/latest/tutorial/anlz.html)). [SPEC-01 §3.1](SPEC-01-syncbox.md) states the opposite. **Does F8 backup cover ANLZ?** Otherwise, a restore may lose cues written on the ANLZ side. To decide in Phase 2.
2. **Legal Track Matcher — purchase sources**: ✅ **RESOLVED** ([_research/13](_research/13_Achat-legal-ISRC.md), [SPEC-UNIFIED §5.13](SPEC-UNIFIED.md)) — Beatport API v4 = **de facto closed** portal (partner-only); recommendation = **app-side constructed search URLs to Beatport + Bandcamp** (stdlib, zero network). **Juno Download closed on 2026-06-01** (removed).
3. **streamrip — embedding model**: ✅ **RESOLVED** ([_research/14](_research/14_streamrip-embedding-Deezer-SoundCloud.md), [SPEC-UNIFIED §5.5/§6.5](SPEC-UNIFIED.md)) — **imported library = default** (API `PendingSingle.resolve()→track.download_path`, real D18), **CLI subprocess ruled out** (no machine-readable output); **Deezer-only v1** (SoundCloud→v2, ffmpeg); ARL in memory, never plaintext; **deemix-fork = documented fallback**.
4. **Validation of SHOULD candidates** (Doctor analytics, setlist export) not yet submitted to the owner.
5. **Spotify dependency**: Web API tightening (Feb. 2026) — confirm that only `playlist-read-*` scopes are used and no deprecated endpoint (audio-features, recommendations) is required.
6. **Acquisition legal risk** to document (Deezer ToS, DMCA, streamrip GPL license) — consistent with “optional module”.

### 9.2 Identified Reusable Building Blocks (Without Architecture Choice)
| Building block | URL | Syncbox usage |
|---|---|---|
| **pyrekordbox** | [github](https://github.com/dylanljones/pyrekordbox) | DB core (already used). Writes master.db; **not** ANLZ. Now reads `exportLibrary.db` (USB). |
| **Chromaprint / pyacoustid** | [github](https://github.com/acoustid/chromaprint) | Audio fingerprint for A2 (dedup) and A5 (enrichment). |
| **beets** | [github](https://github.com/beetbox/beets) | AcoustID + MusicBrainz reference (canonical ISRC) for A5. |
| **streamrip** | [github](https://github.com/nathom/streamrip) | Acquisition backend B1 (Qobuz/Tidal/Deezer/SC + history dedup). |
| **Music Library Doctor (FFT concept)** | [site](https://musiclibrarydoctor.com/) | Spectral cutoff algorithm for A3 (fake-320/FLAC) — reproducible. |
| **koraysels/rekordbox-library-fixer** | [github](https://github.com/koraysels/rekordbox-library-fixer) | Keeper quality scale (format/bitrate, BitRate=0 case) for D6. |
| **rekordbox-bulk-edit (jviall, v0.6.0)** | [github](https://github.com/jviall/rekordbox-bulk-edit) | filter→dry-run→confirm→mutate pattern on pyrekordbox (Smart Fixes A1). |
| **tseitz/rekordbox-smart-playlist** | [github](https://github.com/tseitz/rekordbox-smart-playlist) | Smart playlist creation + backup-before-write (mirror of Syncbox stack). |
| **davehenke/rekordbox-mcp** | [github](https://github.com/davehenke/rekordbox-mcp) | Ready-made queries: `get_unplayed_tracks` (never played), compatible key (analytics F1). |
| **rekordbox-repair (edkennard)** | [github](https://github.com/edkennard/rekordbox-repair) | Rule “refuse relink on multiple match” (F6). |
| **rekordcrate / crate-digger / Deep Symmetry** | [djl-analysis](https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/exports.html) | PDB/ANLZ specs to verify USB export (E3, and backup-ANLZ question). |
| **rbox (Rust, same author as pyrekordbox)** | [docs.rs](https://docs.rs/rbox) | Future path if ANLZ writing is required (cues/beatgrids) from a Rust/Tauri sidecar. |

---

*End of report. All value, redundancy, and feasibility claims are sourced (`file:line`, URL, or native function). Flagged uncertainties: exact Lexicon/MIK prices (JS pages, secondary sources); RB7 status for cue writes; real stability of streamrip vs Deezer/Qobuz evolutions. The complete research (158 verified items) is archived in the run log.*
