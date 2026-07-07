# PROMPT — Refaire le front (écrans M4.7 → M4.13), Fable seul, clean-room

> **How to use.** Paste into a **fresh** Claude Code (Fable) session at the repo root, on branch
> `build/front-fable`. **Single-agent session by design**: this prompt deliberately omits the
> multi-agent keyword; do not launch workflows or agent fan-outs. `/ponytail full` stays active.
> Interaction in **French**; all repository content in **English**.

## Clean-room — HARD, non-negotiable

A previous model already built these exact screens on another branch. **That implementation is
deliberately hidden from you and you must never look at it.**

- **Forbidden**, no exception, not even "just to compare": the branch `opus-m4`, the branch
  `build/clean-room-kit`, the commits `1eaac50` / `410de86`, their files, their diffs, their git
  history — and any older Syncbox UI anywhere on this machine. Do **not** `git checkout`,
  `git show`, `git diff`, `git log -p`, or read a single file from them.
- The **only** authority is the working tree of `build/front-fable` + the specs + `docs/REMARKS.md`.
  You build every screen **from the spec**, in your own design, not from anyone's prior code.
  This rule binds any subagent you might spawn.
- Missing information → `AskUserQuestion`, never guess, never go digging on another branch.

Why: the point of this redo is a clean, correct implementation that does not inherit the prior
build's defects. Copying it would defeat the exercise. The defects worth knowing are already
distilled for you in `docs/REMARKS.md` (below) — that is all you get from the prior attempt.

## Mission

Build the frontend **screens** of milestone M4 — increments **M4.7 → M4.13** of
[M4-PLAN.md](M4-PLAN.md) — on top of the foundation already present in this working tree
(M4.1–M4.6: backend, shell, UI foundation, chrome, Dashboard). You are creating, from the design
spec: **Bibliothèque, Events, Santé de collection (hub), Missing tracks (centre), Réglages
(réel), Onboarding (10 étapes)**, and every modal they need. Wire them to the real sidecar
REST/SSE on `127.0.0.1:8765`.

## What already exists — build on it, do NOT rebuild it

The backend, the shell and the UI foundation are done, reviewed and green. Do not touch them
except to add screen i18n keys and (only if an owner-approved gap requires it) a small sidecar
route.

- **Backend** (`sidecar/`): composition root + full REST/SSE + owner-approved gaps G1–G5
  (`GET /api/status`, library-track candidates + manual match, missing-collection remove,
  matching thresholds/weights/isrc-policy in settings, spotify playlist preview). Stored paths
  expand `~` already. **Read `sidecar/src/syncbox/api.py` once — it is the REST/SSE contract you
  wire.** Do not re-read it after.
- **Shell** (`shell/`): Tauri supervisor + regression harnesses. Untouched by front work.
- **UI foundation (yours from M4.4–M4.6 — keep it):**
  - `ui/src/styles/tokens.css` + `base.css` (SPEC-DESIGN §7 tokens).
  - `ui/src/i18n/{index,en,fr}.ts` — keys exist through the `dashboard`/`activity` sections;
    **add each screen's keys as you build it, keep en/fr in parity** (a parity test is in place).
  - `ui/src/api/client.ts` — one typed client: error envelope as a discriminated union,
    interceptors for 423 (sets `rbOpen`), 409 `stale_snapshot`, 428 consent, an in-flight
    mutation counter, and a **consent-broker hook** you wire your consent modal into.
    `ui/src/api/sse.ts` — one SSE client.
  - `ui/src/stores/{status,jobs,health,settings}.ts` — `health` is the **single canonical
    selector** every badge/pill/tile reads; `jobs` holds SSE progress (`pct` only, F16);
    `status` polls `/api/status`; `settings` gates features on the two configured paths.
  - `ui/src/router/index.ts` — 6 routes, deep-linkable `#/health/<tab>` and `#/missing/<scope>`,
    route persistence, unknown → Dashboard. **The 5 task screens are placeholders you replace.**
  - `ui/src/components/` chrome primitives: `AppSidebar`, `HealthPill`, `RbGuardBanner`,
    `BackendDownOverlay`, `ModalShell`, `StatusBadge`, `QualityBadge`, `ScopeBadge`,
    `EmptyState`, `LoadingState`, `ErrorState`, `JobRow`. `ui/src/screens/DashboardScreen.vue`
    is done. `ui/src/shell.ts` = the opener wrapper for external URLs.
