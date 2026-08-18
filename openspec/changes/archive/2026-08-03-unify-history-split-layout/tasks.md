## 1. Pin the screen frame (mirror LibraryScreen)

- [x] 1.1 In `ui/src/screens/HistoryScreen.vue` `<style scoped>`, make `.screen` fill the window like Library: `height: 100%; display: flex; flex-direction: column; min-height: 0; box-sizing: border-box;`
- [x] 1.2 Mark the fixed frame elements as non-growing: `flex: none` on `.head`, `.live-banner`, and `.toolbar`
- [x] 1.3 Give `.split` the remaining height: `flex: 1; min-height: 0;` and drop `align-items: flex-start` so both panes stretch to the frame height

## 2. Independent pane scrolls

- [x] 2.1 On `.list`, replace `max-height: 70vh` with `min-height: 0` (keep `overflow-y: auto`) so it scrolls within the frame height
- [x] 2.2 Make `.workspace` a flex column with internal containment: `display: flex; flex-direction: column; min-height: 0;` (keep existing card background/border/`overflow: clip`)
- [x] 2.3 Keep `.ws-head` and `.banner` pinned with `flex: none`
- [x] 2.4 In the template, wrap the tracklist rows (the `v-for` over `displayRows`) in a `<div class="table-body">` inside `.table`, matching Library's `.table` / `.table-head` / `.table-body` structure
- [x] 2.5 Style the scroll chain: `.table { flex: 1; min-height: 0; display: flex; flex-direction: column; }`, `.table-head { flex: none; }`, `.table-body { flex: 1; min-height: 0; overflow-y: auto; }`

## 3. Verify against the spec scenarios

- [x] 3.1 With a long tracklist selected: no page-level scrollbar; header, chips, and both panes hold position; `.ws-head` (name, meta, export/hide) stays visible and operable while the tracklist scrolls
- [x] 3.2 Scrolling either pane never moves the other; the left list is fully visible while browsing a tracklist
- [x] 3.3 Loading / error / empty states and the no-selection case still render correctly inside the pinned frame
- [x] 3.4 Behavior untouched: selection, rename, export, hide/unhide, live banner and live poll append (frame and left-list scroll position undisturbed)
- [x] 3.5 Run the existing UI checks (`pnpm -C ui test` and lint) — no regressions
