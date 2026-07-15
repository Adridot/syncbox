# ui — Vue 3 front end

The six routed Syncbox destinations are Dashboard, Library, Events,
Collection Health, Missing, and Settings, plus the 10-step onboarding.
Collection Health contains Duplicates, Missing, Untagged, Smart Fixes, and
Backups tabs; Missing separates library, event, and collection scopes. Vite +
Vue 3 + TypeScript (strict), Pinia stores, vue-i18n (en/fr), no CSS framework
(design tokens in `src/styles/`).

Wiring rules (see [the unified specification](../docs/SPEC-UNIFIED.md),
especially §§6.3 and 6.12):

- One API client ([src/api/client.ts](src/api/client.ts)) — envelope handling
  for 423 (Rekordbox open), 409 (stale), 428 (consent) is centralized.
- One SSE client for the canonical job stream; stores decorate it.
- Every mutation goes through guarded components (`GuardedButton`,
  `DryRunModal`, `ConsentModal`) — the confirmed payload is exactly what is
  sent.

```sh
pnpm dev          # standalone against a running sidecar (localhost:5173)
pnpm test         # vitest
pnpm typecheck    # vue-tsc
pnpm build        # typecheck + production build (used by tauri build)
```

The app version is injected at build time from `package.json`
(`__APP_VERSION__`) — the single version source for the whole repo.
