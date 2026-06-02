<script setup lang="ts">
import { onMounted } from "vue";
import AppShell from "./components/AppShell.vue";
import ToastCenter from "./components/ToastCenter.vue";
import DashboardView from "./views/DashboardView.vue";
import DoctorView from "./views/DoctorView.vue";
import DownloadMatchCenterView from "./views/DownloadMatchCenterView.vue";
import DuplicatesView from "./views/DuplicatesView.vue";
import EventsView from "./views/EventsView.vue";
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
  <AppShell>
    <ToastCenter />

    <DashboardView v-if="ui.activeView === 'dashboard'" />
    <LibraryView v-else-if="ui.activeView === 'library'" />
    <EventsView v-else-if="ui.activeView === 'events'" />
    <DownloadMatchCenterView v-else-if="ui.activeView === 'downloadCenter'" />
    <DuplicatesView v-else-if="ui.activeView === 'duplicates'" />
    <DoctorView v-else-if="ui.activeView === 'doctor'" />
    <SettingsView v-else />
  </AppShell>
</template>
