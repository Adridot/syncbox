## Why

On the Prestations (History) screen the two columns are visually and behaviorally dissociated: the left performance list has its own scrollbar capped at `70vh`, while the right tracklist stretches to its full content height and scrolls the whole page — so the left column scrolls away while browsing a tracklist, and the two columns never share a coherent frame. The Library screen already implements the correct pattern (screen pinned to the window height, each pane scrolling internally).

## What Changes

- Align the Prestations screen layout on the Library model: the screen occupies the window height, the performance list (left) and the tracklist workspace (right) each scroll independently inside a shared, stable frame.
- The workspace header (performance name, meta, export/hide actions) stays visible while the tracklist scrolls.
- The page-level scrollbar disappears on this screen; the `70vh` cap on the left list is removed.
- No behavior change: selection, live polling, rename, export, hide/unhide are untouched.

## Capabilities

### New Capabilities

- `history-split-layout`: Layout contract for the Prestations two-pane screen — window-height frame, independent internal scrolls, persistent workspace header, consistent with the Library master/detail pattern.

### Modified Capabilities

<!-- none: no existing spec in openspec/specs/ covers this screen's layout -->

## Impact

- `ui/src/screens/HistoryScreen.vue` — template structure lightly, `<style scoped>` mainly (`.screen`, `.split`, `.list`, `.workspace`, `.table` scroll containment).
- No API, store, or routing changes.
