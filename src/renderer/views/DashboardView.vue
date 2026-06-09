<script setup lang="ts">
import {
  AlertTriangle,
  Database,
  Download,
  Library,
  ListMusic,
  RefreshCw,
  Tags,
  UploadCloud
} from "@lucide/vue";
import { computed, watch } from "vue";
import MetricCard from "../components/MetricCard.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { useEventsStore } from "../stores/events";
import { useLibraryStore } from "../stores/library";
import { useSystemStore } from "../stores/system";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
const system = useSystemStore();
const events = useEventsStore();
const library = useLibraryStore();

// Load the collection stats once the API client is ready (it may be initialised
// after this view mounts).
watch(
  () => system.api,
  (api) => {
    if (api) system.refreshCollectionStats();
  },
  { immediate: true }
);

// Aggregate the per-source review counters across all followed playlists.
const lib = computed(() => {
  const acc = { total: 0, imported: 0, toDownload: 0, ready: 0, conflict: 0 };
  for (const s of library.sources) {
    acc.total += s.trackCount;
    acc.imported += s.importedTrackCount;
    acc.toDownload += s.newTrackCount;
    acc.ready += s.readyTrackCount;
    acc.conflict += s.conflictTrackCount;
  }
  return acc;
});
const coverage = computed(() =>
  lib.value.total ? Math.round((lib.value.imported / lib.value.total) * 100) : 0
);

const activeDownloads = computed(
  () =>
    events.globalAcquisitionJobs.filter((job) =>
      ["queued", "downloading", "resolved"].includes(job.status)
    ).length
);
const failedDownloads = computed(
  () => events.globalAcquisitionJobs.filter((job) => job.status === "acquisition_failed").length
);
const needsAttention = computed(
  () => lib.value.conflict + failedDownloads.value
);

const stats = computed(() => system.collectionStats);
const taggedPct = computed(() =>
  stats.value && stats.value.total ? Math.round((stats.value.tagged / stats.value.total) * 100) : 0
);

const recentEvents = computed(() => events.summaries.slice(0, 5));
</script>

