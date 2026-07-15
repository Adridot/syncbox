# PROMPT-02 — Unification & Finalization of the Syncbox Specs (ultracode + ponytail)

> **Historical prompt.** Its output has been superseded by the current
> SPEC-UNIFIED owner override and PROMPT-05 release contract.

> **How to use it.** Paste this prompt into a Claude Code session. The word **`ultracode`** activates multi-agent orchestration (Workflow). The **ponytail** module must remain active throughout (`/ponytail full`). Every structural choice **goes through me** via `AskUserQuestion` — do not decide anything alone.

---

ultracode — `/ponytail full`

## Mission

Unify **`docs/SPEC-01-syncbox.md`** (functional/technical spec, focused on its **Phase 2 open questions §10**, the **decision log §7 (D1–D25)**, the **non-negotiables §9**, the **domain model §6**) and **`docs/SPEC-02-architecture.md`** (target architecture, **4 forks A–D**, de-risking order §5) into **a single coherent, complete, contradiction-free spec**.

The final goal: a “perfect and unified” spec that resolves **all** outstanding questions — through **sourced state-of-the-art research** whenever there is a choice, and through **my validation** on each arbitration — to serve as input for the **ideal app-building prompt** (final deliverable).

## Non-Negotiable Principles (Apply to Every Phase)

1. **Ponytail lens on EVERY choice.** Climb the ladder: (1) should this component/feature exist? (2) does the stdlib do it? (3) does a native platform/OS feature cover it? (4) is an already installed dependency enough? (5) one line? (6) otherwise, the minimum that works. **Explicitly challenge SPEC-02**, which “sets maintainability aside” and “assumes increased complexity”: for every proposed change (Tauri, JSON-RPC stdio, embedded deemix, etc.), first ask *“vs what already works today, should this change happen?”*. Reintegrate maintainability as a guardrail. Run `/ponytail-review` on the retained architecture choices and `/ponytail-audit` (mental) on the surface area of the final spec.
2. **No choice without sourced state of the art.** Every option and every recommendation is based on **real, dated, verified** sources (web). No memory-based claims about a tool/lib/version.
3. **Everything goes through me.** Structural forks and product/functional choices are presented via `AskUserQuestion` (ponytail recommendation **first**, sourced alternatives, trade-offs vs the 3 priorities *robustness > lightness > performance* **and** maintainability impact). Do not freeze anything without my answer.
4. **Preserve the SPEC-01 §9 non-negotiables**: Rekordbox safety (RB-closed guards, `_mutate`, backup-before-mutation, soft delete, load-bearing status integers), volume-relative/absolute path resolution, “never move files” + TCC quirk, and the **`service/tests/` test contract** as the behavior reference.
5. **Faithful reporting.** If a question remains without a reliable answer after research, say so — do not invent a consensus.

## Already Identified Contradictions & Gaps (Starting Point — to Complete, Not Presume Exhaustive)

- **Fork A — inconsistent label in SPEC-02.** §4 defines `A2 = exchange formats only`; §2.4 + the “validated decisions” table use `A2 = master.db in place only, without XML`. Two meanings for the same label → decide the wording **and** confirm the real decision.
- **“4 forks to validate” vs “Validated decisions.”** SPEC-02 says both. Clarify the status: are these forks still open, or already decided and to be ratified?
- **Fork C1 ⟂ OAuth.** C1 (JSON-RPC stdin/stdout, **no HTTP server**) breaks the Spotify callback that SPEC-01 §3.9 pins to `http://127.0.0.1:8765/...`. Without an HTTP server, no loopback redirect → resolve the interaction (dedicated ephemeral OAuth loopback listener? another mechanism?).
- **Questions still open after SPEC-02** (SPEC-01 §10) not resolved by the architecture: §10.4 secrets at rest (OS keychain vs encrypted DB), §10.5 schema migration tool, §10.6 multi-OS abstraction (Windows RB process detection, OS trash, system paths), §10.7 service port + OAuth callback, §10.9 UI/UX structure (§8.2 tracks A/B/C), §10.10 configurable matching (thresholds 82 / margin 6 / weightings; single ISRC collision policy).
- **Ponytail vs SPEC-02 tension**: every “chosen complexity” (Tauri shell, rewritten transport, embedded downloader) must survive the question “YAGNI / is what already works enough?”.

## Orchestration (Workflow)

