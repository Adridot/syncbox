## Why

Switching screens via the sidebar briefly freezes the whole app, and scrolling the Library becomes sluggish and buggy as the library grows (target: 2 000–10 000 tracks). Three compounding causes live in the UI shell: (1) the global `<keep-alive>` in `App.vue` keeps every visited screen mounted forever, so the DOM and memory footprint only ever grows; (2) `LibraryScreen` (and `EventsScreen`) render every track as a full DOM row with no virtualization — ~12 nodes per track, so 5 000 tracks ≈ 60 000 live nodes; (3) every keep-alive re-entry refetches all sources × all tracks and compares the entire payload with `JSON.stringify` (`sameData` in `lib/refresh.ts`), stalling the main thread proportionally to library size.

## What Changes

- Replace the unbounded whole-payload refresh cycle: keep the "instant last state on return, silent refresh" behavior (owner 16/07) but make the re-entry check cheap — no full-library `JSON.stringify` round-trip on the main thread.
- Virtualize the large track tables (Library review table, Events tracklist): only rows near the viewport exist in the DOM; scroll stays smooth at 10 000 tracks.
- Bound the memory held by inactive screens: the global `<keep-alive>` no longer retains every screen's full DOM indefinitely (bounded via `max`/include-list, or heavy screens release their big lists on deactivation while keeping scroll/selection state).
- Preserve existing UX contracts: skeleton on first load only, no full-screen flash on silent refresh, selection survives a refresh, "reopening shows the last state instantly".

## Capabilities

### New Capabilities

- `ui-performance`: Responsiveness contract for navigation and large lists — screen switches complete without a perceptible freeze, large tables render via virtualization, silent refreshes never stall the main thread proportionally to library size, and inactive screens' memory footprint is bounded.

### Modified Capabilities

<!-- none: openspec/specs/ has no populated capability covering navigation or list rendering today -->

## Impact

- `ui/src/App.vue` — keep-alive strategy.
- `ui/src/lib/refresh.ts` — `sameData` / `useRefreshOnReturn` replaced or reworked (used by every screen).
- `ui/src/screens/LibraryScreen.vue`, `ui/src/screens/EventsScreen.vue` — virtualized track tables.
- Possibly `ui/src/api/client.ts` / sidecar endpoints if a cheap change-detection signal (etag/updated_at/count) is added; no schema migration expected.
- No routing, backend job, or Rekordbox-side changes.
