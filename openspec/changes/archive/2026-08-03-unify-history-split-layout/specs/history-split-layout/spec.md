## Purpose

Make the Prestations screen's two panes behave as one coherent surface, matching the Library master/detail pattern: a window-height frame with independent internal scrolls.

## ADDED Requirements

### Requirement: The screen occupies the window height with no page-level scroll
The Prestations screen SHALL be pinned to the window height like the Library screen. The header, live banner, and filter chips SHALL stay in place; the page itself SHALL NOT scroll.

#### Scenario: Long tracklist is open
- **WHEN** a performance with a long tracklist is selected
- **THEN** the window shows no page-level scrollbar and the screen frame (header, chips, both panes) keeps its position

### Requirement: Each pane scrolls independently inside the shared frame
The performance list (left) and the tracklist workspace (right) SHALL each scroll internally, filling the available frame height. Scrolling one pane SHALL never move the other, and the left list SHALL remain fully visible while the user browses a tracklist. The `70vh` cap on the left list is removed in favor of the frame height.

#### Scenario: Scrolling the tracklist
- **WHEN** the user scrolls a long tracklist in the right pane
- **THEN** the left performance list stays in place and visible, and only the tracklist content moves

#### Scenario: Scrolling the performance list
- **WHEN** the user scrolls a long performance list in the left pane
- **THEN** the right workspace stays in place and only the list content moves

### Requirement: The workspace header stays visible while the tracklist scrolls
The selected performance's header (name, date/time/duration meta, export and hide actions, notes and banners) SHALL remain visible while the tracklist scrolls beneath it.

#### Scenario: Exporting after scrolling deep into a tracklist
- **WHEN** the user has scrolled to the bottom of a long tracklist
- **THEN** the performance name and the export/hide actions are still visible and operable without scrolling back up

### Requirement: Existing behaviors are unchanged
Selection, live polling and the live banner, rename, playlist export, and hide/unhide SHALL behave exactly as before; only the layout containment changes.

#### Scenario: Live set updates while scrolled
- **WHEN** the live poll appends tracks to the selected live performance
- **THEN** the update appears in the tracklist pane without disturbing the frame layout or the left list's scroll position
