## Purpose

Give every Syncbox scroll surface a consistent dark, accessible appearance while preserving native macOS scrolling behavior and user display preferences.

## ADDED Requirements

### Requirement: Dark-only document contract
The application document SHALL declare dark as its only supported color scheme both before application styles load and in the global CSS cascade. Browser-provided controls, canvas surfaces, and scrollbars SHALL therefore use their native dark appearance even when the user's system appearance is light.

#### Scenario: Document loads under a light system appearance
- **WHEN** Syncbox loads while macOS is using its light appearance
- **THEN** the document and browser-provided UI render with the declared dark color scheme and no light document or scrollbar flash is visible

#### Scenario: Nested scroll container is created
- **WHEN** any screen or overlay creates a scrollable descendant
- **THEN** the descendant inherits the application's dark color-scheme contract without requiring component-specific theme signaling

### Requirement: Native scrollbars are the baseline
Every scrollable area SHALL preserve the native macOS scrollbar model, normal platform width, overlay behavior, scrolling input support, and user-selected visibility preference. The application SHALL NOT hide scrollbars, force a thinner width, or replace them with custom application controls.

#### Scenario: Scrollbars are configured to show automatically
- **WHEN** the macOS "Show scroll bars" preference is set to "Automatically based on mouse or trackpad"
- **THEN** each application scroll surface follows the native automatic visibility and overlay behavior

#### Scenario: Scrollbars are configured to show while scrolling
- **WHEN** the macOS "Show scroll bars" preference is set to "When scrolling"
- **THEN** each application scroll surface reveals its native scrollbar during scrolling and allows it to recede according to the system behavior

#### Scenario: Scrollbars are configured to always show
- **WHEN** the macOS "Show scroll bars" preference is set to "Always"
- **THEN** each application scroll surface keeps a visible, operable native scrollbar with its normal pointer target

### Requirement: Progressive token-based scrollbar colors
Where the active WKWebView version supports application scrollbar colors and native dark scrollbars do not provide sufficient visual integration, the application SHALL apply global colors sourced from design tokens. Any application-provided scrollbar track color SHALL be transparent, and any thumb color SHALL remain distinguishable from adjacent dark surfaces. Unsupported WKWebView versions SHALL fall back cleanly to native dark scrollbars.

#### Scenario: WKWebView supports the global color enhancement
- **WHEN** the supported scrollbar-color capability is available and the enhancement is enabled
- **THEN** scroll thumbs use the designated dark-theme token, tracks remain transparent, and component-local raw color copies are unnecessary

#### Scenario: WKWebView does not support the color enhancement
- **WHEN** the supported scrollbar-color capability is unavailable
- **THEN** the browser ignores the enhancement and all scroll surfaces continue to use native dark scrollbars without losing scrolling functionality

### Requirement: Global coverage of application scroll surfaces
The scrollbar contract SHALL apply to the main routed content and every nested scroll container, including tables, lists, panels, onboarding content, and modal content. Adding a new scroll container SHALL inherit the global behavior unless a documented accessibility requirement demands a scoped exception.

#### Scenario: User scrolls a primary content surface
- **WHEN** main content, a table, a list, or a panel overflows
- **THEN** its scrollbar follows the same dark native baseline and progressive color behavior as the application viewport

#### Scenario: User scrolls overlay content
- **WHEN** onboarding or modal content overflows its available height
- **THEN** its scrollbar follows the same dark native baseline and progressive color behavior without clipping content or controls

### Requirement: Scrollbar accessibility is preserved
Scrollbar styling SHALL preserve keyboard scrolling, wheel and trackpad scrolling, native pointer targets, and visible thumb-to-background contrast. The application SHALL not use a hidden or reduced-width scrollbar as part of this change.

#### Scenario: User relies on pointer interaction
- **WHEN** a scrollbar is visible and the user points to its thumb or track
- **THEN** the native-size target remains available and operable

#### Scenario: User relies on non-pointer scrolling
- **WHEN** a focused scroll surface receives supported keyboard, wheel, or trackpad input
- **THEN** it scrolls as before the visual unification

### Requirement: Scrollbar visual verification
Release verification SHALL exercise the current macOS development host with every macOS scrollbar display preference and representative main-content, table or panel, onboarding, and modal scroll surfaces. The recorded evidence SHALL identify the exact macOS and Safari/WebKit patch versions and SHALL NOT imply coverage of untested macOS versions.

#### Scenario: Scrollbar verification matrix is executed
- **WHEN** the change is prepared for release
- **THEN** native visibility behavior, transparent tracks, dark thumb appearance, pointer targets, and scrolling input are visually checked on the recorded current host without treating jsdom output as native scrollbar evidence or claiming unexecuted cross-version coverage
