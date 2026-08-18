# spotify-attribution-reveal

## Purpose

Spotify attribution arrows revealed on row hover must never linger as ghost elements after scrolling: their visibility is driven by explicit pointer state that scrolling resets, not by CSS `:hover` alone.

## ADDED Requirements

### Requirement: Attribution arrows reveal on pointer hover via explicit state

In every hover-reveal container, the Spotify attribution arrow SHALL become visible when the pointer enters its row and hidden when the pointer leaves it, driven by state the component manages from pointer events rather than by a CSS `:hover` selector. Keyboard focus inside the row SHALL keep revealing the arrow. Sites that display the arrow permanently (History, re-match modal) SHALL be unaffected.

#### Scenario: Pointer enters and leaves a row

- **WHEN** the pointer enters a hover-reveal row and later leaves it
- **THEN** the arrow becomes visible on enter and hidden on leave

#### Scenario: Keyboard focus reaches the arrow

- **WHEN** focus moves into a hover-reveal row via keyboard navigation
- **THEN** the arrow is visible while focus remains inside the row

### Requirement: Scrolling never leaves ghost arrows visible

When any scrolling occurs in a view containing hover-reveal rows, every arrow revealed by pointer hover SHALL be hidden, and SHALL only reappear after a new pointer enter on a row. At no time after a scroll SHALL more than one hover-revealed arrow remain visible, in any of the hover-reveal sites (Library sources and tracks, Events, Missing center, add-source picker and preview).

#### Scenario: Scrolling a list with a revealed arrow

- **WHEN** an arrow is revealed by hover and the user scrolls the list
- **THEN** the arrow hides, and no other row's arrow appears without a fresh pointer enter

#### Scenario: Hovering again after a scroll

- **WHEN** after scrolling the user moves the pointer over a row
- **THEN** exactly that row's arrow is revealed
