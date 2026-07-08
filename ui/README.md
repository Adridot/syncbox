# ui — Vue 3 front end

The Syncbox screens: Dashboard, Library, Events, Collection health
(duplicates / untagged), Missing tracks, Settings, plus the 10-step
onboarding. Vite + Vue 3 + TypeScript (strict), Pinia stores, vue-i18n
(en/fr), no CSS framework (design tokens in `src/styles/`).

Wiring rules (see [docs/M4-PLAN.md](../docs/M4-PLAN.md) §4):

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
