# Syncbox — M4 Plan (Tauri v2 shell + Vue 3 UI)

> **Purpose.** Distilled map and build sequence for milestone M4, produced from a full kit
> inventory (specs read in full; `api.py`/`server.py`, mockup, POC shell, and repo state
> surveyed on 2026-07-03). This plan is a **map, not an authority**: on any conflict,
> [SPEC-UNIFIED.md](SPEC-UNIFIED.md) wins, then [SPEC-DESIGN.md](SPEC-DESIGN.md) + mockup
> (behavior/hierarchy only). The plan only fixes the *sequence* and the *owner arbitrations*
> recorded below.
>
> **Legal scope** (invariant): no download/acquisition feature of any kind. Missing tracks =
> purchase links + manual relink only. See SPEC-UNIFIED §6.5 and §8 (do-not-build list) below.

---

## 0. Owner arbitrations (2026-07-03)

| Topic | Decision |
|---|---|
| Onboarding step count | **10 steps** (bi-phase 4+6). SPEC-UNIFIED §11.4 is authoritative; the "11 étapes" wording in SPEC-DESIGN §2 and PROMPT-03 predates the download-step removal. Do not propagate "11". |
| Sidecar API gaps G1–G5 (§2) | **Fix in M4** — dedicated sidecar increment (M4.2), each addition pytest-covered. |
| UI stack | **"Batteries standard"**: Vite + Vue 3 + TypeScript + vue-router + **Pinia** + **vue-i18n** (+ Vitest/@vue/test-utils, @fontsource Geist). |
| Clean-room | Never read the `master` branch or any older implementation. Only the current working tree of `build/clean-room-kit` is authoritative — including for subagents. |

---

## 1. Facts from the kit inventory

### 1.1 Repo state

- **No frontend exists.** Repo root: `docs/ poc/ sidecar/ syncbox-ui-ux-design/`. `.gitignore`
  already reserves the M4 layout: **`ui/`** (Vue app) and **`shell/src-tauri/`** (Tauri shell)
  at repo root — use it.
- **No sidecar entrypoint.** The app is only ever assembled in tests. A launcher must compose:
  `platform_os.app_db_path()` → `appdb.open_app_db()` → `api.Deps(conn, bus, spotify_auth,
  log_path)` → `api.build_app(deps)` → `await server.serve(app)`. `server.py` hardcodes
  `127.0.0.1:8765` (port deliberately non-rotatable: OAuth redirect_uri is fixed); uvicorn runs
  in the main asyncio loop, 1 worker, graceful shutdown 3 s.
- **CORS is already amended** (§6.3): `tauri://localhost` + `http://tauri.localhost` +
  loopback-http regex (covers the Vite dev server). No sidecar change needed for origins.
- Tests: 372 pytest tests green (`cd sidecar && .venv/bin/python -m pytest`). **Zero JS test
  infra** — M4 creates it. Toolchain present: rustc/cargo 1.96.1, node 24, pnpm.
- Secrets: Spotify tokens in the sqlcipher-encrypted store (unsigned-build path). Nothing for
  the UI to manage beyond `/api/spotify/authorize` + `/callback`.
- Packaging (PyInstaller, signing) is **M5**. In dev, the shell spawns
  `sidecar/.venv/bin/python -m syncbox`.

### 1.2 Shell POC (poc/02 + poc/04) — what carries over

- Known-good: Tauri **2.11.5** Cargo.lock (compiles on this machine), `tauri.conf.json` shape,
  plugins single-instance + shell in the dependency set.
