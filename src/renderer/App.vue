<script setup lang="ts">
import { defineAsyncComponent, onMounted } from "vue";
import AppShell from "./components/AppShell.vue";
import ToastCenter from "./components/ToastCenter.vue";
import DashboardView from "./views/DashboardView.vue";
// Secondary views are code-split: each lands in its own chunk and is fetched
// only when first navigated to, keeping the initial renderer bundle lean.
const DoctorView = defineAsyncComponent(() => import("./views/DoctorView.vue"));
const DownloadMatchCenterView = defineAsyncComponent(
  () => import("./views/DownloadMatchCenterView.vue")
);
const DuplicatesView = defineAsyncComponent(() => import("./views/DuplicatesView.vue"));
const EventsView = defineAsyncComponent(() => import("./views/EventsView.vue"));
const LibraryView = defineAsyncComponent(() => import("./views/LibraryView.vue"));
const MissingFilesView = defineAsyncComponent(() => import("./views/MissingFilesView.vue"));
const UntaggedView = defineAsyncComponent(() => import("./views/UntaggedView.vue"));
const SettingsView = defineAsyncComponent(() => import("./views/SettingsView.vue"));
import { useRefreshManager } from "./composables/useRefreshManager";
import { useEventsStore } from "./stores/events";
import { useLibraryStore } from "./stores/library";
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

useRefreshManager();

onMounted(async () => {
  await system.init();
  await Promise.all([
    system.refreshStatus(),
    settings.load(),
    library.refreshTagRules(),
    library.refreshSources(),
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
    <MissingFilesView v-else-if="ui.activeView === 'missing'" />
    <UntaggedView v-else-if="ui.activeView === 'untagged'" />
    <DoctorView v-else-if="ui.activeView === 'doctor'" />
    <SettingsView v-else />
  </AppShell>
</template>
