## Why

Syncbox currently renders its dark studio interface below a conventional macOS title bar, leaving a visually disconnected strip at the top of the window and inconsistent scrollbar appearance across nested scroll containers. A native title-bar overlay and a single dark scrollbar contract will make the shell feel coherent on the supported macOS 14+ baseline while retaining standard macOS window behavior.

## What Changes

- Configure the main Tauri window to keep native decorations and traffic-light controls while using the macOS overlay title-bar style, hiding the redundant title, forcing the native dark theme, matching native window and webview backgrounds to existing design tokens, and placing the traffic lights in the sidebar's top chrome area.
- Extend the Vue application shell to the top window edge, reserve non-interactive space for the native controls, and provide a dedicated draggable region without recreating window controls in HTML.
- Preserve the existing sidebar, content layout, routing, and interactive behavior across normal, inactive, maximized, and fullscreen states.
- Declare Syncbox as dark-only at the document and CSS levels, use native dark scrollbars by default, and apply token-based scrollbar colors progressively where supported, with transparent tracks and accessible native pointer targets.
- Cover every application scroll surface, including main content, tables, panels, onboarding, and modals.
- Add automated Tauri configuration and Vue shell-contract tests, plus a current-host visual verification matrix for window states, window sizes, and scrollbar display preferences; jsdom tests will not attempt to render or validate native macOS chrome, and no manual evidence is claimed for macOS versions that were not tested.
- Add no dependencies.

## Capabilities

### New Capabilities

- `macos-window-chrome`: Native macOS title-bar overlay behavior and its integration with the Vue application shell.
- `dark-scrollbars`: Dark-only document signaling and consistent, accessible scrollbar behavior across application scroll containers.

### Modified Capabilities

None.

## Impact

- Tauri window configuration in `shell/src-tauri/tauri.conf.json` and configuration-focused automated tests.
- Vue shell structure and styling in `ui/src/App.vue`, `ui/src/components/AppSidebar.vue`, `ui/index.html`, and global design-token/base styles.
- Existing nested scroll containers in screens, tables, panels, onboarding flows, and modal components.
- UI-shell tests under `ui/src/**/__tests__` and manual macOS visual verification documentation.
- No routing, backend API, persistence, native-control replacement, or dependency changes.
