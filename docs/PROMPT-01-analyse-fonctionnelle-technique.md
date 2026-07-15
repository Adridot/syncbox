# PROMPT — Exhaustive Functional & Technical Analysis of Syncbox
### Phase 1/2: reverse engineering for a clean rewrite

> **Historical prompt.** It describes the legacy Electron/Deemix repository
> analysis and is not a current implementation or release instruction.

> **How to use.** Open a Claude Code session at the repository root and paste everything that follows (starting from “── START OF PROMPT ──”). The result is a **specification document**, not code and not an architecture. It is the input for Phase 2 (architecture choices & development approach), which will be covered by a separate prompt.

---

## ── START OF PROMPT ──

### Context

You are analyzing **Syncbox**, a desktop application (Electron + Vue 3 + Python FastAPI service) that synchronizes Spotify playlists to a DJ’s Rekordbox collection, downloads missing tracks via Deemix/Deezer, and maintains the collection (duplicates, missing files, tags). The app was built through successive prompts and has accumulated bugs, inconsistencies, and debt. The final goal is to **rewrite it from scratch, functionally identical but without the inherited defects**.

This analysis is the **first of two steps**:

1. **(you, now)** Exhaustively understand what the app does, how it behaves, how it is built, what is broken, and **decide with the user what to keep / remove / change**. Produce a functional + technical specification.
2. **(later, another session)** Based on your spec, design the target architecture and development approach.

### Your Role and Stance

You are a product analyst **and** a senior reverse-engineering engineer. You are rigorous, factual, and skeptical: you describe what *is*, not what *should be*. You are not impressed by the existing code — it is a source to audit, not a source of truth.

### Golden Rules — NON-NEGOTIABLE

1. **You do NOT choose the stack or target architecture.** No “we should use X”, no “let’s rewrite in Y”. You may *note technical observations* and *list open options*, but any architecture decision is deferred to Phase 2. If you catch yourself writing a stack recommendation, stop and turn it into an *open question*.

2. **When in doubt, ASK.** As soon as a feature, behavior, or data item could reasonably be *kept as is*, *removed*, *simplified*, or *modified* — and you cannot decide alone with certainty — ask the user (via `AskUserQuestion`, in grouped thematic batches). Never assume what is valuable to them. When hesitating between “ask” and “decide alone”: ask.

3. **Everything is anchored in the real code.** Every feature, rule, or contract you assert must point to evidence (`file:line`). Do not invent any feature. If something seems to exist but you cannot find it, mark it as *to confirm*, not as fact.

4. **Separate three things that are easily conflated:**
   - what the app **does today** (observable),
   - what is **intentional** vs what is a **bug / side effect / debt**,
   - what we **want** in the rewrite (keep / remove / change).
   Never mix these three registers in the same sentence without signaling it.

5. **UI/UX is an OPEN topic, not a given.** Describe the current organization (pages, menus, navigation, states) and suggest *directions*, but do not lock anything in: page distribution, menu hierarchy, and flows are explicitly “to be redefined in the design phase”. The user is not certain they are relevant — treat them as hypotheses to challenge, not as constraints.

6. **Capture the BEHAVIORAL CONTRACT, not the implementation.** What must survive a rewrite are the *business rules, invariants, and edge cases* (e.g. “Rekordbox mutations are blocked if Rekordbox is running”, “deletions are reversible via backup”), not how the current code implements them. Describe the *what* and the *why*, leave the *how* to Phase 2.

7. **Do not write code and do not modify anything.** Read-only. The only artifact you produce is the specification document (+ the questions asked to the user).

### Method (Analysis Phases)

Work in this order. You may parallelize exploration, but respect the logical sequence of the deliverables.

**P0 — Reconnaissance.** Map the repository: layers (renderer / Electron main / Python service), tree structure, entry points, build scripts, dependencies and their role. Confirm/complete the starting appendix below instead of starting from scratch.

**P1 — Functional Decomposition.** Inventory *all* user-exposed features (the locale files `en.ts`/`fr.ts` are an excellent feature index). For each: what it does, where it lives, its status (complete / half-finished / dead). List screens, navigation, and key end-to-end flows.

**P2 — Behavioral Specification (the “core” to preserve).** For each domain, extract the **business rules, invariants, safety guarantees, and edge cases**: blocking conditions, operation order, reversibility, conflict handling, sort priorities, matching strategies, etc. This is the most valuable part of the spec.

**P3 — Technical Reverse Engineering.** Document the layers and especially the **internal contracts**: IPC channels (renderer↔main), HTTP endpoints (renderer↔service), SSE streams, spawn environment variables, payload shapes. Document the data layer (persistence, caches, sources of truth) and Rekordbox/Spotify/Deemix access. Describe *the contracts*, not the code quality (that comes in P4).

