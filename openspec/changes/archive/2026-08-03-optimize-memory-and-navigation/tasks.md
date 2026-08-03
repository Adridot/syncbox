## 1. Virtualization groundwork

- [x] 1.1 Add `@tanstack/vue-virtual` to `ui/package.json` (pnpm)
- [x] 1.2 Create `ui/src/lib/virtualRows.ts`: thin wrapper around `useVirtualizer` shared by both tables — stable `track.id` keys, `measureElement` dynamic heights, small overscan, scroll-element resolution (own element, or nearest scrollable ancestor via `closest()` with a safe fallback for bare mounts in tests)

## 2. Library table (LibraryScreen.vue)

- [x] 2.1 Window `.table-body`: relative wrapper sized to `getTotalSize()`, rows absolutely positioned via `translateY`, existing row markup/classes untouched; `.table-empty` still renders when the filtered list is empty
- [x] 2.2 Pixel-parity pass against current design: row borders, hover-reveal actions, selected tint, 2-line clamped titles, restored-flash, floating SelectionBar with zero layout shift
- [x] 2.3 Delete `sameData` from `ui/src/lib/refresh.ts` and its guard in `load()`: silent refresh always swaps `sources`/`tracksBySource` (design Decision 2); update the keep-alive comment in `App.vue` if it references the compare

## 3. Events tracklist (EventsScreen.vue)

- [x] 3.1 Window the tracklist rows with the scroll element resolved to App's `.main` (nearest scrollable ancestor); page-level scrolling behavior unchanged
- [x] 3.2 Parity pass: added-after-apply chip, acquisition badge/phases, `.row-error` line growth re-measures the row correctly

## 4. Tests (vitest)

- [x] 4.1 Library: with a few thousand mocked tracks, the DOM contains only ~viewport rows (assert rendered row count ≪ dataset size)
- [x] 4.2 Select-all over a filtered, windowed table selects every filtered track including off-DOM rows; a bulk action (apply/tags payload) covers off-screen selected ids
- [x] 4.3 Silent refresh with identical data: no skeleton, selection and scroll intact, no visible table change; existing `refresh.spec.ts` still passes with `sameData` removed
- [x] 4.4 Events screen mounts and renders windowed rows outside the App shell (scroll-element fallback path)

## 5. Verification at scale

- [x] 5.1 Seed the Syncbox-dev sandbox (never the real db; check port 8765 owner first) to ~10 000 tracks; verify: no perceptible freeze switching screens, smooth Library/Events scrolling, memory stays flat when cycling all screens repeatedly
- [x] 5.2 `pnpm typecheck` + `pnpm test` green; quick visual pass of both screens against the current design
