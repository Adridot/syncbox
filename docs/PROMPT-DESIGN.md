# PROMPT-DESIGN — Syncbox UI/UX Design (design phase, before the build)

> **Historical design prompt.** Its macOS+Windows framing predates the macOS
> v1 owner override. The implemented UI and release scope are defined by
> SPEC-UNIFIED, PROMPT-05, and the current source/tests.

> **How to use it.** Paste this prompt into a **Claude Design** session (clickable mockups). It **precedes** [PROMPT-03-build.md](PROMPT-03-build.md): screens/flows are designed first, then coded. The spec that is authoritative for the **WHAT** (behavior, safety, data) is [SPEC-UNIFIED.md](SPEC-UNIFIED.md) — **do not re-debate it**. The design phase decides the **HOW** of the screens: this is exactly what SPEC-UNIFIED §9 (§10.9 UI/UX + §10.10 configurable matching) **delegates here**.
>
> **Expected deliverables** (two, one feeds the build):
> 1. **High-fidelity clickable mockups** (desktop, macOS + Windows), navigable flows, real states (empty / loading / error / success / warning).
> 2. **`docs/SPEC-DESIGN.md`** — a concise doc that freezes: screen map, navigation model, component inventory, visual tokens (colors/type/spacing/density), and **the decided §10.9 + §10.10 decisions**. This is the UI input for PROMPT-03.

---

## Mission

Design the **complete UI/UX** of **Syncbox** — an open-source **macOS + Windows** desktop app that maintains a DJ’s **Rekordbox** collection: syncs **Spotify playlists** (read-only), **maintains the collection** (duplicates, missing files, tags, bulk metadata cleanup **Smart Fixes**, **fake-320/FLAC detection**), and offers two paths for missing tracks: a **highlighted legal purchase path** (Beatport/Bandcamp links) and an **optional download module, OFF by default** (Deezer).

**Design goal**: **clear, safe, and explainable** flows, faithful to the product promise (“I tag my library and my events without ever risking my Rekordbox collection”). The design is **free in its aesthetics and screen structure**, but **bound by the UI safety guards** below — they have non-negotiable screen surface.

## Inputs (authority hierarchy)

1. **[SPEC-UNIFIED.md](SPEC-UNIFIED.md)** — authoritative for behavior: domain model (§4), invariants (§5), non-negotiables (§3). The design **dresses** these invariants and never contradicts them.
2. **[SPEC-01-syncbox.md](SPEC-01-syncbox.md) §8** — **current UI state + open directions** (9 screens, Pinia state-based navigation, shared components, identified inconsistencies). This is the **starting point to challenge**, not a constraint.
3. The rest of SPEC-01 / `_research`: only if a design question touches a precise constant or mechanism.

## The design is free on… / bound by…

**Free**: visual direction, structure and number of screens, navigation model (router/deep-link or state), grouping, density, onboarding, micro-interactions. Nothing existing is fixed.

**Bound (safety guards with UI surface — non-negotiable, from §3/§5)**:
- **“Rekordbox open” guard**: any mutation action is **blocked** if Rekordbox/rekordboxAgent is running, with a **friendly** message (no PID, no `/Applications/` path, no technical flag). This state must be **visible and understandable**, not a dry error.
- **`dry-run → confirm → mutate` cycle** (Smart Fixes, deletes, dedup, events): the user **previews** the exact effect (per track: field, before → after) **before** writing. The confirmation text reflects **exactly** the executed payload (never the opposite of the action — fixes B10).
- **`protected` excluded by default** from Smart Fix writes: including a protected track requires a **named opt-in, never checked by default, never remembered** between runs; the dry-run **lists by name** the protected tracks affected.
- **Irreversible deletion (file on cloud/exFAT volume)**: **warning + explicit consent BEFORE** the action (“the audio will be permanently lost on this volume”). Never an after-the-fact notification. The DB always remains reversible (soft-delete + backup).
- **Explainable duplicate keeper**: the keeper suggestion displays **the reason** (ordered priority scale: protected > file present > quality/bitrate > tie-breaker), not an opaque score. Confirmation **per group** (no 1-click bulk auto-resolve).
- **Fake-320/FLAC quality verdict**: signal in **3 levels** (`ok` / `lossy probable` / `uncertain`), never binary; `uncertain` is a cautious nuance, not an accusation.
- **Real progress**: every job bar/counter derives from the real SSE stream — **no fake bar** (fixes the existing fake progress). Health counters (Spotify/Rekordbox/downloads) **derived from a single source** (fixes divergent sidebar↔dashboard counters).
- **“Backend unavailable” state**: after restarts are exhausted, a clear state + “Restart” button. Design it as a real state, not a freeze.
- **Download module OFF by default**: **explicit** user activation (+ entry of their ARL). The **legal path (purchase links) is highlighted** as the default path for missing tracks; downloading is the opt-in option, never imposed or pre-activated.
- **FR/EN i18n**: every user-facing label must exist in parallel FR/EN (the design provides translatable strings, not hardcoded text in the image).
- **Secrets**: ARL / token fields are never displayed in clear text once entered (masked field + “configured” state).