**P4 — Bug & Pain Catalog (what MUST NOT be reproduced).** List defects, classified as: `bug` (incorrect behavior) / `fragile` (race, missing error handling, hidden assumption) / `debt` (inconsistency, duplication, unjustified complexity) / `unfinished` (half-built feature). For each: observable symptom, `file:line`, probable cause, and user impact. Use the “known debt” appendix as a starting point, verify it, and extend it.

**P5 — Domain & Data Model.** Describe the domain that must survive regardless of technology: entities (source/playlist, track, event, acquisition job, tag, backup…), their relationships, lifecycles and statuses, matching identities (ISRC, fuzzy). This is the reusable business foundation.

**P6 — Keep / Remove / Change Decisions (INTERACTIVE).** For each feature and each notable behavior, propose a decision and — at the slightest doubt — **ask the user**. Record each answer in a *decision log*. See the taxonomy and protocol below.

**P7 — UI/UX: Current State + Open Directions.** Describe the current organization, then propose 2-3 alternative structuring directions (without deciding), and list open design questions. Mark everything as “hypothesis to validate in the design phase”.

**P8 — Constraints & Non-Negotiables.** What the rewrite *must* respect no matter what: Rekordbox safety (SQLCipher, blocking if RB is open, backups), unavoidable external dependencies (pyrekordbox, Deemix, Spotify OAuth), packaging constraints (embedded Python binary), platform (macOS), etc.

**P9 — Open Questions for Phase 2.** The explicit list of *undecided* architecture and product decisions, ready to be carried into the architecture prompt. This is the bridge to the next step.

### Interaction Protocol (When and How to Ask)

- **Group your questions by theme** and ask them with `AskUserQuestion` (max 4 per call). Do not flood the user with one question at a time.
- **Ask a question as soon as the answer changes what we keep/remove/change**, i.e. when: (a) a feature’s value is ambiguous, (b) a current behavior could be a bug *or* intentional, (c) two features overlap (which one to keep?), (d) complexity exists without visible justification (remove it?), (e) a feature seems unfinished (finish it, cut it, or rethink it?).
- **Do NOT ask** what the code answers unambiguously, micro implementation details, or stack choices (deferred). For everything else, recommend a default option *and* ask for confirmation.
- **Every answer goes into the decision log**, with its justification.

### Decision Taxonomy (to apply to each feature/behavior)

`KEEP` (as is) · `KEEP-BUT-FIX` (the behavior remains, the bug goes away) · `SIMPLIFY` (keep the intent, reduce the surface area) · `CHANGE` (revise the behavior) · `REMOVE` · `TO-DECIDE` (question asked to the user).

### Expected Deliverable

A single structured, dense, navigable Markdown document — the **functional & technical specification of Syncbox** — including at minimum:

1. Executive summary (what the app is, in 10 lines).
2. Functional inventory (features × status × location).
3. Behavioral specification by domain (rules, invariants, edge cases).
4. Technical map & internal contracts (IPC, HTTP, SSE, data, externals).
5. Defect catalog (bug / fragile / debt / unfinished) with `file:line`.
6. Domain & data model.
7. **Decision log** keep/remove/change (with the user’s answers).
8. UI/UX: current state + open directions.
9. Constraints & non-negotiables.
10. **Open questions for Phase 2 (architecture).**

The document must be readable on its own by someone who has never seen the code, and sufficient to rewrite the app functionally identically. Stay factual; explicitly flag anything assumed or to be confirmed.

---

## Appendix A — Starting Map (to verify and deepen, not copy)

> This is a starting point from a first exploration. Confirm every element in the code, correct anything false, and **complete** it — do not simply reuse it.

### Screens (~9, navigation via Pinia `useUiStore` state, no Vue Router)
Dashboard · My Library (Spotify playlist tracking, master-detail) · Events (DJ sets, creation in 3 modes, “Live Import” M3U8) · Download & Match (Deemix queue, conflict resolution) · Duplicates (ISRC/fuzzy scan, auto-resolution) · Missing Files (re-download / re-link / soft-delete) · Untagged (diagnostic + suggestions + bulk tagging) · Doctor (diagnostics, Rekordbox backups, restore, logs) · Settings (Spotify, Deemix/ARL, paths, EN/FR language, backup/restore).

### Functional Domains
Synchronization & acquisition (playlist tracking, source/all sync, auto-tag MyTags) · Events/DJ sets (Spotify analysis, workspace, staging, Live Import without DB writes) · Download & matching (Deemix, job statuses, ambiguous conflict resolution via Deezer search) · Collection management (duplicates, missing files, untagged) · Config & access (language, Spotify OAuth, paths, backup/restore) · System & monitoring (API/Rekordbox/Deemix/Spotify health, collection stats, diagnostics).

