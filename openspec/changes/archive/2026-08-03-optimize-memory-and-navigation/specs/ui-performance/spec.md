## Purpose

Keep Syncbox responsive as the library grows (2 000–10 000 tracks): screen switches never freeze the app, large tables scroll smoothly, and background refreshes never stall the main thread.

## ADDED Requirements

### Requirement: Screen switches complete without perceptible freeze
Navigating between screens via the sidebar SHALL NOT block the main thread for a duration proportional to the library size. Any work proportional to the full dataset (fetching, diffing, re-rendering) SHALL happen off the critical navigation path so the target screen becomes interactive immediately.

#### Scenario: Switching to the Library with a large dataset
- **WHEN** the user opens the Library screen while 10 000 tracks are followed
- **THEN** the screen renders its last known state and responds to input without a perceptible freeze, and any data refresh proceeds without blocking interaction

#### Scenario: Leaving a heavy screen
- **WHEN** the user navigates from the Library to any other screen
- **THEN** the destination screen becomes interactive immediately, unaffected by the size of the Library dataset

### Requirement: Silent refresh must not re-render or re-compare the full dataset synchronously
Re-entering a screen SHALL show the last known state instantly and refresh silently, per the existing contract. The unchanged-data check SHALL be cheap: the application SHALL NOT serialize or deep-compare the entire dataset on the main thread on every re-entry, and unchanged data SHALL NOT cause the large tables to re-render.

#### Scenario: Re-entering the Library with unchanged data
- **WHEN** the user returns to the Library and the backend data has not changed
- **THEN** no visible re-render of the table occurs and the main thread is not blocked by a whole-dataset comparison

#### Scenario: Re-entering the Library after a change
- **WHEN** the user returns to the Library after tracks changed on the backend
- **THEN** the updated rows appear without a full-screen skeleton and without a freeze proportional to library size

### Requirement: Large track tables are virtualized
Track tables that can exceed a few hundred rows (Library review table, Events tracklist) SHALL render only the rows near the viewport. Scrolling SHALL remain smooth at 10 000 tracks. Row height, hover actions, selection affordances, and keyboard/scrollbar behavior SHALL remain visually and functionally identical to the current design.

#### Scenario: Scrolling a 10 000-track Library
- **WHEN** the user scrolls the Library table containing 10 000 visible tracks
- **THEN** scrolling is smooth, the DOM holds only the rows near the viewport, and each row renders identically to the non-virtualized design

#### Scenario: Select-all over a filtered, virtualized table
- **WHEN** the user activates select-all while a filter chip narrows the table
- **THEN** the selection covers every filtered track — including rows not currently rendered — exactly as it does today

#### Scenario: Acting on an off-screen selected row
- **WHEN** the user applies a bulk action (apply, tag edit) with selected rows scrolled out of view
- **THEN** the action covers all selected tracks regardless of whether their rows are currently in the DOM

### Requirement: Inactive screens hold bounded memory
Screens that are not displayed SHALL NOT retain an unbounded DOM or data footprint indefinitely. Repeatedly visiting all screens in one session SHALL NOT grow memory without bound. Returning to a previously visited screen SHALL still restore its scroll position, active filters, and selection.

#### Scenario: Long session cycling through screens
- **WHEN** the user switches between all screens repeatedly during a long session
- **THEN** the application's memory footprint stays bounded rather than accumulating per visit

#### Scenario: Returning to a heavy screen late in a long session
- **WHEN** the user returns to the Library late in a long session, after many navigations across all screens
- **THEN** the screen restores its scroll position, filters, and selection, refreshing silently per the existing contract

### Requirement: Existing UX contracts are preserved
The performance work SHALL NOT regress the established behaviors: skeleton on first load only, silent refresh with no full-screen flash, selection preserved across silent refreshes, floating selection bar with zero layout shift.

#### Scenario: First load of a screen
- **WHEN** a screen loads for the first time in a session
- **THEN** a skeleton is shown once, and never again on subsequent re-entries

#### Scenario: Silent refresh during an active selection
- **WHEN** a silent refresh completes while the user has rows selected
- **THEN** the selection and the floating selection bar remain intact with no layout shift
