# Current-host macOS Window Chrome and Scrollbar QA Matrix

This matrix records the native release verification for the integrated macOS title-bar overlay and dark scrollbar contract. Every result must come from the packaged Tauri application on the named macOS installation. Vitest, jsdom, screenshots of the browser-only Vite shell, and static configuration tests are not native evidence.

## Result and evidence rules

- Allowed results: `PASS`, `PARTIAL`, `FAIL`, `BLOCKED`, and `NOT RUN`.
- Replace each `NOT RUN` cell with the result plus an evidence link or a concise note identifying the screenshot, screen recording, or observation log.
- Record the exact macOS, Safari, and WebKit build numbers before executing any row. An OS major version alone is insufficient. This matrix intentionally records only the current development host and makes no manual-compatibility claim for other macOS versions.
- Use `980x640` as the minimum window size and `1440x900` as the representative larger size.
- For maximized and fullscreen rows, the size is the pre-transition and restored size.

## Environment inventory

| Target | Exact macOS version | macOS build | Safari version | Safari build | WebKit version | WebKit build | Host and notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Current development host | 26.5.2 | 25F84 | 26.5.2 | 21624.2.5.11.8 | 21624 | 21624.2.5.11.8 | Local host inventory captured 2026-08-03 |

## Supplementary local observation log

These observations used an unsigned debug `.app` built from this change on the current host above. Most automated observations used the configured initial window size of `1280x820`; the manual minimum-size and drag observations explicitly identify `980x640`.

| Area | Result | Evidence or notes |
| --- | --- | --- |
| Normal focused chrome | PASS (supplementary) | Computer Use screenshot, 2026-08-03: native traffic lights are visible in the sidebar chrome; no light title-bar strip or redundant native title is visible; sidebar and main backgrounds reach the top edge. |
| Zoom/maximize and restore | PASS (supplementary) | Computer Use screenshots before and after the native zoom action: backgrounds, brand, navigation, routed content, and native controls remained aligned and usable after restoration. |
| Fullscreen and restore | PASS (supplementary) | Computer Use screenshots in settled fullscreen and after Escape: no exposed light surface or clipped shell content; native window controls returned after restoration. |
| Inactive appearance and first inactive click | BLOCKED | The automation API refocuses Syncbox whenever it captures the target window, so it cannot provide valid inactive traffic-light evidence. |
| Minimum-size focused chrome | PASS | Manual observation at the exact `980x640` minimum, 2026-08-03: native controls, dark background continuity, brand/navigation clearance, and routed content remained coherent. |
| Empty-region dragging | PASS | Manual observation at `980x640`, 2026-08-03: the freshly rebuilt bundle moved from the empty top region without selecting content. |
| Selection policy | PASS | Manual observation, 2026-08-03: sidebar chrome and controls do not select; useful track metadata, paths, and editable fields remain selectable. |
| Main routed content, `Always` | PARTIAL | The Settings route displayed a normal-width dark native scrollbar with a transparent track. Input behavior was not fully exercised on this surface. |
| Table/panel surfaces, `Always` | PASS (supplementary) | The Library route displayed independent normal-width scrollbars for the source panel and track table. Table content moved with both automated wheel scrolling and keyboard Page Down; thumb/track contrast and transparent tracks were visually observed. A direct pointer-thumb drag and a physical trackpad gesture remain unverified. |
| Onboarding, `Always` | PARTIAL | All onboarding steps remained visible and operable without title-bar overlap at `1280x820`; this size did not force the onboarding surface to overflow. The pre-existing completed-onboarding state was restored after the check. |
| Modal scrolling | NOT RUN | Requires the mandatory size/preference matrix run. |
| Scrollbar preferences | PARTIAL | The host preference was `Always` before and after QA. `Automatic` and `When scrolling` were not changed or claimed as tested. |

## Window chrome matrix

Every result cell covers all of the following checks: native traffic-light placement and full hit targets; dark window/webview background continuity; brand and navigation clearance; focused or inactive native appearance; dragging from the empty region; sidebar routes; kept-alive routed content; the Settings shortcut; Rekordbox banner; onboarding; consent; backend-down state; modals; and coherent transition and restoration behavior.

