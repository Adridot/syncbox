# PROMPT — Feature Value Analysis & Objective Product Overhaul
### Phase 1.5/2: utility, redundancy vs Rekordbox, and features to add

> **Historical prompt.** Current product scope is defined by SPEC-UNIFIED and
> PROMPT-05; this file only preserves the earlier analysis instructions.

> **Instructions.** To be run **after** Phase 1 (functional & technical analysis, see `PROMPT-01-analyse-fonctionnelle-technique.md`). Either in the same session (“you already have the big picture”), or in a fresh session — in that case, first read the spec document produced by Phase 1. The deliverable is a **product overhaul report**: it rules on the value of each feature and proposes a target scope. It does not decide the architecture (Phase 2).

---

## ── START OF PROMPT ──

### Context

Now that you have an overview of **Syncbox** (Rekordbox companion app: Spotify playlist sync, Deemix/Deezer download, collection cleanup — duplicates / missing files / untagged files, preparation of DJ events/sets), I want you to perform an **in-depth and objective value analysis** of all its features, then propose an **overhaul** of the product scope.

Three questions guide the analysis, for **each** existing feature:
1. **Intrinsic utility** — what it is really for, for whom, how often.
2. **Redundancy** — does it duplicate a **native Rekordbox** function (or an obvious competitor’s function)? If yes, to what degree, and is the native side free or paid?
3. **Interest / differentiation** — does it provide value that the native feature does not cover (or covers poorly)?

Then: **what could we add?** There are surely some very interesting features I would want to integrate. To find them, **explore the web in depth**, and **especially all GitHub projects** related to Rekordbox and DJing in general. Bring back everything related to it.

Final objective: a **highly objective overhaul**, to result in an application **useful for all DJs**, not only for my current personal use.

### Your Role and Stance

You are a **product strategist** combined with a **DJ domain analyst**. You are objective and evidence-based: every value judgment is grounded in a verifiable fact (a real use case, a web source, redundancy observed in the code or in Rekordbox), never in a gratuitous opinion. You represent **all DJs**, not the current owner of the app.

### Golden Rules — NON-NEGOTIABLE

1. **Traceable objectivity.** Every claim of value, redundancy, or gap must cite its evidence: `file:line` from the code, URL of a source, or identified native Rekordbox function. No “this would be nice” without justification. Clearly separate *fact* / *inference* / *opinion*.

2. **“Useful for all” = reason by personas, not by my setup.** The current app is tailored to a single user (e.g. hard-coded Dropbox storage paths, very personal Spotify→Deemix workflow). For each feature and each addition, ask yourself: *which DJ profiles benefit from it, and how many?* Define 4-6 personas (see Phase A) and evaluate the breadth of audience for each feature.

3. **Redundancy vs native: verify systematically.** For each feature, explicitly compare it against **native Rekordbox** capabilities (use Appendix A as a base, but verify/update — Rekordbox evolves quickly, e.g. Spotify reintegration in Sept. 2025). Conclude with: `complement` / `partial duplicate` / `total duplicate`, noting whether the native feature is free or paid (paid changes the equation: duplicating a Rekordbox Pro feature can have value if we offer it for free).

4. **Web & GitHub research is MANDATORY and in-depth.** Appendices B/C/D are a **dated starting point (June 2026), not a limit**. Extend them: look for new GitHub projects (Rekordbox, Serato, Traktor, Engine DJ, tagging/analysis tools, downloaders), new competitors, and recurring DJ pain points (forums, Reddit, specialized press). For each lead: URL, what it does, and what we could reuse or take inspiration from.

5. **At the slightest doubt about keeping / adding / removing → ASK.** As soon as a trade-off depends on my tastes, usage model, or priorities — and you cannot decide objectively — ask me the question (`AskUserQuestion`, in thematic batches). Especially for: high-potential but high-effort features, ambiguous redundancies, and “differentiating but risky” additions. When in doubt: ask.

6. **You do NOT decide the architecture or the stack.** Here we are discussing **product scope and value**, not implementation. You may note relative effort and reusable building blocks (Appendix B), but technical choices are for Phase 2. If you write “X should be coded in Y,” turn it into an effort note or an open question.

7. **Honesty about legal and technical feasibility.** Clearly distinguish what is feasible, gray, or blocked: **streaming downloads** (Deemix/yt-dlp) are in a legal gray area; **playable streaming** (Spotify/Beatport direct playback) is locked down by label licenses and reserved for partners (Rekordbox/Serato/djay) — unrealistic for a third-party app. Do not propose the impossible without flagging it.