- **The committed `main.rs` is the POC #4 stub** (spawns nothing, self-exits after 90 s). The
  supervisor must be **rebuilt** from the proven recipe in `poc/02-lifecycle-treekill/VERDICT.md`:
  1. Register **single-instance first**; second launch self-exits; callback never re-spawns.
  2. Spawn the sidecar in its **own process group** via `std::process::Command` +
     `process_group(0)` — *not* plugin-shell's `sidecar()` (no process-group control).
     `killpg` is only safe when `pgid == pid`; group isolation at spawn is load-bearing.
  3. Shutdown handshake (§6.6): `POST /shutdown` → bounded wait → SIGTERM to group → SIGKILL
     to group. macOS caveat: `killpg` from the GUI shell can return EPERM → direct-pid fallback.
  4. Crash vs intent: **AtomicBool intent flag set before killing**, never exit codes.
  5. Supervisor loop (deliberately skipped by the POC): consume child output, bounded restart
     N=3 backoff 1/2/4 s, then emit **`backend-down`** event to the UI; manual "Relancer"
     command after exhaustion.
- POC #4 (GO): EventSource works incrementally in WKWebView under Tauri v2; webview origin is
  exactly `tauri://localhost`; mid-stream sidecar death yields a prompt EventSource `error`.
- Regression harnesses to retarget at the production shell/sidecar: `driver_lifecycle.py`,
  `test_single_instance.py` (path constants + log markers only).
- Windows half (taskkill /T, `http://tauri.localhost`, mutex single-instance) is **deferred to
  pre-M5** — keep the OS seams obvious, do not implement Windows code paths in M4.

### 1.3 Sidecar API — wiring rules the UI must obey

Route map (detail lives in `sidecar/src/syncbox/api.py` — read it once, it is the contract):

```
Transport   GET /health · GET /events (SSE) · POST /shutdown · GET /callback
Spotify     GET /api/spotify/authorize
Sources     GET|POST /api/sources · POST /api/sources/sync · PATCH|DELETE /api/sources/{id}
            POST /api/sources/{id}/sync · GET /api/sources/{id}/tracks · POST /api/sources/{id}/apply
Library     POST /api/library/tracks/tags · POST /api/library/tracks/{id}/rematch|ignore|restore
Events      GET|POST /api/events · GET|PATCH /api/events/{id}
            POST /api/events/{id}/tracks|match|claim|apply|reapply|delete
Missing     GET /api/missing/{scope} · POST /api/missing/collection/{content_id}/relink
            POST /api/missing/{scope}/{row_id}/status|restore
Duplicates  POST /api/duplicates/scan|resolve|dismiss
Untagged    GET /api/untagged · GET|POST /api/untagged/patterns · DELETE /api/untagged/patterns/{id}
            POST /api/untagged/delete
SmartFixes  POST /api/smartfixes/dry-run|execute
Settings    GET|PUT /api/settings          Readouts  GET /api/readouts
Doctor      GET /api/doctor/backups · POST /api/doctor/backups/{name}/restore
            POST /api/doctor/retention · GET /api/doctor/logs
```

Cross-cutting contract (source: full `api.py`/`server.py` read):

- **Error envelope**: `{error: <stable code>, message, ...extras}`. Codes: `mutation_blocked`
  (**423**, + `message_key`), `stale_snapshot` (**409**, + `action:'rerun_dry_run'`, guarantee:
  nothing written, no backup), `conflict` (409), `consent_required` (**428**, `consent:'anlz'` or
  `'permanent_delete'` + `path` + `message_key`), `spotify_not_connected` (409),
  `spotify_api_error` (502, + Spotify `status_code`; 404 = private playlist, actionable),
  `not_found` (404), `invalid_request` (400). **423 is not part of the 409 family** — own
  message, never leaks PID/path.
- **Consent is per-call, never remembered**: 428 → show the consent modal → re-call with the
  consent flag. `duplicates/resolve` is re-entrant (retry skips committed DB work). Smart Fixes
  protected opt-in ids must be sent on **both** dry-run and execute.
- **Fingerprints** (`duplicates/scan`, `smartfixes/dry-run`) are echoed back **verbatim**
  (JSON arrays) to `resolve`/`execute`; 409 `stale_snapshot` → re-run the preview.
- **Event delete defaults to `dry_run:true`** — an empty body is a preview; the destructive
  call sends `{dry_run:false}` explicitly. Confirmation text is built from the dry-run payload
  (B10: text == executed payload).