| Case | Starting/restored size | Window state | Current host result / evidence |
| --- | --- | --- | --- |
| C01 | 980x640 | Normal, focused | PARTIAL — minimum size, focused chrome, empty-region dragging, and selection policy passed manually; remaining overlay cases are not yet run |
| C02 | 980x640 | Normal, inactive | NOT RUN |
| C03 | 980x640 | Maximized, then restored | NOT RUN |
| C04 | 980x640 | Fullscreen, then restored | NOT RUN |
| C05 | 1440x900 | Normal, focused | NOT RUN |
| C06 | 1440x900 | Normal, inactive | NOT RUN |
| C07 | 1440x900 | Maximized, then restored | NOT RUN |
| C08 | 1440x900 | Fullscreen, then restored | NOT RUN |

## Scrollbar and scrolling matrix

Every result cell covers native visibility behavior, normal native pointer target size, a distinguishable dark thumb, a transparent track where `scrollbar-color` is supported, and successful keyboard, mouse-wheel, and trackpad scrolling. `Auto` means the macOS “Automatically based on mouse or trackpad” preference; `Scrolling` means “When scrolling”.

| Case | Size | Surface | macOS preference | Current host result / evidence |
| --- | --- | --- | --- | --- |
| S01 | 980x640 | Main routed content | Auto | NOT RUN |
| S02 | 980x640 | Main routed content | Scrolling | NOT RUN |
| S03 | 980x640 | Main routed content | Always | NOT RUN |
| S04 | 980x640 | Table or panel | Auto | NOT RUN |
| S05 | 980x640 | Table or panel | Scrolling | NOT RUN |
| S06 | 980x640 | Table or panel | Always | NOT RUN |
| S07 | 980x640 | Onboarding | Auto | NOT RUN |
| S08 | 980x640 | Onboarding | Scrolling | NOT RUN |
| S09 | 980x640 | Onboarding | Always | NOT RUN |
| S10 | 980x640 | Modal content | Auto | NOT RUN |
| S11 | 980x640 | Modal content | Scrolling | NOT RUN |
| S12 | 980x640 | Modal content | Always | NOT RUN |
| S13 | 1440x900 | Main routed content | Auto | NOT RUN |
| S14 | 1440x900 | Main routed content | Scrolling | NOT RUN |
| S15 | 1440x900 | Main routed content | Always | NOT RUN |
| S16 | 1440x900 | Table or panel | Auto | NOT RUN |
| S17 | 1440x900 | Table or panel | Scrolling | NOT RUN |
| S18 | 1440x900 | Table or panel | Always | NOT RUN |
| S19 | 1440x900 | Onboarding | Auto | NOT RUN |
| S20 | 1440x900 | Onboarding | Scrolling | NOT RUN |
| S21 | 1440x900 | Onboarding | Always | NOT RUN |
| S22 | 1440x900 | Modal content | Auto | NOT RUN |
| S23 | 1440x900 | Modal content | Scrolling | NOT RUN |
| S24 | 1440x900 | Modal content | Always | NOT RUN |

## Known unfocused-drag limitation

Tauri tracks an upstream macOS limitation in [tauri-apps/tauri#4316](https://github.com/tauri-apps/tauri/issues/4316): an element marked with `data-tauri-drag-region` cannot begin a drag while its window is unfocused. Record this separately from the chrome matrix; do not replace the native title bar or enable first-mouse behavior as a workaround.

On the current development host:

1. Make Syncbox inactive and confirm that all three native inactive traffic lights remain operable.
2. Attempt a drag directly from the empty web drag region and record the observed limitation.
3. Focus the window, retry the same empty region, and confirm normal dragging.
4. Attach evidence or notes here: `current host — NOT RUN`.

## References

- [Tauri window configuration](https://v2.tauri.app/reference/config/#windowconfig)
- [Tauri window customization and drag regions](https://v2.tauri.app/learn/window-customization/)
- [CSS Color Adjustment: `color-scheme`](https://drafts.csswg.org/css-color-adjust-1/#color-scheme-prop)
- [CSS Scrollbars Styling: `scrollbar-color`](https://drafts.csswg.org/css-scrollbars/#scrollbar-color)