<template>
  <div class="h-full overflow-y-auto p-6 md:p-8">
    <div class="mx-auto w-full max-w-7xl">
      <div class="mb-8">
        <h2 class="mb-2 text-2xl font-bold text-on-surface md:text-3xl">{{ $t("pageTitle.dashboard") }}</h2>
        <p class="text-sm text-on-surface-variant">
          {{ $t("dashboard.subtitle") }}
        </p>
      </div>

      <!-- Hero metrics: the actionable state of the library -->
      <div class="mb-8 grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          :title="$t('dashboard.metric.librarySynced')"
          :value="`${coverage}%`"
          :detail="$t('dashboard.metric.librarySyncedDetail', { imported: lib.imported, total: lib.total })"
          :icon="Library"
          tone="primary"
        />
        <MetricCard
          :title="$t('dashboard.metric.toDownload')"
          :value="lib.toDownload"
          :detail="$t('dashboard.metric.toDownloadDetail')"
          :icon="Download"
          tone="secondary"
        />
        <MetricCard
          :title="$t('dashboard.metric.readyToImport')"
          :value="lib.ready"
          :detail="$t('dashboard.metric.readyToImportDetail')"
          :icon="UploadCloud"
          tone="secondary"
        />
        <MetricCard
          :title="$t('dashboard.metric.needsAttention')"
          :value="needsAttention"
          :detail="$t('dashboard.metric.needsAttentionDetail')"
          :icon="AlertTriangle"
          :tone="needsAttention > 0 ? 'error' : 'muted'"
        />
      </div>

      <div class="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <!-- Library sync breakdown -->
        <section class="rounded-xl border border-outline-variant bg-surface-container p-6">
          <div class="mb-4 flex items-center justify-between">
            <h3 class="text-lg font-bold text-on-surface">{{ $t("dashboard.librarySync") }}</h3>
            <button
              class="rounded border border-outline bg-surface-container-high px-3 py-1.5 text-xs font-bold text-on-surface transition-colors hover:border-primary"
              type="button"
              @click="ui.navigateTo('library')"
            >
              {{ $t("dashboard.openLibrary") }}
            </button>
          </div>

          <div class="mb-2 flex items-end justify-between">
            <span class="text-sm text-on-surface-variant">{{ $t("dashboard.importedToRekordbox") }}</span>
            <span class="text-sm font-bold text-on-surface">{{ coverage }}%</span>
          </div>
          <div class="h-2.5 w-full overflow-hidden rounded-full bg-surface-container-high">
            <div class="h-full rounded-full bg-primary" :style="{ width: `${coverage}%` }" />
          </div>

          <div class="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <span class="block text-xl font-bold text-secondary">{{ lib.imported }}</span>
              <span class="text-[11px] uppercase tracking-wide text-on-surface-variant">{{ $t("dashboard.imported") }}</span>
            </div>
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <span class="block text-xl font-bold text-on-surface">{{ lib.ready }}</span>
              <span class="text-[11px] uppercase tracking-wide text-on-surface-variant">{{ $t("dashboard.ready") }}</span>
            </div>
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <span class="block text-xl font-bold text-on-surface">{{ lib.toDownload }}</span>
              <span class="text-[11px] uppercase tracking-wide text-on-surface-variant">{{ $t("dashboard.toGet") }}</span>
            </div>
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <span class="block text-xl font-bold" :class="lib.conflict > 0 ? 'text-error' : 'text-on-surface'">{{ lib.conflict }}</span>
              <span class="text-[11px] uppercase tracking-wide text-on-surface-variant">{{ $t("dashboard.conflicts") }}</span>
            </div>
          </div>

          <div class="mt-4 flex items-center gap-4 text-xs text-on-surface-variant">
            <span class="flex items-center gap-1.5">
              <ListMusic :size="13" aria-hidden="true" />
              {{ $t("dashboard.playlistsEvents", { playlists: library.sources.length, events: events.summaries.length }) }}
            </span>
            <span v-if="activeDownloads > 0" class="flex items-center gap-1.5 text-primary">
              <Download :size="13" aria-hidden="true" /> {{ $t("dashboard.downloadingCount", { count: activeDownloads }) }}
            </span>
            <span v-if="failedDownloads > 0" class="flex items-center gap-1.5 text-error">
              <AlertTriangle :size="13" aria-hidden="true" /> {{ $t("dashboard.notOnDeemix", { count: failedDownloads }) }}
            </span>
          </div>
        </section>

        <!-- Collection health -->
        <section class="rounded-xl border border-outline-variant bg-surface-container p-6">
          <h3 class="mb-4 text-lg font-bold text-on-surface">{{ $t("dashboard.collectionHealth") }}</h3>

          <template v-if="stats?.available">
            <div class="mb-2 flex items-end justify-between">
              <span class="text-sm text-on-surface-variant">
                <strong class="text-on-surface">{{ stats.total }}</strong> {{ $t("dashboard.tracksTagged", { pct: taggedPct }) }}
              </span>
            </div>
            <div class="h-2.5 w-full overflow-hidden rounded-full bg-surface-container-high">
              <div class="h-full rounded-full bg-secondary" :style="{ width: `${taggedPct}%` }" />
            </div>

            <div class="mt-5 grid grid-cols-3 gap-3">
              <div class="rounded border border-outline-variant bg-surface-container-high p-3">
                <span class="block text-xl font-bold" :class="stats.untagged > 0 ? 'text-tertiary' : 'text-on-surface'">{{ stats.untagged }}</span>
                <span class="flex items-center gap-1 text-[11px] uppercase tracking-wide text-on-surface-variant">
                  <Tags :size="11" aria-hidden="true" /> {{ $t("dashboard.untagged") }}
                </span>
              </div>
              <div class="rounded border border-outline-variant bg-surface-container-high p-3">
                <span class="block text-xl font-bold text-on-surface">{{ stats.withoutIsrc }}</span>
                <span class="text-[11px] uppercase tracking-wide text-on-surface-variant">{{ $t("dashboard.noIsrc") }}</span>
              </div>
              <div class="rounded border border-outline-variant bg-surface-container-high p-3">
                <span class="block text-xl font-bold text-on-surface">{{ stats.withoutArtist }}</span>
                <span class="text-[11px] uppercase tracking-wide text-on-surface-variant">{{ $t("dashboard.noArtist") }}</span>
              </div>
            </div>
          </template>
          <p v-else-if="stats && !stats.available" class="text-sm text-on-surface-variant">
            {{ $t("dashboard.collectionUnavailable", { reason: stats.reason || $t("dashboard.collectionUnavailableDefault") }) }}
          </p>
          <p v-else class="text-sm text-on-surface-variant">{{ $t("dashboard.readingCollection") }}</p>
        </section>

        <!-- System status -->
        <section class="rounded-xl border border-outline-variant bg-surface-container p-6">
          <h3 class="mb-4 text-lg font-bold text-on-surface">{{ $t("dashboard.systemStatus") }}</h3>
          <div class="space-y-3">
            <div class="flex items-center justify-between rounded border border-outline-variant bg-surface-container-high p-3">
              <div class="flex items-center gap-3">
                <div
                  class="h-2 w-2 rounded-full"
                  :class="system.health?.status === 'ok' ? 'bg-secondary shadow-[0_0_8px_var(--color-secondary)]' : 'bg-tertiary shadow-[0_0_8px_var(--color-tertiary)]'"
                />
                <span class="text-sm font-semibold text-on-surface">{{ $t("dashboard.localApi") }}</span>
              </div>
              <StatusBadge :tone="system.health?.status === 'ok' ? 'ok' : 'warn'">
                {{ system.health?.status ?? $t("shell.starting") }}
              </StatusBadge>
            </div>

            <div class="flex items-center justify-between rounded border border-outline-variant bg-surface-container-high p-3">
              <div class="flex items-center gap-3">
                <Database class="text-primary" :size="18" aria-hidden="true" />
                <span class="text-sm font-semibold text-on-surface">{{ $t("dashboard.rekordboxDatabase") }}</span>
              </div>
              <StatusBadge :tone="system.rekordboxStatus?.mutationAllowed ? 'ok' : 'warn'">
                {{ system.rekordboxStatus?.mutationAllowed ? $t("dashboard.statusReady") : $t("dashboard.statusLocked") }}
              </StatusBadge>
            </div>

            <div class="flex items-center justify-between rounded border border-outline-variant bg-surface-container-high p-3">
              <div class="flex items-center gap-3">
                <RefreshCw class="text-secondary" :size="18" aria-hidden="true" />
                <span class="text-sm font-semibold text-on-surface">{{ $t("dashboard.deemixIntegration") }}</span>
              </div>
              <StatusBadge :tone="system.deemixStatus?.available && system.deemixStatus?.authenticated ? 'ok' : 'warn'">
                {{ system.deemixStatus?.available && system.deemixStatus?.authenticated ? $t("dashboard.statusReady") : $t("dashboard.statusUnavailable") }}
              </StatusBadge>
            </div>
          </div>
        </section>

        <!-- Recent events -->
        <section class="rounded-xl border border-outline-variant bg-surface-container p-6">
          <div class="mb-4 flex items-center justify-between">
            <h3 class="text-lg font-bold text-on-surface">{{ $t("dashboard.recentEvents") }}</h3>
            <button
              class="rounded border border-outline bg-surface-container-high px-3 py-1.5 text-xs font-bold text-on-surface transition-colors hover:border-primary"
              type="button"
              @click="ui.navigateTo('events')"
            >
              {{ $t("dashboard.openEvents") }}
            </button>
          </div>
          <div class="space-y-4">
            <div
              v-for="event in recentEvents"
              :key="event.id"
              class="border-l-2 border-primary py-1 pl-4"
            >
              <p class="text-sm font-semibold text-on-surface">{{ event.eventName }}</p>
              <p class="mt-1 text-xs text-on-surface-variant">
                {{ $t("dashboard.eventReady", { ready: event.readyTracks, total: event.totalTracks, status: event.status }) }}
              </p>
            </div>
            <div v-if="recentEvents.length === 0" class="text-sm text-on-surface-variant">
              {{ $t("dashboard.noEvents") }}
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