**Phase 0 — Ingestion & Mapping** *(parallel agents, read-only)*
- SPEC-01 reader → extract: D1–D25 (status keep/change/remove), open questions §10, non-negotiables §9, domain model §6, behavior contract §3.
- SPEC-02 reader → extract: verdicts by layer §2, forks A–D + status, validated decisions, de-risking order §5.
- `docs/_research/` + `docs/_analysis/` reader → inventory sources already gathered (avoid re-searching what is already acquired; identify outdated/to-refresh material).
- **Output**: a **unified matrix** `{ topic → SPEC-01 position → SPEC-02 position → contradiction? → status (decided / to-research / to-validate) }`.

**Phase 1 — Diff, Contradictions, Gaps** *(barrier: requires all of Phase 0)*
- A synthesis agent cross-checks both specs and produces: (a) **complete** list of contradictions (seed above + new ones); (b) questions **still open**; (c) choices whose **state of the art is missing**; (d) ranking by priority and action type.

**User Gate 1** *(`AskUserQuestion`)* — present me with the matrix + the list of contradictions/questions; confirm scope, priorities, and any strong preference **before** heavy research.

**Phase 2 — State-of-the-Art Research** *(pipeline: one thread per question/fork; verify as soon as a research task finishes)*
- Per topic: one agent researches (`deep-research` style) WebSearch/WebFetch fan-out → **sourced + dated options matrix** + **ponytail recommendation** (the laziest option that satisfies the non-negotiables).
- **Adversarial verify** per topic: a skeptic verifies that sources are real/up to date and that the “lazy option” breaks no non-negotiable (default: refute). Majority required to validate.
- **Pre-identified topics** (complete according to Phase 1): secrets at rest macOS+Windows; lightweight SQLite migration tool; Rekordbox process detection on Windows + cross-platform OS trash; OAuth loopback **without** HTTP server (Fork C1 impact); 2025–2026 state of Tauri sidecar signing/notarization (#11992); deemix vs streamrip (maintenance + current Deezer API + GPL/DMCA legal dimension); PyInstaller `--onedir` vs Nuitka (measured size/cold start); configurable matching model (whether to expose thresholds).

**User Gate 2** *(`AskUserQuestion`, in batches)* — for each fork/choice: ponytail recommendation **first**, alternatives, trade-offs vs priorities + maintainability, sources. Collect my decisions.

**Phase 3 — Unified Spec Synthesis**
- Produce **`docs/SPEC-UNIFIED.md`**: a single spec integrating D1–D25, decided forks, researched + validated answers, non-negotiables, domain model, target architecture. Forks rewritten with **one coherent label only** and **clear status (decided)**. Each ponytail simplification carries a `ponytail:`-style rationale (what is rejected, when to add it). Update/remove SPEC-01 §10 and SPEC-02 §4 to point to the final decision (no double source of truth — apply the principle to the docs themselves).
- Enrich `docs/_research/` with the new sourced research.

**Phase 4 — Adversarial Review (Loop Until Convergence)**
- *Completeness critic*: what is missing? residual contradiction? unanswered §10 question? unsourced choice? §9 non-negotiable lost along the way?
- *Ponytail-review*: where is the spec still over-designed? what should be removed/merged?
- Loop again while: contradictions ≠ 0, open questions ≠ 0, or untreated ponytail findings.

**Phase 5 — The Ideal Build Prompt**
- From the frozen `SPEC-UNIFIED.md`, generate **`docs/PROMPT-03-build.md`**: the prompt that enables building the app (final objective), including the decided stack, de-risking order (POC first), non-negotiables, test contract, and the ponytail lens as an implementation constraint.

## Deliverables

1. `docs/SPEC-UNIFIED.md` — single, complete, sourced spec, **zero contradictions**, decided forks.
2. Consolidated decision log (ratified forks A–D + answers to the 10 §10 questions), traceable.
3. Enriched `docs/_research/` (new dated/sourced research).
4. `docs/PROMPT-03-build.md` — the final build prompt.

## Interaction Rules

- **Every structural or product fork/choice → `AskUserQuestion`**, ponytail recommendation first. Do not move into Phase 3 without my decisions.
- Ponytail active: deliverable first, short explanation afterward. No prose defending a simplification — the simplification is justified by its brevity.
- Language: **French** (consistent with the existing docs).