## Screens & domains to cover (input, freely reorganizable)

Existing = **9 screens, state-based navigation** (no router). Functional domains to support, regardless of the chosen breakdown:
- **Library** — Spotify playlists followed continuously; tracks with statuses (`new → matched|conflict|ready|imported`, + `missing`, `removed_from_source`, `ignored`); default tags; review table (filters, ignore/restore, bulk tag editing in **delta add/remove**).
- **Events** — temporary imports (wedding, party) from playlist / empty / link; staging; apply creates a smart playlist under “Event Imports”.
- **Collection Health (Doctor)** — **Duplicates** (groups + explainable keeper), **Missing Files** (re-download / re-link / remove), **Untagged** (4 categories: junk < dup < alt < review), **Smart Fixes** (metadata cleanup dry-run→confirm→mutate), **backup management** (list / restore / rotation N) + **logs**.
- **Acquisition** — missing tracks: **purchase links (default)** + **Deezer download module (opt-in)**; unified jobs (event/library/collection) with SSE progress.
- **Settings** — Spotify credentials (OAuth PKCE), Deezer ARL (opt-in), 4 paths, backup retention, language, download module activation.
- **Onboarding** — first launch: connect Spotify → choose paths → (optional) download module → collection ready.

## Design Questions to DECIDE (and justify in SPEC-DESIGN.md)

These are the decisions SPEC-UNIFIED §9 explicitly delegates:

1. **§10.9 — Navigation & structure.** Router (deep-link/back) or state-based navigation? Persistence of the current screen between launches? Keep 9 screens (track A) or **group by task** (track B: a **unified acquisition center**; a **“Collection Health” hub** for Duplicates/Missing/Untagged/Smart Fixes/Doctor)? **Guided flows** (track C: linear onboarding, “sync source” / “create an event” flows) rather than drawer screens? Do the Download Center and event context overlap? Does system health deserve a dedicated screen or an indicator?
2. **§10.10 — Configurable matching.** Whether to expose to the user the thresholds (confidence **82**, ambiguity margin **6**, title/artist/duration weights) and the ISRC collision policy? If yes: where, in what form (advanced/hidden?), with what guardrails? The **algorithm invariants (§5.3) and single normalization (D19) remain untouchable** — only the **exposure** is at stake. An expected recommendation, not a catalog of options.

> Ponytail lens (to apply to the design too): do not draw a screen/setting “for later.” A matching-threshold panel exists only if you truly recommend it. The smallest set of screens that serves the real flows wins. Prefer a native feature (system state, standard field) to a custom component.

## Method

1. Read SPEC-UNIFIED §3/§4/§5/§9 and SPEC-01 §8. List the **existing inconsistencies** to fix (divergent counters, inconsistent “download ready” condition, divergent event status tones, fake bar, cross-filter selection acting on hidden rows).
2. Ask me (via question) **at most 3 decisions** you cannot make alone (e.g. visual ambition, audience, priority platform).
3. Propose a **direction** (screen map + navigation model + visual language) **before** producing all screens — so we validate the structure first.
4. Produce the **clickable mockups** covering the domains above, **with the states** (empty, loading, error, success, warning, RB-open-blocked, backend-down, dry-run/confirm).
5. Write **`docs/SPEC-DESIGN.md`**: screen map, decided navigation model, reusable component inventory, visual tokens, and the justified §10.9 + §10.10 answers. This is what PROMPT-03 will consume.

**Faithful reporting**: if a safety guard makes a flow heavy, say so and propose the best compromise — do not hide the friction, do not sacrifice the guard.
