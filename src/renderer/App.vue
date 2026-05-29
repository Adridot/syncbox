<script setup lang="ts">
import { AlertTriangle, CheckCircle2 } from "@lucide/vue";
import { onMounted } from "vue";
import AppShell from "./components/AppShell.vue";
import DashboardView from "./views/DashboardView.vue";
import DownloadMatchCenterView from "./views/DownloadMatchCenterView.vue";
import EventImportsView from "./views/EventImportsView.vue";
import LibraryView from "./views/LibraryView.vue";
import SettingsView from "./views/SettingsView.vue";
import { useRefreshManager } from "./composables/useRefreshManager";
import { useEventsStore } from "./stores/events";
import { useLibraryStore } from "./stores/library";
import { useProposalsStore } from "./stores/proposals";
import { useSettingsStore } from "./stores/settings";
import { useSpotifyStore } from "./stores/spotify";
import { useSystemStore } from "./stores/system";
import { useUiStore } from "./stores/ui";

const ui = useUiStore();
const system = useSystemStore();
const settings = useSettingsStore();
const events = useEventsStore();
const library = useLibraryStore();
const spotify = useSpotifyStore();
const proposals = useProposalsStore();

useRefreshManager();

onMounted(async () => {
  await system.init();
  await Promise.all([
    system.refreshStatus(),
    settings.load(),
    library.refreshTagRules(),
    library.refreshSources(),
    library.refreshMappings(),
    proposals.refresh(),
    events.refreshSummaries(),
    events.refreshGlobalJobs(),
    spotify.refreshRekordboxTags(),
    spotify.fetchAllPlaylists().catch(() => {}),
  ]);
});
</script>

<template>
  <AppShell
    :active-view="ui.activeView"
    :health="system.health"
    :rekordbox-status="system.rekordboxStatus"
    :deemix-status="system.deemixStatus"
    :search-query="ui.searchQuery"
    :title="ui.pageTitle"
    @change-view="ui.navigateTo($event)"
    @update-search-query="ui.searchQuery = $event"
  >
    <div
      v-if="ui.errorMessage"
      class="absolute bottom-4 right-4 z-50 flex min-h-11 max-w-xl items-center gap-3 rounded border border-error/30 bg-error-container px-4 text-sm text-on-error-container shadow-xl"
    >
      <AlertTriangle :size="18" aria-hidden="true" />
      <span>{{ ui.errorMessage }}</span>
    </div>
    <div
      v-if="ui.successMessage"
      class="absolute bottom-4 right-4 z-50 flex min-h-11 max-w-xl items-center gap-3 rounded border border-secondary/30 bg-secondary/10 px-4 text-sm text-secondary shadow-xl"
    >
      <CheckCircle2 :size="18" aria-hidden="true" />
      <span>{{ ui.successMessage }}</span>
    </div>

    <DashboardView v-if="ui.activeView === 'dashboard'" />
    <LibraryView v-else-if="ui.activeView === 'library'" />
    <EventImportsView v-else-if="ui.activeView === 'events'" />
    <DownloadMatchCenterView v-else-if="ui.activeView === 'downloadCenter'" />
    <SettingsView v-else />
  </AppShell>
</template>
