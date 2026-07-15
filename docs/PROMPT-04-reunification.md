# PROMPT-04 — Syncbox Specs Reunification: Overhaul Scope × Architecture (ultracode + ponytail)

> **Historical prompt.** It records a prior specification-reconciliation step;
> it is not an instruction for the current macOS v1 release.

> **How to use it.** Paste this prompt into a Claude Code session at the repository root. The word **`ultracode`** activates multi-agent orchestration (Workflow). The **ponytail** module must remain active (`/ponytail full`). Any structural choice **goes through me** via `AskUserQuestion` — do not decide anything alone.

---

ultracode — `/ponytail full`

## Mission

The product-scope decisions in **`docs/OVERHAUL-01-valeur-features.md`** (06/16, the most recent) were made **after** **`docs/SPEC-UNIFIED.md`** and have **not been propagated back** into the architecture spec or the build prompt. The two sources of truth have diverged.

**Fold OVERHAUL-01 into SPEC-UNIFIED**, resolve the contradictions introduced by the overhaul, **complete `docs/_research/`** for the new building blocks, then **regenerate `docs/PROMPT-03-build.md`** — to obtain **a single coherent spec, with no contradictions, carrying the real v1 scope** (sync + hygiene + safety + the 5 additions), ready to build.

**Single-source-of-truth principle maintained**: the output **updates `SPEC-UNIFIED.md` in place** (not a 3rd doc). OVERHAUL-01 remains the **record** of value decisions; SPEC-UNIFIED remains the consolidated **architecture+product source of truth**.

## Inputs (Authority Hierarchy)

1. **`docs/OVERHAUL-01-valeur-features.md`** — most recent **scope/value** decisions (§7 target scope, §8 interactive journal, §9 open questions + reusable building blocks). **Authoritative for the WHAT/the scope.**
2. **`docs/SPEC-UNIFIED.md`** — **authoritative for the architecture** (forks A–D §7.1, answers §10 in §7.2, D1–D25 §7.3, non-negotiables §3, domain model §4, invariants §5, architecture §6, de-risking §8). To be **updated**, not re-debated.
3. **`docs/SPEC-01-syncbox.md`** — canonical source for **constants** (thresholds, weightings, buckets) + observable behavior.
4. **`docs/_research/00–10`** — existing sourced state of the art (to be **completed**, not redone).
5. **`docs/_analysis/00–15`** — `file:line` evidence of existing behavior.

In case of **scope** conflict: OVERHAUL-01 > SPEC-UNIFIED. In case of **architecture/invariant** conflict: SPEC-UNIFIED > SPEC-01 > research > analysis.

## Non-Negotiable Principles (Every Phase)