- **SSE**: one canonical stream `/events`. Events: `job.progress` `{job, kind, done, total,
  pct}` (real work units, F16) and `job.done` `{job, kind, ...summary}`. **No `job.error`
  event, no replay after reconnect** → SSE is progress *decoration*; the HTTP response (or a
  re-fetch) is the authority. Correlate by `kind` (one job of a kind at a time). Ignore
  comment ping lines (15 s keepalive).
- **One app-wide lock**: every `/api` call serializes (long scans block all other API calls;
  `/health` + `/events` stay responsive). UI must disable/queue mutating CTAs while a job runs,
  never fire parallel requests.
- **Settings gate**: most endpoints 400 until `rekordbox_db_path` + `storage_root` are set —
  gate features on `GET /api/settings`. Updates apply on next request (no restart); blank
  `spotify_client_id` **preserves** the stored value.
- **OAuth flow**: `GET /api/spotify/authorize` → open URL in the **system browser** → browser
  hits `/callback` (plain HTML page). No status endpoint existed → G1 below.
- Booleans arrive as SQLite ints (0/1); `tags` are JSON arrays; exact paths only (trailing
  slash 307-redirects); the only allowed request header is `content-type`.
- `quality_verdict` exists **only** on duplicate-group members (computed on demand);
  `/api/readouts` counts absent verdicts as `ok` (§11.3 — never a binary red counter).
- Purchase links appear only for `missing`/`purchase_link_unavailable`; open in the system
  browser; the sidecar never contacts stores.

### 1.4 Mockup deltas already settled by the specs

- **Onboarding = 10 steps** (§11.4): mockup step 4 "Module" is removed; mockup step 9
  "Acquisition" becomes **Missing tracks** (purchase + relink content). Rail phases:
  Configuration (4) / Prise en main (6).
- **Settings folders**: the API exposes **2 editable paths** (`rekordbox_db_path`,
  `storage_root`); the "4 dossiers" rows render the derived `_rekordbox_sync` subdirs
  (inbox/backups) as **read-only validated rows** (SPEC-UNIFIED §4 layout wins over labels).
- **Smart Fixes catalog is fixed server-side** (§5.11) — the mockup's 4 per-family checkboxes
  are not selectable options; render the families as descriptive text + one dry-run CTA.
- **No toast system** — feedback via inline banners, badges, disabled-state labels, previews.
- Library/Events per-row "Acheter/Racheter → Acquisition" is deprecated; those rows **link to
  the Missing tracks center with the scope pre-filtered** (SPEC-DESIGN §2).
- "Démo états" simulator panel and theme knobs (accent/typeface/radius) are mockup artifacts —
  never built.
- Untagged junk-pattern editor: API exists (D7) but the design shows none → build the minimal
  in-tab editor (list / add / delete a regex pattern). `ponytail:` smallest surface satisfying D7.

---

## 2. Sidecar surface completion — G1–G5 (owner-approved)

The only sidecar work in M4 besides the composition root. Each addition is small, follows the
existing `api.py` idioms (envelope, lock, i18n message keys), and lands with pytest coverage.

| # | Addition | Contract sketch |
|---|---|---|
| **G1** | `GET /api/status` | `{rb_open: bool, spotify_connected: bool}` — read-only psutil check + token presence. Feeds the RB banner/hero/HealthPill *proactively* (today unknowable without a failing mutation). UI polls (interval + window focus + after any 423). |
| **G2** | `GET /api/library/tracks/{id}/candidates` + `POST /api/library/tracks/{id}/match` | Candidates = matcher's scored top-N from the snapshot `{content_id, title, artist, duration_ms, bitrate, confidence}`; manual confirm sets `content_id` + `status='matched'` (`match_method='manual'`). Powers ReMatchModal (SPEC-DESIGN §6: candidate list, not blind re-run). |
| **G3** | `POST /api/missing/collection/{content_id}/remove` | §5.8 "remove" = **soft-delete via `_mutate`** (423-guarded, backup, reversible). No audio file deletion. |
| **G4** | Matching thresholds in settings | Keys: `match_confidence_threshold` (82), `match_ambiguity_margin` (6), `match_weights` title/artist/duration (0.52/0.36/0.12, **sum==1.00 validated**), `isrc_collision_policy`. Consumed by `matching.py`; exposed via GET/PUT `/api/settings`; reset = PUT defaults. Locked invariants (ISRC-first, single normalization D19, duration buckets) are **not** configurable. |
| **G5** | `GET /api/spotify/playlists/{playlist_id}/preview` | Read-only `{name, owner, tracks_total, image_url\|null}` for AddSourceModal's resolved preview before following. 409 `spotify_not_connected` / 502 pass-through. |

