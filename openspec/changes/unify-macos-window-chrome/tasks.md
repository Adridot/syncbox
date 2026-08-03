## 1. Native Window Configuration

- [x] 1.1 Update the `main` Tauri window to keep decorations, use the overlay title-bar style, hide the native title, force the dark theme, set `#0a0c10` as the window/webview background, and place traffic lights at logical position `{ x: 16, y: 18 }` without enabling transparency or private APIs.
- [x] 1.2 Add a standard-library configuration test that finds the `main` window by label, asserts every overlay field and the macOS 14.0 minimum, and verifies that the configured background equals the `--bg-base` CSS token.

## 2. Dark Document and Scrollbar Contract

- [x] 2.1 Add shared top-chrome, traffic-light-clearance, and scrollbar-thumb tokens to `ui/src/styles/tokens.css`, keeping all new visual values token-based.
- [x] 2.2 Declare the document as dark-only in `ui/index.html` before application style loading and on `:root` in `ui/src/styles/base.css`.
- [x] 2.3 Add a global feature-detected `scrollbar-color` enhancement with a token-based thumb and transparent track, while leaving native scrollbar width, visibility, and Tauri scrollbar style untouched.
- [x] 2.4 Audit the main content, table/list, panel, onboarding, and modal overflow containers to confirm they inherit the global contract and remove or reconcile only conflicting component-local scrollbar rules.

## 3. Vue Application Shell Integration

- [x] 3.1 Add one empty top drag element owned by `App.vue`, mark it as a Tauri drag region, exclude the shared native-control clearance, and ensure it has no interactive descendants.
- [x] 3.2 Extend the existing sidebar and main backgrounds to the top edge and offset their first interactive content by the shared chrome height without changing scroll ownership, minimum dimensions, or overlay stacking.
- [x] 3.3 Adjust the sidebar brand and navigation spacing to preserve existing visual alignment below the native traffic lights, with no HTML window controls or component-specific duplicate geometry.
- [x] 3.4 Verify in the web shell that sidebar routes, kept-alive views, Settings shortcut, banners, onboarding, consent, backend-down state, and modals retain their existing structure and behavior.

## 4. Automated Verification

- [x] 4.1 Add focused Vitest shell tests asserting that the drag region is empty and non-interactive and that brand, navigation, banners, and routed content remain outside it.
- [x] 4.2 Add authored-contract tests for the early dark document declaration, inherited CSS color scheme, feature-detected transparent-track scrollbar colors, and absence of hidden or reduced-width scrollbar styling.
- [x] 4.3 Run the new configuration test, the full sidecar and UI test suites, UI type checking, and the production UI build; fix regressions without changing routes or adding dependencies.

## 5. macOS Visual Verification

- [x] 5.1 Create a recorded QA matrix for the current macOS development host that captures the exact OS and Safari/WebKit patch versions, window size, window state, scrollbar preference, result, and evidence or notes without claiming coverage of untested macOS versions.
- [ ] 5.2 On the current macOS development host, verify native traffic-light placement and hit targets, dark background continuity, brand/navigation clearance, focused and inactive appearance, empty-region dragging, and normal/maximized/fullscreen transitions at `980x640` and a representative larger size.
- [ ] 5.3 On the current macOS development host, verify main-content, table or panel, onboarding, and modal scrolling with "Automatically based on mouse or trackpad", "When scrolling", and "Always", including native target size, transparent tracks where supported, and keyboard, wheel, and trackpad input.
- [ ] 5.4 On the current macOS development host, record the known unfocused-overlay drag limitation separately, confirm that native inactive traffic lights remain operable, and do not use jsdom results as evidence for any native macOS chrome or scrollbar behavior.
