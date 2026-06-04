import { useDocumentVisibility, useIntervalFn } from "@vueuse/core";
import { watch } from "vue";
import { useAcquisitionStream } from "./useAcquisitionStream";
import { useEventsStore } from "../stores/events";
import { useLibraryStore } from "../stores/library";
import { useSpotifyStore } from "../stores/spotify";
import { useSystemStore } from "../stores/system";
import { useUiStore } from "../stores/ui";

export function useRefreshManager() {
  const ui = useUiStore();
  const system = useSystemStore();
  const events = useEventsStore();
  const library = useLibraryStore();
  const spotify = useSpotifyStore();
  const visibility = useDocumentVisibility();

  // SSE stream pushes global acquisition jobs; when live we skip the redundant
  // poll-based job refreshes below.
  const { connected: streamConnected } = useAcquisitionStream();
  const refreshGlobalJobs = async () => {
    if (streamConnected.value) return;
    await events.refreshGlobalJobs();
  };

  async function runBackground(task: () => Promise<void>): Promise<void> {
    try {
      await task();
    } catch (error) {
      if (visibility.value === "visible") {
        console.warn("[refresh]", error);
      }
    }
  }

  // 5s — health, rekordbox, deemix + view-specific fast refresh
  useIntervalFn(async () => {
    if (visibility.value !== "visible" || !system.api) return;
    await runBackground(async () => {
      await system.refreshStatus();
      if (ui.activeView === "library" && library.activeReview) {
        await Promise.all([
          library.refreshActiveReview(),
          library.refreshSources(),
          streamConnected.value ? Promise.resolve() : library.refreshGlobalJobs(),
        ]);
      }
      if (ui.activeView === "events" || ui.activeView === "downloadCenter") {
        await events.refreshSummaries();
        await refreshGlobalJobs();
      }
    });
  }, 5000);

  // 30s — slow background data
  useIntervalFn(async () => {
    if (visibility.value !== "visible" || !system.api) return;
    await runBackground(async () => {
      await Promise.all([
        library.refreshTagRules(),
        library.refreshSources(),
        events.refreshSummaries(),
        spotify.refreshRekordboxTags(),
        refreshGlobalJobs(),
      ]);
    });
  }, 30000);

  // 60s — spotify playlists (only when library/events view is active)
  useIntervalFn(async () => {
    if (visibility.value !== "visible" || !system.api) return;
    if (!["library", "events"].includes(ui.activeView)) return;
    await runBackground(() => spotify.fetchAllPlaylists());
  }, 60000);

  // 5s — active event refresh
  useIntervalFn(async () => {
    if (visibility.value !== "visible" || !system.api || !events.activeEvent) return;
    await runBackground(() => events.refreshActiveEvent());
  }, 5000);

  // 15s — staging scan
  useIntervalFn(async () => {
    if (visibility.value !== "visible" || !system.api || !events.activeEvent) return;
    if (!["events", "downloadCenter"].includes(ui.activeView)) return;
    await runBackground(() => events.scanStaging());
  }, 15000);

  // On tab becomes visible — trigger all refreshes immediately
  watch(visibility, (v) => {
    if (v !== "visible" || !system.api) return;
    void runBackground(() => system.refreshStatus());
    if (["library", "events"].includes(ui.activeView)) {
      void runBackground(() => spotify.fetchAllPlaylists());
      void runBackground(() => spotify.refreshRekordboxTags());
    }
    if (events.activeEvent) {
      void runBackground(() => events.refreshActiveEvent());
    }
  });

  // On view change — refresh view-specific data
  watch(() => ui.activeView, (view) => {
    if (!system.api) return;
    if (view === "library" || view === "events") {
      void runBackground(() => spotify.fetchAllPlaylists());
      void runBackground(() => spotify.refreshRekordboxTags());
    }
    if (view === "library") {
      void runBackground(async () => {
        library.refreshSources();
        if (library.activeReview) await library.refreshActiveReview();
      });
    }
    if (view === "events" || view === "downloadCenter") {
      if (events.activeEvent) void runBackground(() => events.refreshActiveEvent());
    }
  });

  // On active event change — immediately fetch its state
  watch(() => events.activeEvent?.id, (eventId) => {
    if (eventId && system.api) {
      void runBackground(() => events.refreshActiveEvent());
    }
  });
}