---

## 3. Stack & layout (arbitrated)

```
ui/                     Vite + Vue 3 + TypeScript (strict) + vue-router (hash history)
                        Pinia (stores) · vue-i18n (en.ts/fr.ts) · @fontsource geist-sans+geist-mono
                        Vitest + @vue/test-utils (jsdom)
shell/src-tauri/        Tauri 2 (start from poc/02 skeleton: Cargo.toml/lock, conf shape)
                        plugins: single-instance (registered first) + opener (external URLs)
                        sidecar spawn: std::process::Command + process_group(0)
                        capabilities/: core defaults + opener + the shell's restart command
sidecar/src/syncbox/    __main__.py composition root (M4.1) + G1–G5 (M4.2). Nothing else.
```

- Dev loop: `pnpm tauri dev` — `devUrl http://localhost:5173`, `beforeDevCommand pnpm dev`;
  release: `frontendDist ../ui/dist`, `beforeBuildCommand pnpm build`. Loopback origin is
  already CORS-allowed, so plain browser dev (`pnpm dev` alone) also works for UI-only work.
- Tokens §7 as CSS custom properties in one `tokens.css`; no CSS framework. Geist self-hosted
  (no CDN — the packaged app must work offline; strict CSP).
- External links (purchase, authorize URL, "open logs folder") go through the **opener
  plugin** — `target=_blank` is not a system browser in a webview.
- CSP: replace the POC's `null` with a real policy per §6.3 (self + `http://127.0.0.1:8765`
  connect-src for REST/SSE).
- Production window config + identifier (`dev.syncbox.app` style), unsigned build (Phase 0).

## 4. UI architecture rules (corrects T4/T5/F16 by construction)

- **One API client** module typing the error envelope as a discriminated union; interceptors:
  423 → set `rbOpen` in the status store; 409 `stale_snapshot` → invalidate the preview that
  sent it; 428 → open the matching consent modal and re-call on consent.
- **One SSE client**: single `EventSource`, auto-reconnect, comment-tolerant; publishes into a
  jobs store; **JobRow progress only ever reads SSE `pct`** (never tone/status).
- **One `health` selector** (Pinia getter): sidebar badges, dashboard tiles, health-hub tab
  badges, HealthPill — all derive from it. There is exactly one definition of "connected",
  "ready", "active". Duplicates count = **last scan result** held in the store; the spectral
  scan is never auto-run on mount (it locks the whole API) — tiles show "—" + a scan affordance
  until a scan has run.
- **Job serialization**: a `jobRunning` flag disables mutating CTAs app-wide while any job runs.
- **Status store**: `/api/status` polled (interval + window focus + after any 423); RB banner,
  dashboard hero, and CTA "Rekordbox ouvert — bloqué" variants derive from the store only.
- **Router**: 6 destinations + `#health/<tab>` + missing-center scope param; current route
  persisted (localStorage); unknown route → Dashboard (never Settings). Back/forward native.
- **i18n**: every mockup FR string becomes a key; `en.ts`/`fr.ts` parallel; **a unit test
  asserts key-set parity**; locale bound to `settings.language` (single source of truth —
  localStorage only caches the last known value for pre-settings boot).
- **Onboarding** done-flag in localStorage (not a sidecar setting); "Revoir l'onboarding"
  relaunches at step 1.
- Activity feed (dashboard) is **UI-local**: derived from `job.done` events + the session's own
  actions. `ponytail:` no history endpoint/persistence — add only if the owner asks for
  cross-session history.