8. **Read-only, no code.** The only artifact is the overhaul report (+ the questions asked).

### Method (Analysis Phases)

**Phase A — Evaluation Framework.**
Before judging anything, establish the framework:
- **Define 4-6 DJ personas** (e.g. mobile/wedding open-format DJ · electronic club DJ/harmonic mixing · multi-genre collector · beginner DJ · professional multi-device/multi-software DJ · producer-DJ). For each: their workflow, what hurts, what they value.
- **Define the scoring rubric** (see below) and the possible **verdicts**.
- Identify the **domain invariants** that must remain true regardless of scope (Rekordbox safety, local files playable on CDJ, preservation of cues/beatgrids/My Tags during writes).

**Phase B — Value Audit of EXISTING Features.**
For **each** feature identified in Phase 1, produce a fact sheet:
- short description + location (`file:line`);
- utility & personas concerned;
- **redundancy vs native Rekordbox** (complement / partial duplicate / total duplicate; free or paid) and vs competitors (Lexicon, MIK, DJ.Studio, Mixxx…);
- interest/differentiation;
- **score** (rubric below);
- **verdict**: `KEEP` / `MERGE` (with which other one) / `SIMPLIFY` / `REMOVE` / `TO-DECIDE` (question asked).
End with a ranking of features from most to least justified.

**Phase C — Opportunity Discovery (In-Depth Research).**
Start from the existing features + Appendices B/C/D, then **dig through the web and GitHub**. Build a **catalog of candidate features**, each with: description, who already does it (URL/project), personas served, and what makes it relevant for Syncbox. Cover at least: advanced library hygiene, sourcing/acquisition, set preparation & harmonic mixing, backup/portability, metadata/analysis, and any unexpected angle that emerges from the research.

**Phase D — Candidate Scoring & Prioritization.**
Apply the same rubric to the candidates. Classify them as: `MUST-ADD` / `SHOULD-ADD` / `NICE-TO-HAVE` / `DISCARD` (with reason: redundant, illegal/blocked, out of scope, disproportionate effort). For uncertain trade-offs → **ask me**.

**Phase E — Objective Overhaul (The Target).**
Synthesize a **target scope vision** for “an app useful to all”:
- what we **keep / merge / simplify / remove** from the existing product;
- what we **add** (by wave: essential v1, v2, later);
- what we **explicitly exclude** and why;
- the resulting **positioning** (how the app is useful and different from native Rekordbox + competitors);
- the **necessary generalizations** to move from a single-user tool to a multi-DJ product (path configuration, assumptions to remove, etc.).

**Phase F — Bridge to Phase 2.**
List the unresolved **open scope questions** (to be picked up by the architecture prompt), and the **reusable building blocks** identified (Appendix B + findings) without making an architecture choice.

### Scoring Rubric (To Apply in B and D)

Rate each criterion 0-5, then give a weighted overall score and explain it (no blind averaging):
- **Utility** — real value for the targeted DJ.
- **Audience breadth** — how many personas benefit from it (0 = only one, 5 = all).
- **Complementarity to native** — 5 = fills a real Rekordbox gap; 0 = total duplicate of a free native function. *(This is the inverse of redundancy.)*
- **Differentiation** — compared with competitors (Lexicon, MIK, DJ.Studio, Mixxx…).
- **Effort** (indicative, without deciding the technology) — 5 = low, 0 = very heavy.
- **Risk** — legal / technical / maintenance — 5 = negligible, 0 = blocking.

### Interaction Protocol

- Group your questions by theme, `AskUserQuestion`, max 4 per call; always propose a default recommendation **and** ask for validation.
- **Ask** when the trade-off depends on my tastes/priorities or when a feature is “strong but costly/risky.” **Do not ask** about what the research objectively resolves, nor about implementation details.
- Each response feeds the corresponding verdict and is recorded.

### Expected Deliverable

A single structured Markdown document — the **Syncbox Product Overhaul Report** — comprising:
1. Executive summary (the verdict in 10 lines: what we keep, what we add, the positioning).
2. Personas & evaluation framework (rubric, domain invariants).
3. Value audit of existing features (fact sheets + scores + verdicts + ranking).
4. Redundancy map vs native Rekordbox (and competitors).
5. Catalog of candidate features (from in-depth web/GitHub research, with URLs).
6. Candidate scoring & prioritization (MUST / SHOULD / NICE / DISCARD).
7. **Target overhaul**: v1/v2/future scope, exclusions, multi-DJ generalizations, positioning.
8. Interactive decision log (my responses).
9. Open questions & reusable building blocks for Phase 2.

