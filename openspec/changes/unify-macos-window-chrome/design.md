## Context

See `proposal.md` for motivation and the capability specs for observable behavior.

The application has one Tauri main window with native decorations, a macOS 14.0 minimum, and no title-bar customization. The Vue shell is a fixed-height flex layout: `AppSidebar.vue` paints `--bg-sidebar`, `App.vue` owns the `--bg-base` main scroll area, and both currently begin below the native title bar. `--bg-base` is `#0a0c10`; this is also the appropriate opaque startup color for the native window and webview because it is the broadest shell surface.

The main content region and several table, panel, onboarding, and modal elements scroll independently. Global CSS currently declares no color scheme or scrollbar contract. Tauri 2.11.5 is already locked and supports the required overlay, hidden title, theme, background, and traffic-light configuration, so the change needs no dependency or native extension work.

## Goals / Non-Goals

**Goals:**

- Keep native AppKit window controls and behaviors while letting the existing web shell paint through the title-bar area.
- Establish one explicit geometry contract for traffic-light placement, top clearance, and the drag-only region.
- Make dark browser-provided UI and scrollbars effective from initial document parsing through every nested scroll surface.
- Keep native scrollbar sizing and display-preference behavior, adding only progressively supported token colors.
- Separate static configuration and DOM/style contract tests from native visual verification.

**Non-Goals:**

- Creating, drawing, or scripting HTML window controls.
- Adding vibrancy, transparency, custom AppKit code, runtime window-control APIs, or new dependencies.
- Redesigning the sidebar, routed screens, navigation, or scroll ownership.
- Claiming that jsdom can validate AppKit control rendering, WKWebView scrollbar rendering, focus appearance, or native fullscreen transitions.

## Decisions

### 1. Configure the existing decorated window directly

The main window configuration will explicitly set:

- `decorations: true`
- `titleBarStyle: "Overlay"`
- `hiddenTitle: true`
- `theme: "Dark"`
- `backgroundColor: "#0a0c10"`
- `trafficLightPosition: { "x": 16, "y": 18 }`

The explicit decorations flag protects the native-control requirement even though `true` is currently the default. The background is opaque and matches `--bg-base`, avoiding private transparency APIs and reducing startup or resize flashes. A configuration contract test will compare the configured background with the CSS token so this unavoidable native/web duplication cannot drift silently.

The traffic-light coordinates are logical positions and pair with the web geometry in Decision 2. Their final visual calibration is part of the current-host macOS matrix; any adjustment must update both the configuration assertion and the clearance tokens.

Alternatives considered:

- A frameless window with HTML controls was rejected because it loses native inactive, hover, accessibility, zoom, and fullscreen behavior and directly violates the requirements.
- Rust or JavaScript calls after startup were rejected because these values are available declaratively, would add timing and flash risks, and would complicate state handling without benefit.
- A transparent window was rejected because it requires macOS private APIs and is unnecessary for an opaque dark studio shell.

### 2. Use one empty drag layer and shared top-chrome tokens

Add design tokens for a `52px` top-chrome height and an `80px` left traffic-light clearance. The sidebar and main surfaces will continue to paint their own existing backgrounds to the top edge, while their first interactive content is offset below the top-chrome height.

`App.vue` will own one empty, absolutely positioned drag element across the top of the shell. It begins after the `80px` native-control clearance, spans the remaining window width, carries Tauri's drag-region marker, and has no children. The element's geometry is derived entirely from the shared tokens. Native traffic lights occupy the excluded left segment; brand, banners, route content, and navigation start below the top chrome.

This structure remains stable through normal, inactive, maximized, and fullscreen transitions without mirroring native window state into Vue. In fullscreen, the same dark top-chrome surface remains intentional and non-interactive while AppKit owns native control visibility; avoiding a reactive fullscreen class prevents content jumps and event-listener lifecycle complexity. The visual matrix will confirm that this stable clearance is acceptable at both required window sizes.

Alternatives considered:

- Marking the brand or the entire sidebar as draggable was rejected because nested links and controls could lose pointer interactions.
- Multiple component-local drag regions and offsets were rejected because their geometry could diverge.
- Runtime fullscreen detection was rejected because no functional behavior requires a different layout and the static shell avoids transition reflow.

### 3. Declare dark-only behavior at document and cascade boundaries

Add `<meta name="color-scheme" content="dark">` in `ui/index.html` before style loading, and add `color-scheme: dark` on `:root` in global CSS. The meta declaration lets WKWebView select dark browser chrome during initial parsing; the CSS declaration makes the behavior inherited by dynamically mounted and nested content.

`dark` is used rather than `light dark` because Syncbox has no light design and the requirement is dark-only. The native window independently uses Tauri's dark theme so AppKit and WKWebView agree even when macOS itself is in light appearance.

Alternative considered: relying only on the system appearance was rejected because a light system would reintroduce light browser controls and scrollbars inside the dark application.

### 4. Prefer native dark scrollbars, then enhance with the standard property

Do not set `scrollbar-width`, do not hide scrollbars, and do not set Tauri's `scrollBarStyle` because Tauri documents that the option has no macOS effect beyond the default. The dark `color-scheme` declaration is the baseline that lets WebKit render native dark scrollbars and honor the user's macOS visibility preference.

