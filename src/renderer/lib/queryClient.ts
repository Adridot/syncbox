import { QueryClient } from "@tanstack/vue-query";

// Single QueryClient for the renderer (one window = one client). Exported so
// non-component code — e.g. the SSE acquisition stream — can invalidate queries
// directly via `queryClient.invalidateQueries(...)`; components should prefer
// `useQueryClient()`.
//
// The defaults reproduce the old useRefreshManager contract in one place:
//   * refetchOnWindowFocus / refetchOnReconnect -> the "refresh when the tab
//     becomes visible again" watcher.
//   * a short staleTime so a freshly-focused view doesn't refetch on every
//     mount while still feeling live.
// Per-query `refetchInterval` (5s / 30s / 60s) replaces the individual
// useIntervalFn timers.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
      retry: 1,
      staleTime: 3_000,
    },
  },
});
