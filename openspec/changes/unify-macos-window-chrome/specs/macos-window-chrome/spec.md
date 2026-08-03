## Purpose

Provide a coherent dark macOS window surface that retains native window behavior while integrating the title-bar area with the Syncbox application shell.

## ADDED Requirements

### Requirement: Native macOS title-bar overlay
On macOS 14 and later, the main application window SHALL retain native decorations and native traffic-light controls, SHALL present its title bar as an overlay over application content, SHALL omit the redundant visible window title, and SHALL use a native dark appearance. The native window surface and web content surface SHALL use colors matching the existing dark design tokens so that startup and exposed background areas do not introduce a light or mismatched strip.

#### Scenario: Main window opens in its normal state
- **WHEN** Syncbox opens its main window on macOS 14 or later
- **THEN** the application content reaches the top edge beneath a native overlay title bar, the native traffic lights remain available, no redundant window title is visible, and the visible native and web surfaces form one dark composition

#### Scenario: Window is inactive
- **WHEN** the main window loses focus
- **THEN** macOS continues to render the native traffic lights in their system-defined inactive state and Syncbox does not replace or cover them with HTML controls

### Requirement: Native traffic-light placement and reservation
The application SHALL position the native traffic-light controls explicitly within the sidebar's top chrome area and SHALL reserve sufficient non-interactive space around their full native hit area. Brand, navigation, and main-content controls SHALL remain visually aligned with the existing design system and SHALL not overlap the reserved traffic-light area.

#### Scenario: Sidebar is visible with native controls
- **WHEN** the main window is displayed at any supported non-fullscreen size
- **THEN** all three native traffic-light controls appear within the sidebar chrome, with the brand and first navigation item aligned below or beside the reserved area without overlap or clipping

#### Scenario: User operates a traffic-light control
- **WHEN** the user points to and activates a native close, minimize, or zoom control
- **THEN** the native hit target receives the interaction without interception by application content

### Requirement: Dedicated draggable top region
The application shell SHALL provide a draggable top region that is visually continuous with the sidebar and main backgrounds. The draggable region SHALL contain no interactive application control and SHALL not extend over native traffic lights, navigation links, buttons, fields, or other interactive content.

#### Scenario: User drags empty top chrome
- **WHEN** the user drags an unoccupied point in the designated top region while the window is movable
- **THEN** macOS moves the window using native window-drag behavior

#### Scenario: User interacts near the drag region
- **WHEN** the user activates a native traffic light or any application control adjacent to the top region
- **THEN** the intended control receives the interaction and no window drag begins

### Requirement: Window-state resilience
The integrated shell SHALL remain coherent and usable in normal, inactive, maximized, and fullscreen window states. State transitions SHALL not clip the brand, navigation, banners, routed content, or native controls; SHALL not introduce an exposed light surface; and SHALL never display HTML replicas of macOS window controls.

#### Scenario: Window is maximized and restored
- **WHEN** the user maximizes the main window and later restores it
- **THEN** the sidebar, top chrome, traffic-light reservation, draggable region, and routed content remain correctly aligned and usable in both states

#### Scenario: Window enters and exits fullscreen
- **WHEN** the user enters fullscreen and later returns to a windowed state
- **THEN** the shell uses the available top area without clipping or blocking content, native controls follow macOS fullscreen behavior, and the windowed overlay alignment is restored on exit

### Requirement: Existing application behavior is preserved
The title-bar integration SHALL preserve the current application layout model, sidebar navigation destinations, route transitions, kept-alive routed views, overlays, keyboard shortcuts, and minimum supported window dimensions.

#### Scenario: User navigates after the chrome change
- **WHEN** the user follows any existing sidebar route or opens Settings with the existing keyboard shortcut
- **THEN** the same destination and application behavior occur as before the title-bar integration

#### Scenario: Overlay content is displayed
- **WHEN** onboarding, consent, backend-down, guard, or modal content is shown
- **THEN** it remains visible and operable without being hidden behind the title-bar overlay or reserved traffic-light area

### Requirement: macOS visual compatibility verification
The release verification SHALL cover the current macOS development host and SHALL exercise normal, inactive, maximized, and fullscreen states at the minimum supported window size and a representative larger size. The recorded evidence SHALL identify the exact macOS and Safari/WebKit patch versions and SHALL NOT imply manual coverage of untested macOS versions. This verification scope does not change the macOS 14 minimum support contract.

#### Scenario: Chrome verification matrix is executed
- **WHEN** the change is prepared for release on the recorded current macOS host
- **THEN** that host is visually checked for native control placement, dark background continuity, drag behavior, content clearance, and state transitions, with results recorded outside jsdom and other macOS versions explicitly left unclaimed