Stay factual and cite your sources. Flag any uncertainty (e.g. free/paid status of a Rekordbox feature, reliability of a source). The report must be able to objectively convince a third party of the selected scope.

---

## Appendix A — Native Rekordbox: Base for Redundancy Analysis
*(dated June 2026 — to verify/update; sources: rekordbox.com, AlphaTheta support, Digital DJ Tips, DJ TechTools, DeeJay Plaza)*

**Natively covered and fairly complete (⇒ high redundancy risk):**
- **My Tag** (custom tags, 4 groups), comments, ratings, colors, genre — complete management/classification. *Strategy: write INTO My Tag rather than replace it.*
- **Intelligent / Smart Playlists** by rules (BPM, key, genre, My Tag, ratings, dates, play count…) auto-regenerated — **very complete**. *Strong redundancy if Syncbox recreates rule-based playlists.*
- **BPM / key / beatgrid / waveform / phrase** analysis, **vocal detection & STEMS** (now presented as available in Free, to reconfirm), **hot/memory cues, loops, active loops**.
- **Related Tracks / Track Match / Traffic Light** (harmonic suggestions), **Collection/Streaming Radar**.

**Covered but weak/rudimentary (⇒ real third-party added value possible):**
- **Duplicates**: no auto remover; only manual “Duplicate Search” by title, without audio fingerprint. → established third-party market.
- **Relocate / Relocate All** (missing files): exists but rudimentary and risky (first match, poor handling of homonyms/renames).
- Collection **Backup**: not automatic by default, restoration not very granular (cues live in `DjmdCues` of master.db, not in ANLZ).

**Paid / gated (⇒ duplicating for free may have value):**
- **Cloud Library Sync / CloudDirectPlay** (Free = max 10 tracks), **Collection Auto Upload** & **Device Library Backup** (Professional), **collaborative playlists**. *NB: new Core/Creative subscriptions suspended since March 2025 → real choice is Free vs Professional.*

**Native Spotify (reintegrated Sept. 24, 2025) — KEY POINT:** **live streaming only**, **no download / no offline / no USB-CDJ export**, limited cues/stems, no import into collection, Premium required, 51 markets, 3 software programs (RB/Serato/djay). → Does **NOT** duplicate a “Spotify → playable local file” flow; it is complementary.
*Sources: rekordbox.com/feature/overview · rekordbox.com/plan · rekordbox.com/en/2025/09/…spotify-support · djtechtools.com (09/24/2025) · deejayplaza.com (My Tag, Intelligent Playlist, Related Tracks, Track Match, Backup).*