- **Green baseline right now**: `cd sidecar && .venv/bin/python -m pytest -q` = **388**;
  `cd ui && pnpm typecheck` clean; `cd ui && pnpm test` = **27**. Run all three before you start;
  keep them green at every increment (no watch modes).

## Authority hierarchy

1. [SPEC-UNIFIED.md](SPEC-UNIFIED.md) — product/architecture QUOI, §5 invariants, §11 amendments.
2. [SPEC-DESIGN.md](SPEC-DESIGN.md) + mockup `syncbox-ui-ux-design/project/Syncbox.dc.html` — the
   UI contract. **Behaviour and hierarchy only, never the literal CSS. Spec beats mockup.** Open
   the mockup **per-screen**, grepping the relevant block only — never read the whole file.
3. [M4-PLAN.md](M4-PLAN.md) — the increment map: **§5 increments M4.7–M4.13** (what each screen
   contains + expected tests), **§4** architecture rules (one client / one SSE / one health
   selector / job serialization / consent loop), **§6** do-not-build list. A map, not an
   authority: if it seems to contradict a spec, the spec wins and you say so.
4. [docs/REMARKS.md](REMARKS.md) — **mandatory, read it fully.** See next section.

## docs/REMARKS.md — read it in full; it is the reason for this redo

The prior build of these screens shipped defects the owner caught in testing. `REMARKS.md`
records them as **B1–B4** (bugs — mistakes to NOT repeat) and **R1–R5** (owner-requested
enhancements). Honour them:

**B1–B4 — hard constraints, get them right by construction:**

- **B1 — never swallow a backend error on a user-triggered action.** The prior Duplicates scan
  did nothing on click when the sidecar returned 423 (RB open) / 400 (paths not configured) /
  500 — the handler had no `try/catch` and no error surface, so the click was a silent no-op.
  Every action that can 4xx/5xx surfaces the message **actionably** (RB-open banner already
  exists for 423; still show why a click failed for 400/409/network). Silent `.catch(() => {})`
  is allowed **only** for a truly-optional background refresh, never for something the user
  clicked.
- **B3 — a validity tick (✓/✕) must reflect a REAL server check, re-run on load.** The prior
  Settings showed ✓ for any non-empty path, even one that did not exist. A pre-filled default
  path must be validated (server `validate_directory` / not-found) **before** it earns a ✓; on
  mount, re-validate stored paths so the tick is never optimistic.
- **B4 — a preview must make invisible changes visible.** Smart Fixes showed rows like
  `Carole Fredericks → Carole Fredericks` (identical to the eye) when the only change was a
  trailing / doubled / non-breaking space. Highlight suspect whitespace git-diff style (mark
  leading/trailing, doubled, and non-ASCII spaces) so the "aperçu exact" (§5.11 / B10) is
  genuinely exact. The backend never emits a no-op, so an identical-looking row is always a
  real, invisible change — surface it.
- **B2** was a backend `~`-expansion bug, **already fixed** in `api.py` (`_expanduser` on
  `db_path`/`storage_root`, regression test `test_db_path_expands_tilde`). Nothing to redo.
- Two findings the prior build's own review caught — do not reproduce them:
  - the **428 consent broker must QUEUE concurrent consents (FIFO)**, never a single overwritten
    slot (which stranded a promise and left `jobRunning` stuck true);
  - **bounded poll loops** (the Spotify-OAuth-completion poll) must **auto-cancel on unmount**
    (register the cancel in `setup`, not inside the async handler).

**R1–R5 — owner-requested enhancements.** Fold in the front-only, settled ones; **STOP and
`AskUserQuestion`** for any that need a backend route or a spec change:

