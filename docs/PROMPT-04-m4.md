# PROMPT-04 — M4: Tauri v2 shell + Vue 3 UI

> **How to use.** Paste into a **fresh** Claude Code (Fable) session at the repo root, branch
> `build/clean-room-kit`. **Single-agent session by design**: this prompt deliberately does not
> contain the multi-agent keyword; do not launch workflows or agent fan-outs — the exploration
> was already done and distilled into [M4-PLAN.md](M4-PLAN.md). `/ponytail full` stays active.
> Interaction in **French**; all repository content in **English**.

## Mission

Execute milestone **M4** — the Tauri v2 shell and the Vue 3 UI — exactly as sequenced in
[M4-PLAN.md](M4-PLAN.md) (increments M4.1 → M4.13), implementing
[SPEC-DESIGN.md](SPEC-DESIGN.md) wired to the real sidecar REST/SSE surface on port 8765.
M1–M3 are closed (372 pytest green). The sidecar is off-limits **except** the composition root
(M4.1) and the five owner-approved gaps G1–G5 (M4.2), both specified in the plan.

## Authority hierarchy

1. [SPEC-UNIFIED.md](SPEC-UNIFIED.md) — product/architecture QUOI, §11 amendments included.
2. [SPEC-DESIGN.md](SPEC-DESIGN.md) + mockup `syncbox-ui-ux-design/project/Syncbox.dc.html` —
   UI contract. **Behavior and hierarchy only, never the literal CSS.** Spec beats mockup.
3. [M4-PLAN.md](M4-PLAN.md) — sequence, owner arbitrations, distilled inventory. A map, not an
   authority: if the plan seems to contradict a spec, the spec wins and you say so.

## Read first — token discipline

Read **once**, in this order, then build from memory + targeted lookups:

1. `docs/M4-PLAN.md` — the whole file (it is the distilled kit).
2. `docs/SPEC-DESIGN.md` — the whole file (279 lines, the M4 contract).
3. `docs/SPEC-UNIFIED.md` — **only** §6.3, §6.5, §6.6, §11.
4. `sidecar/src/syncbox/api.py` — the whole file, once (the REST/SSE contract you wire).

Do **not** re-read the kit afterwards; grep the specific section when a detail is missing.
Open the mockup **only per-screen, at the moment you build that screen**, and only the relevant
block (grep for the screen's labels) — never re-read the whole 2 780-line file. Never read
`docs/_research/04*`, `10*`, `14*` (deprecated download research), `docs/SPEC-01-syncbox.md`
(constants annex, only if §5 is not precise enough), or anything outside this working tree.

## Clean-room (strict)

The old implementation does not exist here, deliberately. Never read the `master` branch, any
other branch, git history of other branches, or any older application on this machine — the
current working tree of `build/clean-room-kit` is the only authority, **including for any
subagent**. Missing information → ask (`AskUserQuestion`), never guess, never go digging.

## Legal constraints (invariant, verbatim)

- Spotify playlist sync is read-only and uses authorized OAuth scopes.
- Missing tracks are handled only through legal purchase links and manual relink to local
  files the user already lawfully owns.
- Do not implement, prototype, or test any feature that downloads, extracts, bypasses
  protections, or retrieves full-track media from streaming services.
- Do not collect provider credentials for music download features.
- Any download / ARL / Deezer / SoundCloud control in the mockup is DEPRECATED and must not be
  built (SPEC-DESIGN §10/§11, SPEC-UNIFIED §6.5). Purchase links first, manual relink second,
  zero download job. The complete do-not-build control list is M4-PLAN §6.

## Execution rules

1. Follow the plan's increments **in order**; each increment ends green (`vitest run` +
   `cargo check`; pytest too whenever the sidecar was touched). No watch modes.
2. Owner arbitrations in M4-PLAN §0/§2/§3 are **settled** — do not re-open them. Any **new**
   structural decision the kit does not settle → stop and `AskUserQuestion`, ponytail
   recommendation first.
3. Ponytail at every brick; deliberate simplifications carry their `ponytail:` marker.
4. No dependency beyond M4-PLAN §3 without asking.
5. Non-trivial logic ships with its smallest failing-if-broken check (M4-PLAN §5 lists the
   expected tests per increment).
6. Faithful reporting: a failing test, a spec that does not hold against the real API, a guard
   that makes a flow heavy → say it and surface it, never mask it.
7. Windows code paths are out of scope (pre-M5); keep the OS seams visible.

## Done means

- Increments M4.1–M4.13 delivered; UI conforms to SPEC-DESIGN (6 destinations + real router +
  deep links + persistence, components §6, tokens §7, safety-guard surfaces §8, contractual
  states wired to the real REST/SSE, **10-step** onboarding, en/fr i18n with key parity).
- Shell supervisor passes the retargeted POC harnesses (tree-kill, port freed, single-instance,
  shutdown handshake). G1–G5 pytest-covered; full pytest suite green.
- Zero deprecated control built (M4-PLAN §6). Zero cleartext secret. One cache layer, one SSE
  stream, one health selector.
- Close protocol M4-PLAN §7 executed: three-lens review (sequential, high effort) → fix pass →
  **one closing commit**.

## Interaction

Livrable d'abord, explication courte ensuite. Langue d'échange : **français**.