## Appendix B — GitHub / Open-Source Ecosystem (Building Blocks to Reuse or Take Inspiration From)
*(to be extended by research)*
- **pyrekordbox** — https://github.com/dylanljones/pyrekordbox — Python, reads/writes master.db (SQLCipher) + XML + ANLZ; **foundation already used** by Syncbox.
- **OneTagger** — https://github.com/Marekkon5/onetagger — Rust/Vue, multi-source auto-tagging (Beatport/Discogs/MusicBrainz/Spotify), **ISRC matching**, **writing Rekordbox My Tags**, BPM/KEY detection. *Most relevant for the metadata layer.*
- **CueGen** — https://github.com/mganss/CueGen — .NET, **writes hot cues + My Tags + active loops** into Rekordbox (from Mixed In Key data). Proof of feasibility for auto-cues.
- **libKeyFinder** (Mixxx) — https://github.com/mixxxdj/libkeyfinder — C++, open-source key detection (alternative to Mixed In Key); + Essentia for BPM/key.
- **rekordbox-library-fixer** — https://github.com/koraysels/rekordbox-library-fixer — deduplication (metadata + audio), relocation, backups.
- **rekordcrate** (Rust, https://github.com/Holzhaus/rekordcrate) / **crate-digger** (Java, https://github.com/Deep-Symmetry/crate-digger) + **Deep Symmetry docs** (https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/) — USB/PDB/ANLZ export formats (read).
- Direct OSS Spotify↔DJ competitors: **PySync-DJ**, **DJ-Tools** (a-rich), **Trackmatch**, **rekordbox-spotify-downloader** (Dixter999) — playlist→download→analysis→tags→Rekordbox playlist patterns.
- Inter-app conversion: **dj-data-converter** (Traktor/RB/Serato), **libdjinterop** (Engine DJ), **traktor-nml-utils**, **serato-tools**.
- Downloaders: **spotDL**, **deemix** (bambanah / deemix-gui forks), **beatportdl**, **scdl**, **beets** (MusicBrainz tagging).
*⚠️ Most downloaders go through YouTube (limited bitrate) or sources in a gray area; writing to master.db requires Rekordbox closed + backup.*

## Appendix C — Competitors & Notable Features (Opportunities)
*(to be extended)*
- **Lexicon DJ** (https://www.lexicondj.com) — THE reference competitor. Sync/conversion between RB/Serato/Traktor/Engine/VirtualDJ/djay (preserves cues/loops/grids/tags). **Track Matcher** (matches a Spotify/Tidal/Apple/SoundCloud/YT/Beatport playlist against the local library, exports missing tracks), **Smart Fixes** (bulk metadata cleanup), duplicates by audio signature, robust relocate, **Energy/Danceability/Popularity/Happiness**, auto-cues, Beatport purchase that **automatically replaces** the streaming version, cloud backup, watch folder, CSV/M3U8/HTML/PDF export, playlist occurrences.
- **Mixed In Key** (https://mixedinkey.com) — key/Camelot, **Energy 1-10**, **8 auto-cues**, **Mashup Studio** (suggests tracks compatible by key+energy+BPM).
- **DJ.Studio** (https://dj.studio) — set preparation on a timeline, **AutoMix/Solver** (harmonic + BPM ordering), AI stems, RB export with hotcues, tracklist/video export.
- **MIXO** (https://www.mixo.dj) — cloud-first library, **mobile editing** (cues/ratings/comments from the phone), sync via Drive/OneDrive/Dropbox.
- **Mixxx** (https://mixxx.org) — OSS: crates + smart crates, **MusicBrainz fingerprinting**, **ReplayGain** (loudness normalization), Auto DJ.
- **Engine DJ / DJUCED** — Smart Crates, **suggestion assistant** (IMA), Energy, Auto-Gain.
- Web crate digging: **Tunebat**, **Mixgraph** (multi-dimensional transition score including **vocal fit**), **Chosic**.

**Consolidated list of opportunities (to score in Phase D):** deduplication by audio fingerprint · multi-source Track Matcher · bulk metadata cleanup/normalization · robust relocate + orphan files · Camelot wheel / harmonic suggestions · Energy levels + enriched analysis fields · auto-cues written into Rekordbox · vocal-fit · ReplayGain · versioned cloud backup · conversion to other DJ software · mobile editing · Beatport purchase with auto replacement · setlist AutoMix/Solver · tracklist export/sharing · occurrence/“never played”.

## Appendix D — DJ Pain Points & Wishlist (Market-Validated Demand)
*(to be extended; proof = number of paid tools per pain point)*
1. **Library hygiene** (acoustic duplicates, missing files after moving disks, inconsistent tags/genres, missing metadata) — **the #1 pain point**, an entire paid market around it (Lexicon, Music Library Doctor, DJ Duplicate Cleaner, RCT).
2. **Fear of database corruption** → need for automatic **versioned** backup with granular restore (cues are in master.db, not recoverable from ANLZ).
3. **Cross-app/device portability** without loss (RB↔Serato↔Engine↔Traktor) — core of Lexicon; OneLibrary (AlphaTheta+NI+Algoriddim) is partial/criticized.
4. **Streaming→playable library sourcing**: the 2025 Spotify reintegration covers neither offline, nor editing, nor USB → need for intact “real files.” Underexploited lead: **ISRC matching** to the equivalent lossless purchase (Beatport/Beatsource/Juno).
5. **Set preparation**: smart crates (unplayed, warm-up/peak, energy stages), planning the energy/harmonic arc; reliable “**never played tracks**” filter.
6. **Tagging transitions** (pairs of tracks that work together) — almost nonexistent elsewhere, potential differentiator but niche.
7. **Key/BPM/beatgrid accuracy** on complex tempos — distrust of native analysis (hence the massive use of MIK).
8. **USB export / Device Library (Plus)** friction, history management.
*Sources: forums.pioneerdj.com · cflo/reallychrism (substack) · digitaldjtips.com · djtechtools.com · cdm.link · lexicondj.com · musiclibrarydoctor.com · github.com/edkennard/rekordbox-repair. (Reddit not directly citable — blocked; the strongest proof remains the number of paid third-party tools per pain point.)*

## ── END OF PROMPT ──