- **R1** user-supplied **Spotify Client ID** field in Réglages (the settings key
  `spotify_client_id` already exists — front-only: a text field + inline help on where to get it;
  gate "Connect Spotify" while empty). Build it.
- **R2** the **sync icon** (`↻`) renders too thin vs the mockup — a CSS size/weight fix on
  `.btn-icon`, no glyph/asset swap. Build it.
- **R3** the **path fields** need explanations + help, and the owner wants `storage_root` split
  into **3 explicit folders** — this changes the settings schema, the backend validation, and
  the volume-relative rule (§3.2/§5.2). **Owner arbitration required** (REMARKS flags it): ask
  before building; until settled, keep the current 2-path model.
- **R4** **audio preview** per duplicate member — needs a sidecar audio-stream endpoint. Ask
  before building.
- **R5** pick a source **from the Spotify library** (playlist picker) — needs
  `GET /api/spotify/playlists`. Ask before building.

## Read first — token discipline

Read **once**, then build from memory + targeted lookups:

1. `docs/REMARKS.md` — fully.
2. `docs/M4-PLAN.md` — §1.4, §4, §5 (increments M4.7–M4.13), §6 (do-not-build list).
3. `docs/SPEC-DESIGN.md` — fully (the UI contract).
4. `docs/SPEC-UNIFIED.md` — **only** §5.5, §5.7, §5.8, §5.11, §5.12, §5.13, §11.
5. `sidecar/src/syncbox/api.py` — once (the REST/SSE contract).

Open the mockup **per-screen, grepping the screen's labels only**. Never read `docs/_research/04*`,
`10*`, `14*` (deprecated download research) or the `opus-m4` branch (forbidden, see clean-room).

## Legal constraints (invariant, verbatim)

- Missing tracks use **legal purchase links + manual relink only**. No download/acquisition
  control of any kind — no Deezer/SoundCloud download, no ARL field, no download toggle/queue/
  job, no acquisition screen. The complete do-not-build list is M4-PLAN §6.
- Event track additions use Spotify metadata links, manual entry, or lawful local relink only.
- Do not implement, prototype, or reword anything to reintroduce a download path. If a control in
  the mockup is download-shaped, it is deprecated — skip it.

## Execution rules

1. Follow M4-PLAN increments **M4.7 → M4.13 in order**; each ends green (`pnpm test` +
   `pnpm typecheck`; `pytest` too if you ever touch the sidecar for an owner-approved gap).
2. Ponytail at every brick; deliberate simplifications carry their `ponytail:` marker. No new
   dependency beyond M4-PLAN §3 without asking.
3. Non-trivial logic ships its smallest failing-if-broken check (M4-PLAN §5 lists the expected
   tests per increment). Keep en/fr parity (the parity test guards it).
4. Owner arbitrations you hit (R3/R4/R5, or anything the kit does not settle) → stop and
   `AskUserQuestion`, ponytail recommendation first. Do not re-open settled M4-PLAN arbitrations.
5. Faithful reporting: a failing test, a spec that does not hold against the real API, a guard
   that makes a flow heavy → say it, never mask it.

## Done means

- Screens M4.7–M4.13 delivered from the spec (6 destinations wired to the real REST/SSE, deep
  links, contractual states empty/loading/error/RB-open/backend-down/stale-dry-run, **10-step**
  onboarding, en/fr with key parity).
- **B1–B4 honoured by construction** (no silent error swallowing, ticks reflect real checks,
  previews surface invisible changes, FIFO consent queue, poll loops cancel on unmount); R1 + R2
  built; R3/R4/R5 arbitrated with the owner.
- Zero deprecated download control (M4-PLAN §6). One cache layer, one SSE stream, one health
  selector. `pnpm test` + `pnpm typecheck` green, `pytest` still 388.
- Close protocol: **three-lens adversarial review** (spec-compliance / failure-modes /
  test-adequacy, sequential, high effort, single agent) → fix pass → **one closing commit** on
  `build/front-fable`.

## Interaction

Livrable d'abord, explication courte ensuite. Langue d'échange : **français**.