### Stack
Electron 42 (main TS, preload CJS) · Vue 3 + Pinia 3 (~6 stores) **and** TanStack vue-query 5 (deliberate but partial coexistence) · vue-i18n 11 (FR/EN) · Tailwind 4 · electron-store 8 · Python 3.12+ FastAPI/uvicorn service · pyrekordbox 0.4.4 (SQLCipher master.db) · mutagen · rapidfuzz · httpx · pydantic · build: Vite/electron-vite + PyInstaller + electron-builder (macOS DMG, Python binary in extraResources).

### Communication Between Layers
Renderer↔Main: IPC via `window.desktop.*` (settings get/set/reload, getApiBaseUrl, openExternal/openPath/openLogs, deemix status/launch/install/onProgress). Renderer↔Service: HTTP fetch (`/api/...`) on port `RBSYNC_SERVICE_PORT` (8765), base URL obtained through IPC. Main↔Service: `child_process.spawn` (dev: `uv run uvicorn`; packaged: PyInstaller binary) with env `RBSYNC_DATA_DIR / _SERVICE_PORT / _APP_VERSION / _LOG_DIR`. Real-time: SSE `/api/acquisition/stream` (4s refresh, client-side reconnect).

### Sources of Truth / Data
electron-store (`syncbox-settings.json`, instant synchronous read) ↔ service SQLite (`syncbox.sqlite3`, source of truth for OAuth/tasks/metadata, seeded on first run) ↔ vue-query (network cache) ↔ `RekordboxAdapter` memory caches (key = master.db mtime+size). Settings reconciliation on boot through one-way *pull* from the service.

## Appendix B — Known Debt (to verify, extend, and quantify in P4)

- **Inconsistent split data layer**: Duplicates/Doctor/Missing/Untagged in vue-query; Events/Library/Settings in Pinia + manual HTTP. `useSystemStatusQuery` writes directly into the store, `useRefreshManager` polls in parallel → double polling, inconsistent invalidation, ambiguous source of truth.
- **Fragile settings reconciliation on boot** (`electron/main.ts` ~75-105): one-way pull; if the service is down on first boot, risk of config overwrite without merge.
- **Service spawn without guardrails** (`electron/main.ts` ~131-180): no existence check for `uv`/binary, no error handler, unmanaged logs; `waitForService` 30s then silent degradation (`api = null`).
- **Event races** (`stores/events.ts` ~68-101): `requestedEventId` limits UI flash but not obsolete slow requests (no abort of in-flight requests).
- **Rekordbox cache invalidation by mtime** (`rekordbox/adapter.py` ~58-63): incorrect hit if RB writes during a read; fixed retries ~3.6s max.
- **Generic error handling** (`stores/ui.ts` withErrorToast; `lib/api/client.ts` parse): `.message` without context; parser breaks if the service returns non-JSON (e.g. Deemix error page).
- **Paths**: `DEFAULT_STORAGE_ROOT` hardcoded for this user (Dropbox); symlinks/mounts poorly handled; `validatePath` service-side only, no early renderer feedback; also see project memory on Rekordbox path resolution (volume-relative vs absolute paths).
- **SSE / acquisition refresh**: no payload validation before parsing; reconnect without jitter; 4s refresh loop silently serving stale data if a pass fails.
- **Deemix installer** (`electron/deemix.ts`): best-effort, no retry, no cleanup of the `.dmg` on failure.
- **Opaque job payloads** (`models.py`/`acquisition.py`): `payload: dict` without schema → silent front-end breakage if the shape changes.
- **Backups on cloud storage**: partially broken in dev build (macOS blocks terminal access to cloud folders); OK in packaged app.

## Appendix C — Decisions Likely to Submit to the User (P6)

Starting list of points to clarify — complete it during the analysis:

- Keep the **Pinia + vue-query coexistence** or converge? (project memory indicates it is *intentional* — to reconfirm in the context of a rewrite).
- **Live Import M3U8** (workaround for DB writing when RB is open): feature to preserve? Central or secondary?
- Complexity of the **Untagged diagnostic** (junk/duplicate/alt/to-review categories): keep everything or simplify?
- **Duplicate auto-resolution**: keep the automatic “keeper” (lossless > cues > permanent) or move everything to manual review?
- **Reversibility** (soft-delete + backups + restore via Doctor): scope to preserve?
- **Deemix installation from the app**: keep it, or assume Deemix is already installed?
- **Bilingual FR/EN**: maintained? Other languages?
- **In-app Spotify OAuth** vs app-only mode: both or only one?
- **Backup retention**, collection stats, health dashboard: desired level of detail?
- **Platform** scope: macOS only, or target Windows/Linux (strong Phase 2 impact)?

## ── END OF PROMPT ──