1. **Ponytail lens on EVERY added feature.** For each of the 5 new ones (Chromaprint, Smart Fixes, fake-320, legal Track Matcher, streamrip), climb the ladder: (1) must it exist in v1? (2) stdlib? (3) native OS/Rekordbox feature? (4) already bundled dependency (numpy/pyrekordbox/mutagen are **already there**)? (5) one line? (6) the minimum. Every new building block weighs on the sidecar (POC measurement #3) and must justify itself.
2. **Preserve ALL SPEC-UNIFIED §3 non-negotiables**: Rekordbox safety (RB closed guard, `_mutate`, backup-before-mutation, soft-delete, load-bearing integers 256/258), volume-relative/absolute path resolution, “never move files” + TCC quirk, secrets never in cleartext, local-first, cross-OS, FR/EN i18n. **Any new feature that writes `master.db` (e.g. Smart Fixes) goes through `_mutate` — no escape hatch.**
3. **No choice without sourced state of the art.** The 5 new building blocks have **no `_research/` file**. Every recommendation relies on real, dated, verified sources (web), not on memory.
4. **Everything goes through me.** Structural or scope forks/choices via `AskUserQuestion` (ponytail recommendation **first**, sourced alternatives, trade-offs vs priorities *robustness > lightness > performance* + maintainability).
5. **Faithful reporting.** Question without a reliable answer after research → say so.

## Already Identified Divergences (Starting Point — Complete, Do Not Assume Exhaustive)

1. **Library acquisition — fixed decision vs delegated.** OVERHAUL §8 decides **streamrip**; SPEC-UNIFIED §6.5/§7.1 leaves it as “streamrip vs deemix-fork delegated to POC”. **Align**: streamrip selected; the POC no longer validates *the library choice* but the **embedding cost** + **full-track viability**. Reconsider the “Deezer” framing → streamrip is **multi-service** (Qobuz/Tidal/Deezer/SoundCloud): should Fork D remain Deezer-only or open up? (→ question).
2. **5 v1 features absent from the architecture.** Chromaprint dedup (A2), Smart Fixes (A1), fake-320/FLAC (A3), legal Track Matcher (B2) — **nothing** in the §4 domain model, §5 invariants, §6 architecture, or PROMPT-03 phases. To **integrate**: entities/statuses, behavioral invariants, dependencies, place in the architecture, build phase.
3. **Acquisition module OFF by default + legal path.** OVERHAUL insists: OFF by default, legal Track Matcher (ISRC purchase links) highlighted as an alternative. SPEC-UNIFIED §6.5 says “optional” without these two points. **Reword Fork D.**
4. **Factual correction — ANLZ cues.** OVERHAUL §2.3-4/§9.1: cues live in `master.db djmdCue` **AND** in ANLZ — contradicts SPEC-01 §3.1. **Consequence to decide**: does the §3.1/§5.1 backup (master.db only) **lose ANLZ cues** on restore? Extend the backup to ANLZ, or document the limitation? (→ question, consistent with memory `cues-in-masterdb-and-anlz`).
5. **Spotify dependency (Feb. 2026).** OVERHAUL §9.5: Web API hardening. Confirm that only `playlist-read-*` are used, no dead endpoint (audio-features, recommendations). Annotate §5.9.
6. **Missing research.** No `_research/` covers: Chromaprint/pyacoustid (license, `fpcalc` packaging, offline); fake-320/FLAC FFT algorithm; Beatport API v4 (approval portal, ToS, Bandcamp/Juno alternatives by ISRC link); streamrip embedding (CLI subprocess vs API, credentials by service); (optional) AcoustID→MusicBrainz for ISRC enrichment.

## Orchestration (Workflow)

**Phase 0 — Ingestion & Divergence Matrix** *(parallel agents, read-only)*
- OVERHAUL-01 reader → extract the **target scope** (§7: KEEP/ADD/REMOVE/EXCLUDE by v1/v2/future wave), the §8 journal, the §9 questions, the §9.2 reusable building blocks.
- SPEC-UNIFIED reader → map where each feature **should** live: §4 domain model, §5 invariants, §6 architecture, §7 forks, §8 de-risking.
- SPEC-01 + `_analysis/` reader → constants/behaviors of KEPT features (do not lose the existing work while reintegrating).
- `_research/00–10` reader → inventory existing work (avoid re-researching) + identify stale items.
- **Output**: matrix `{ feature → overhaul decision → target SPEC-UNIFIED location → present? → action (integrate / realign / research / decide) }`.

**Phase 1 — Diff & Contradictions** *(barrier: requires all of phase 0)*
- A synthesis agent produces: (a) **complete** list of scope↔architecture divergences (seed above + new ones); (b) features without invariant/domain; (c) building blocks without research; (d) impacts on §3 non-negotiables (e.g. Smart Fixes × `_mutate`, Chromaprint × sidecar size).

**User Gate 1** *(`AskUserQuestion`)* — present me with the matrix + divergences; confirm the real v1 scope, and decide upfront: (i) Deezer-only Fork D vs multi-service streamrip; (ii) ANLZ backup or documented limitation; (iii) order/priority of the 5 additions (all v1 or some v2).

**Phase 2 — State-of-the-Art Research for New Building Blocks** *(pipeline: one thread per building block; verify as soon as research finishes)*
- Per building block (Chromaprint, fake-320 FFT, Beatport/legal, streamrip embedding, AcoustID if retained): `deep-research`-style agent → **sourced + dated options matrix** + **ponytail recommendation** (the laziest option that satisfies the non-negotiables and the sidecar budget).
- **Adversarial verify** per building block: a skeptic verifies real/up-to-date sources + that the recommendation breaks no non-negotiable and does not blow up the sidecar (default: refute). Majority required.
- **Output**: new files `docs/_research/11_*` … (one per building block), same dated/sourced format as 00–10.

**User Gate 2** *(`AskUserQuestion`, in batches)* — per building block: ponytail recommendation **first**, alternatives, trade-offs vs priorities + maintainability + sidecar weight, sources. Collect my decisions.

**Phase 3 — Integration into SPEC-UNIFIED** *(in-place update)*
- Update **`docs/SPEC-UNIFIED.md`**: add retained features to the **§4 domain model** (entities/statuses: e.g. duplicate group by fingerprint, Smart Fixes job dry-run→confirm→mutate, fake-320 verdict, missing→purchase links), to the **§5 invariants** (behavior + edge cases + `# ponytail:` for each simplification), to the **§6 architecture** (dependencies, location, isolation), to the **§7 forks** (reworded Fork D), to **§8 de-risking** (new POCs: offline fingerprinting, real ARL full-track already listed, `fpcalc` packaging). Realign §6.5 with streamrip, §5.9 with Spotify 2026, §3.1/§5.1 with the ANLZ correction.
- Update the **§0 decision status** and the **§7.3 journal** (new A1/A2/A3/B2 lines; reworded D-acquisition).
- Properly cross-link OVERHAUL-01 and SPEC-UNIFIED (scope ↔ architecture), without a double source of truth.

**Phase 4 — Adversarial Review (Loop Until Convergence)**
- *Completeness critic*: feature from §7 OVERHAUL not integrated? missing invariant for a feature that writes `master.db`? building block without research? §3 non-negotiable lost? residual contradiction?
- *Ponytail-review*: where does the spec over-design after the addition? which v1 building block should move down to v2? what should be merged?
- Loop while: divergences ≠ 0, non-integrated features ≠ 0, unsourced building blocks ≠ 0, or unaddressed ponytail findings.

**Phase 5 — Regenerate the Build Prompt**
- From the updated `SPEC-UNIFIED.md`, **regenerate `docs/PROMPT-03-build.md`**: integrate the 5 features into the phases (Phase 3 “business logic”: fingerprint dedup, Smart Fixes via `_mutate`, fake-320, Track Matcher; Fork D = streamrip), add the new POCs to Phase 0, update the definition of “done”. Keep the ponytail lens as an implementation constraint.

## Deliverables

1. **Updated `docs/SPEC-UNIFIED.md`** — real v1 scope integrated, streamrip aligned, ANLZ/Spotify corrected, **zero contradiction**, each addition with invariant + `# ponytail:`.
2. **`docs/_research/11_*…`** — one sourced/dated file per new building block.
3. **Regenerated `docs/PROMPT-03-build.md`** — phases + POCs + forks up to date.
4. Divergence matrix + consolidated decision journal (traceable).

## Interaction Rules

- **Any scope or structural choice → `AskUserQuestion`**, ponytail recommendation first. Do not move to phase 3 without my decisions.
- Ponytail active: deliverable first, short explanation after; simplification is justified by its brevity.
- Language: **French** (consistent with the existing docs).