Add scrollbar thumb tokens to `tokens.css`. In `base.css`, use a global `@supports (scrollbar-color: auto)` block to apply `scrollbar-color: var(--scrollbar-thumb) transparent` from the root. The property is inherited by scroll containers, so main content, tables, panels, onboarding, and modals receive one contract without component-specific selectors. Older WKWebView versions ignore the block and retain native dark scrollbars. No `::-webkit-scrollbar` fallback will be added: it would create a second, vendor-specific rendering model on the older versions where the native baseline is most valuable.

Alternative considered: explicit `::-webkit-scrollbar` sizing and painting was rejected because it can change native targets and overlay behavior, duplicates rules across containers, and is unnecessary once dark color-scheme signaling is correct.

### 5. Test configuration and web-shell contracts at their real boundaries

Add a standard-library pytest configuration test alongside the repository's existing cross-package configuration tests. It will parse `tauri.conf.json`, find the `main` window by label, assert all native overlay fields and logical traffic-light coordinates, retain the macOS 14 minimum, and compare `backgroundColor` with `--bg-base` from `tokens.css`.

Add focused Vitest tests for the Vue shell and document/style contracts. These tests will assert that:

- the drag element exists, carries the drag marker, is empty, and has no interactive descendants;
- brand, navigation, banners, and routed content remain outside the drag element;
- the document declares a dark color scheme before application startup;
- global CSS declares dark color-scheme and progressive transparent-track scrollbar colors without reducing or hiding scrollbar width;
- the existing route structure and sidebar destinations remain unchanged.

The tests intentionally inspect configuration, DOM structure, and authored style contracts only. Native traffic-light visuals, inactive appearance, drag execution, scrollbar rendering, user preferences, and fullscreen behavior remain manual macOS verification items.

### 6. Record a current-host state-and-preference visual matrix

Create a concise QA checklist for the current macOS development host, recording its exact macOS and Safari/WebKit patch versions. Exercise normal, inactive, maximized, and fullscreen states at `980x640` and a representative larger size. Verify native controls, background continuity, brand/navigation alignment, drag and control hit areas, route and overlay behavior, and restoration after state transitions. Keep macOS 14 as the supported minimum, but do not require or claim manual evidence for other macOS versions in this change.

On that host, repeat representative main-content, table or panel, onboarding, and modal overflow cases with macOS "Show scroll bars" set to "Automatically based on mouse or trackpad", "When scrolling", and "Always".

## Risks / Trade-offs

- [Tauri overlay title-bar height and native control geometry can vary by macOS release] → Use explicit logical coordinates and generous `80px × 52px` reserved geometry; record that the current-host-only QA scope leaves cross-version visual risk unverified.
- [Tauri documents that a custom overlay drag region cannot initiate a drag while the window is unfocused] → Preserve native inactive traffic-light behavior, keep the empty drag region available after focus, and record this upstream limitation in the visual checklist rather than replacing native chrome.
- [The native background duplicates a CSS token as a JSON literal] → Add an automated equality check between `backgroundColor` and `--bg-base`.
- [Custom scrollbar colors are unavailable in older WKWebView versions] → Make `color-scheme: dark` the complete baseline and gate only the optional standard color enhancement with feature detection.
- [A stable top-chrome band consumes vertical space in fullscreen] → Keep it deliberately small and visually continuous, verify the minimum window and fullscreen cases, and prefer layout stability over runtime fullscreen reflow.
- [Global scrollbar styling could expose a component that depends on an opaque track] → Keep the track transparent by contract and include every known scroll-surface category in visual verification.

## Migration Plan

1. Add the native window configuration and its static contract test first.
2. Add the shared geometry and scrollbar tokens, document-level dark declaration, and global progressive scrollbar rule.
3. Integrate the empty drag layer and top clearance into the application shell without changing router or screen ownership.
4. Add UI-shell contract tests and run existing UI, sidecar, typecheck, and build checks.
5. Execute and record the current-host macOS state/size/preference matrix before release.

Rollback is configuration- and style-only: revert the overlay window fields, drag layer, top clearance, dark document declaration, and scrollbar enhancement together. No user data, API, or migration state is involved.

## References

- [Tauri v2 window configuration](https://v2.tauri.app/reference/config/#windowconfig) documents `Overlay`, `hiddenTitle`, `theme`, `backgroundColor`, and the requirement that `trafficLightPosition` use overlay style with decorations enabled.
- [Apple: Supporting Dark Mode in Web Content](https://developer.apple.com/videos/play/wwdc2019/511/) explains that color-scheme signaling updates WebKit's native form controls and scrollbars.
- [MDN: `color-scheme`](https://developer.mozilla.org/en-US/docs/Web/CSS/color-scheme) documents document-level signaling and early `<meta name="color-scheme">` placement.
- [MDN: `scrollbar-color`](https://developer.mozilla.org/en-US/docs/Web/CSS/scrollbar-color) documents inherited thumb/track colors and the contrast requirement.
- [MDN: `scrollbar-width`](https://developer.mozilla.org/en-US/docs/Web/CSS/scrollbar-width) cautions that thin or hidden scrollbars can reduce accessibility and pointer target size.
- [Safari 26 release notes](https://developer.apple.com/documentation/safari-release-notes/safari-26-release-notes) motivate recording the exact Safari/WebKit patch version of the tested host rather than inferring WebKit behavior from the macOS major version.