## 5. Increments (each ends green: vitest + cargo check, pytest when sidecar touched)

**M4.1 — Scaffold & dev loop.** `ui/` (Vite+Vue+TS+router+Pinia+vue-i18n+Vitest),
`shell/src-tauri/` from POC skeleton (renamed identifiers, real window config, CSP),
`syncbox/__main__.py` composition root (wires app db, secrets/SpotifyAuth, log_path — makes
`GET /api/doctor/logs` configured). Placeholder route renders `/health` result.
*Done when*: `pnpm tauri dev` opens a window that shows the sidecar is alive; vitest smoke
passes; 372+ pytest still green.

**M4.2 — Sidecar surface completion.** G1–G5 per §2, with pytest for each (status truthiness,
candidates shape + manual match transition, remove soft-delete via `_mutate` + 423, weights
sum validation + matcher consumption, preview happy/409/502).

**M4.3 — Shell supervisor.** Rebuild `main.rs` per §1.2 recipe (single-instance first,
own-group spawn, output consumption, intent flag, shutdown handshake wired to window-close,
bounded restart 3× backoff 1/2/4 s, `backend-down` event, `restart_sidecar` command).
Retarget `driver_lifecycle.py` + `test_single_instance.py` as the regression harness.
*Done when*: harness passes against the production shell+sidecar (tree-kill, port freed,
single-instance, handshake with open SQLCipher connection).

**M4.4 — UI foundation.** `tokens.css` (§7), fonts, i18n plumbing + parity test, typed API
client + interceptors, SSE client, status/jobs/health stores + canonical selector, router
(deep-links, persistence, unknown→Dashboard). *Tests*: router behaviors, selector derivations,
envelope mapping (423/409/428), SSE decode + reconnect, i18n parity.

