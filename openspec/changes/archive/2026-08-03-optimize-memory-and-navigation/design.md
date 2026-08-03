## Context

See proposal.md — Why. Facts of the current code that shape the approach:

- `ui/src/App.vue` wraps the router view in a global, unbounded `<keep-alive>`; every visited screen stays mounted forever (deliberate: "reopening shows the last state instantly", owner 16/07).
- `LibraryScreen.vue` renders `visibleTracks` as full DOM rows inside `.table-body`, which is **already a dedicated scroll container** (`overflow-y: auto`).
- `EventsScreen.vue` renders the selected event's tracklist as rows directly in `.table`; the screen has **no internal scroll container** — the page scrolls in App's `.main` (`overflow-y: auto`).
- Row heights are **not fixed**: Library titles clamp at 2 lines, Events rows grow an extra `.row-error` line during acquisition.
- `lib/refresh.ts` exposes `sameData` (double `JSON.stringify` of the whole payload) used by `LibraryScreen.load()` only, to avoid re-rendering the big table on identical silent refreshes. `useRefreshOnReturn` (used by ~9 screens) is behavior we keep as-is.
- Selection (`selection: Set<number>`), select-all (`toggleAll`) and bulk actions already operate on the **filtered data arrays**, never on the DOM.
- Runtime is WKWebView (Tauri v2, macOS-only), Vue 3.5, Pinia. No virtualization library installed.

Constraints: existing UX contracts (skeleton on first load only, silent refresh with no flash, selection survives refresh, floating SelectionBar with zero layout shift, instant last state on return) are non-negotiable; row markup and CSS must stay visually identical.

## Goals / Non-Goals

**Goals:**

- Satisfy `specs/ui-performance/spec.md` with the smallest diff: virtualize the two big tables, delete the whole-payload compare, leave the keep-alive contract intact.
- Keep the existing row markup/classes byte-for-byte; virtualization only changes row *positioning*.
- UI-only change: no sidecar endpoint, no schema, no new Pinia store.

**Non-Goals:**

- Pagination or partial fetch (re-entry still refetches all sources; acceptable — the fetch is async and off the interaction path).
- Backend change-detection signal (etag/`updated_at`): named upgrade path if the ~O(library) JSON parse ever becomes noticeable; not needed to meet the spec.
- Virtualizing small lists (sources master list, Events card rail, History) — hundreds of rows max, not worth it.
- keep-alive eviction / screen-state externalization (see Decision 3).

## Decisions

### 1. Virtualize with `@tanstack/vue-virtual` (dynamic measurement) — new dependency

Both tables get a windowed body: a relative wrapper sized to `getTotalSize()`, rows absolutely positioned via `translateY`, keyed by `track.id`, `measureElement` for real row heights, small overscan (~10).

- **Library**: scroll element = the existing `.table-body` — no layout change.
- **Events**: scroll element = the nearest scrollable ancestor (App's `.main`), resolved at mount via `closest()`; the page keeps scrolling exactly as today.

Why this over the alternatives:

- *Hand-rolled fixed-height windowing*: rows are variable-height (2-line titles, error lines); doing dynamic measurement by hand is ~200 error-prone lines — past the point where avoiding a dependency is the lazy option.
- *`content-visibility: auto`* (native, one line of CSS): skips rendering but keeps all 10 000 vnodes + DOM nodes alive, so Vue still diffs the full list on every reactive change, and the spec explicitly requires only viewport rows in the DOM.
- *vue-virtual-scroller*: component-shaped (replaces our markup), Vue-3 support still beta.

TanStack Virtual is headless (zero styles — our row markup/CSS untouched), maintained, tree-shakes to a few KB.

### 2. Delete `sameData`; silent refresh always swaps the refs

`sameData` exists solely so an unchanged silent refresh doesn't re-render a huge table. With windowing, a swap re-patches only the ~viewport rows — keyed by stable ids, so identical data produces zero DOM mutation and no visible change. Deleting the guard removes the double-`JSON.stringify` main-thread stall (the actual re-entry freeze) with *negative* code cost.

Alternatives considered: per-source hashing, count+`updated_at` compare, backend etag — all add code (and possibly backend surface) to optimize a stall that no longer exists once the guard is gone.

### 3. `App.vue` keep-alive stays exactly as-is

After virtualization, an inactive cached screen retains ~viewport-sized DOM plus its data arrays — O(library size), a few MB at the 10 000-track target — and the screen set is finite (~7 routes). Inactive memory is therefore bounded with zero code.

`:max` eviction was rejected: eviction unmounts the component, destroying filters/selection/scroll and re-arming the first-load skeleton (`sources === null`), which violates the restore and skeleton contracts — unless every screen's state moves into stores, a large refactor whose payoff virtualization already delivered.

### 4. Selection and bulk actions: no design change, only proof

`toggleAll`, `selectedTracks`, apply and bulk-tag already iterate the filtered data arrays (`visibleTracks`), not rendered rows. Windowing cannot affect them. The spec scenarios (select-all over filtered rows, action on off-screen selection) are covered by tests rather than code changes.

## Risks / Trade-offs

- [Variable row heights make the scrollbar estimate drift] → `measureElement` corrects as rows render; stable `track.id` keys let the measurement cache survive silent refreshes; overscan absorbs the jitter.
- [Events virtualizer depends on a scroll element owned by App.vue] → resolved at mount via `closest()`; if the ancestor is not found (unit tests mounting the screen bare), fall back to window/document scrolling so tests and one-off mounts keep working.
- [Unchanged refresh now re-patches viewport rows instead of skipping entirely] → keyed patch of ≤ ~40 identical vnodes, no DOM writes; imperceptible against the removed O(library) stringify.
- [Absolute-positioned rows change border/hover interplay] → row markup and classes unchanged; verify pixel parity by eye against the current design (row borders, hover-reveal actions, selected tint, `.table-empty`).
- [New dependency] → headless and small; if TanStack ever rots, the windowing wrapper is one composable call to replace.

## Migration Plan

Pure front-end change shipped with the app bundle; no data migration, no config, rollback = revert the commit. Validate on the Syncbox-dev sandbox (never the real db) seeded to ~10 000 tracks: navigation freeze gone, smooth scroll, selection/filters intact.
