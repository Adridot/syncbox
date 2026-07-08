# docs — specification & decision record

Authority order (when documents disagree, the higher one wins):

1. **[SPEC-UNIFIED.md](SPEC-UNIFIED.md)** — the WHAT: features, invariants,
   safety model, architecture forks A–D, owner decisions D1–D25, §11
   post-design amendments. The single authority.
2. **[SPEC-DESIGN.md](SPEC-DESIGN.md)** — navigation, screens, configurable
   matching (design phase outcome; the spec wins over the mockup).
3. **[M4-PLAN.md](M4-PLAN.md)** / **[M5-PLAN.md](M5-PLAN.md)** — milestone
   maps (shell+UI, packaging): increment sequences and settled arbitrations.
   Maps, not authorities.

Context:

- [SPEC-01-syncbox.md](SPEC-01-syncbox.md) — the original long-form spec
  SPEC-UNIFIED distilled; superseded except as a constants reference.
- [SPEC-AI-WORKFLOWS.md](SPEC-AI-WORKFLOWS.md) — how the build itself was
  run (clean-room milestones, gates, review protocol).
- [REMARKS.md](REMARKS.md) — owner test feedback that drove the M4 redo.
- [PROMPT-*.md](.) — the actual session prompts used for each milestone.
- [_research/](_research/) — dated, sourced research notes behind every §6
  decision. Files `04*`, `10*`, `14*` document a download module that was
  **removed from scope for legal reasons** (SPEC-UNIFIED §6.5); they are
  historical only and must not be used as implementation references.
- [../poc/](../poc/) — de-risking proofs-of-concept; each folder carries a
  `VERDICT.md` with measurements and GO/NO-GO.