**M4.5 — App chrome.** Sidebar + nav badges, HealthPill, RB-guard banner ("J'ai fermé
Rekordbox" → immediate re-poll), backend-down overlay + "Relancer" (invokes shell command),
Modal shell (backdrop, slide-up, esc/click-outside), StatusBadge/QualityBadge/ScopeBadge,
Empty/Loading(shimmer)/Error primitives, JobRow(SSE).

**M4.6 — Dashboard.** Hero variants (closed/open, "Dernier backup" from doctor/backups),
4 tiles → deep-links, collection snapshot card + readouts (§11.3 vocabulary — `QualityBadge`
wording, never a red binary counter), activity feed (UI-local), connections panel (Spotify
states + reconnect action).

**M4.7 — Bibliothèque.** Master list (search, "Toutes les sources" aggregate row, review-count
badges, add via AddSourceModal with G5 preview + default MyTags), TrackReviewTable (status
filter chips — "Tous" hides `ignored`/`removed_from_source`; select-all over **filtered** rows;
confidence/bitrate chips; 2-line titles when narrow; match method hidden), BulkTagBar +
TagPicker (delta add/remove, searchable, per-row +/− toggles, delta summary), ReMatchModal (G2
candidates, "Marquer comme manquant" escape), ignore/restore (D22 inline feedback), missing
rows link to Missing center (scope=library). 404 error state with "Réessayer" / "Connecter mon
compte Spotify".

**M4.8 — Events.** Cards (lifecycle badges, `pending_delta` "+N en attente", ready/missing
counters), workspace (segmented progress bar from real counts, filters with counts),
AddTrackByLink (paste Spotify link → extract id client-side → resolving state; manual
title/artist entry; **Spotify-only placeholder**), match/claim actions, ApplyEventModal &
DeleteEventModal (previews built from the API's dry-run payload; **both CTAs carry the RB
guard**), ReapplyEventModal (§11.2 delta preview, CTA "Ré-appliquer · N changement(s)"),
"Modifié" banner, rename (pending only).

**M4.9 — Santé hub.** Tab bar (deep-linkable, badges from the selector).
*Doublons*: explicit scan CTA with SSE progress, DuplicateGroupCard (side-by-side comparison,
re-selectable keeper radio, explicit reason, warning groups excluded from bulk, per-group
confirm), resolve flow with 428 permanent-delete consent loop (re-entrant retry), dismiss.
*Fichiers manquants*: purchase/relink/remove rows (G3), relink via ManualRelinkModal +
AnlzReplaceModal on 428. *Untagged*: 4 sorted categories, selection-on-filtered, D15 delete
with real skip report, minimal junk-pattern editor. *Smart Fixes*: fixed catalog description +
dry-run → DryRunModal (before→after rows, protected opt-in named non-remembered, stale banner →
"Relancer l'aperçu", CTA = exact payload count, RB-guarded) → execute. *Backups & logs*: list,
restore (423-guarded, "restore snapshots first" note), retention control, log tail + "Ouvrir
le dossier de logs" (opener).

**M4.10 — Missing tracks center.** Scope tabs/filter (library/event/collection + deep-link
scope param), entries with PurchaseLinks (opener; absent for `removed_from_source` — server
filters, UI must not re-add), ManualRelinkModal (candidates + scores + "aucun de ces
candidats"), ANLZ consent flow (428), status transitions (§5.5) + restore (D22), collection
remove (G3) behind IrreversibleDeleteModal-style confirm only when the API demands consent.

**M4.11 — Réglages.** Spotify card (connect/reconnect/failed states via G1 + authorize flow
through opener; poll for completion), paths (2 editable PathFields with server validation
errors mapped inline + derived read-only rows), retention, langue (drives vue-i18n locale via
PUT settings), Avancé collapsed panel (G4: sliders/weights with sum==1.00 client+server
validation, ISRC collision policy select, locked-invariants box, reset), "Revoir l'onboarding",
version footer.

**M4.12 — Onboarding.** Overlay, clickable rail, 2 phases / **10 steps** (§11.4 list), skip,
per-step CTAs wiring real actions where cheap (Spotify connect, paths validation, first sync),
FR/EN toggle, replay from Settings, done-flag localStorage.

**M4.13 — Hardening & close.** Contractual-states sweep (empty/loading/error/RB-open/
backend-down/stale-dry-run on every screen), i18n parity + untranslated-string hunt, modal
a11y basics (focus trap, esc, labels), dead-code pass, then the **close protocol** (§7).

## 6. Do-not-build appendix (deprecated mockup controls — legal scope)

Never implement: the sidebar "Acquisition" nav item and its badge; the "Téléchargements" row in
the sidebar health pill; the entire Acquisition screen (missing list with "↓ Deezer" buttons,
"Tout ouvrir sur Beatport" bulk, module on/off banners, download "Jobs en cours" panel, ambiguous
job arbitration); the arbitrate-Deezer-candidates modal; Settings "Module de téléchargement"
card, ARL field/sub-section, SoundCloud sub-note; onboarding steps "Module" and the
acquisition-tour step; Deezer/SoundCloud halves of link-input placeholders and provider badge
parsing in the Nouvel event / Ajouter une source modals; ANLZ modal "racheter le fichier"
re-download framing (v1 framing = relink to an owned local file); `acquisition_failed` /
`acquisition_ambiguous` status vocabulary; dashboard "Module téléchargement" connections row and
"Tout voir →" wired to Acquisition; library/events row actions navigating to Acquisition
(→ Missing center links instead); the "Démo états" simulator and theme knobs (mockup artifacts).

## 7. Milestone close protocol

1. **Three-lens adversarial review** (sequential passes, high effort, single agent):
   *spec-compliance* (SPEC-DESIGN §2–§8 + §11 vs built UI; §1.4/§2 of this plan), *failure
   modes* (SSE loss, backend-down mid-job, 423/409/428 paths, stale fingerprints, race on
   navigate-away), *test adequacy* (every §4 rule and §5 increment has its failing-if-broken
   check).
2. Fix pass for every confirmed finding.
3. **One closing commit** for the milestone (convention: one commit per milestone on
   `build/clean-room-kit`).
