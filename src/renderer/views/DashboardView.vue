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
import { useProposalsStore } from "../stores/proposals";
import { useSystemStore } from "../stores/system";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
const system = useSystemStore();
const events = useEventsStore();
const library = useLibraryStore();
const proposals = useProposalsStore();

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
const pendingProposals = computed(
  () => proposals.proposals.filter((p) => p.status === "pending").length
);
const needsAttention = computed(
  () => lib.value.conflict + failedDownloads.value + pendingProposals.value
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
        <h2 class="mb-2 text-2xl font-bold text-on-surface md:text-3xl">Dashboard</h2>
        <p class="text-sm text-on-surface-variant">
          Sync health of your followed playlists and Rekordbox collection.
        </p>
      </div>

      <!-- Hero metrics: the actionable state of the library -->
      <div class="mb-8 grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          title="Library synced"
          :value="`${coverage}%`"
          :detail="`${lib.imported} of ${lib.total} playlist tracks in Rekordbox`"
          :icon="Library"
          tone="primary"
        />
        <MetricCard
          title="To download"
          :value="lib.toDownload"
          detail="New Spotify tracks to acquire"
          :icon="Download"
          tone="secondary"
        />
        <MetricCard
          title="Ready to import"
          :value="lib.ready"
          detail="Downloaded — waiting for Rekordbox"
          :icon="UploadCloud"
          tone="secondary"
        />
        <MetricCard
          title="Needs attention"
          :value="needsAttention"
          detail="Conflicts, failed downloads & proposals"
          :icon="AlertTriangle"
          :tone="needsAttention > 0 ? 'error' : 'muted'"
        />
      </div>

      <div class="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <!-- Library sync breakdown -->
        <section class="rounded-xl border border-outline-variant bg-surface-container p-6">
          <div class="mb-4 flex items-center justify-between">
            <h3 class="text-lg font-bold text-on-surface">Library sync</h3>
            <button
              class="rounded border border-outline bg-surface-container-high px-3 py-1.5 text-xs font-bold text-on-surface transition-colors hover:border-primary"
              type="button"
              @click="ui.navigateTo('library')"
            >
              Open Library
            </button>
          </div>

          <div class="mb-2 flex items-end justify-between">
            <span class="text-sm text-on-surface-variant">Imported to Rekordbox</span>
            <span class="text-sm font-bold text-on-surface">{{ coverage }}%</span>
          </div>
          <div class="h-2.5 w-full overflow-hidden rounded-full bg-surface-container-high">
            <div class="h-full rounded-full bg-primary" :style="{ width: `${coverage}%` }" />
          </div>

          <div class="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <span class="block text-xl font-bold text-secondary">{{ lib.imported }}</span>
              <span class="text-[11px] uppercase tracking-wide text-on-surface-variant">Imported</span>
            </div>
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <span class="block text-xl font-bold text-on-surface">{{ lib.ready }}</span>
              <span class="text-[11px] uppercase tracking-wide text-on-surface-variant">Ready</span>
            </div>
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <span class="block text-xl font-bold text-on-surface">{{ lib.toDownload }}</span>
              <span class="text-[11px] uppercase tracking-wide text-on-surface-variant">To get</span>
            </div>
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <span class="block text-xl font-bold" :class="lib.conflict > 0 ? 'text-error' : 'text-on-surface'">{{ lib.conflict }}</span>
              <span class="text-[11px] uppercase tracking-wide text-on-surface-variant">Conflicts</span>
            </div>
          </div>

          <div class="mt-4 flex items-center gap-4 text-xs text-on-surface-variant">
            <span class="flex items-center gap-1.5">
              <ListMusic :size="13" aria-hidden="true" />
              {{ library.sources.length }} playlists · {{ events.summaries.length }} events
            </span>
            <span v-if="activeDownloads > 0" class="flex items-center gap-1.5 text-primary">
              <Download :size="13" aria-hidden="true" /> {{ activeDownloads }} downloading
            </span>
            <span v-if="failedDownloads > 0" class="flex items-center gap-1.5 text-error">
              <AlertTriangle :size="13" aria-hidden="true" /> {{ failedDownloads }} not on Deemix
            </span>
          </div>
        </section>

        <!-- Collection health -->
        <section class="rounded-xl border border-outline-variant bg-surface-container p-6">
          <h3 class="mb-4 text-lg font-bold text-on-surface">Collection health</h3>

          <template v-if="stats?.available">
            <div class="mb-2 flex items-end justify-between">
              <span class="text-sm text-on-surface-variant">
                <strong class="text-on-surface">{{ stats.total }}</strong> tracks in Rekordbox · {{ taggedPct }}% tagged
              </span>
            </div>
            <div class="h-2.5 w-full overflow-hidden rounded-full bg-surface-container-high">
              <div class="h-full rounded-full bg-secondary" :style="{ width: `${taggedPct}%` }" />
            </div>

            <div class="mt-5 grid grid-cols-3 gap-3">
              <div class="rounded border border-outline-variant bg-surface-container-high p-3">
                <span class="block text-xl font-bold" :class="stats.untagged > 0 ? 'text-tertiary' : 'text-on-surface'">{{ stats.untagged }}</span>
                <span class="flex items-center gap-1 text-[11px] uppercase tracking-wide text-on-surface-variant">
                  <Tags :size="11" aria-hidden="true" /> Untagged
                </span>
              </div>
              <div class="rounded border border-outline-variant bg-surface-container-high p-3">
                <span class="block text-xl font-bold text-on-surface">{{ stats.withoutIsrc }}</span>
                <span class="text-[11px] uppercase tracking-wide text-on-surface-variant">No ISRC</span>
              </div>
              <div class="rounded border border-outline-variant bg-surface-container-high p-3">
                <span class="block text-xl font-bold text-on-surface">{{ stats.withoutArtist }}</span>
                <span class="text-[11px] uppercase tracking-wide text-on-surface-variant">No artist</span>
              </div>
            </div>
          </template>
          <p v-else-if="stats && !stats.available" class="text-sm text-on-surface-variant">
            Collection unavailable — {{ stats.reason || "could not read the Rekordbox database." }}
          </p>
          <p v-else class="text-sm text-on-surface-variant">Reading collection…</p>
        </section>

        <!-- System status -->
        <section class="rounded-xl border border-outline-variant bg-surface-container p-6">
          <h3 class="mb-4 text-lg font-bold text-on-surface">System Status</h3>
          <div class="space-y-3">
            <div class="flex items-center justify-between rounded border border-outline-variant bg-surface-container-high p-3">
              <div class="flex items-center gap-3">
                <div
                  class="h-2 w-2 rounded-full"
                  :class="system.health?.status === 'ok' ? 'bg-secondary shadow-[0_0_8px_var(--color-secondary)]' : 'bg-tertiary shadow-[0_0_8px_var(--color-tertiary)]'"
                />
                <span class="text-sm font-semibold text-on-surface">Local API</span>
              </div>
              <StatusBadge :tone="system.health?.status === 'ok' ? 'ok' : 'warn'">
                {{ system.health?.status ?? "starting" }}
              </StatusBadge>
            </div>

            <div class="flex items-center justify-between rounded border border-outline-variant bg-surface-container-high p-3">
              <div class="flex items-center gap-3">
                <Database class="text-primary" :size="18" aria-hidden="true" />
                <span class="text-sm font-semibold text-on-surface">Rekordbox Database</span>
              </div>
              <StatusBadge :tone="system.rekordboxStatus?.mutationAllowed ? 'ok' : 'warn'">
                {{ system.rekordboxStatus?.mutationAllowed ? "Ready" : "Locked" }}
              </StatusBadge>
            </div>

            <div class="flex items-center justify-between rounded border border-outline-variant bg-surface-container-high p-3">
              <div class="flex items-center gap-3">
                <RefreshCw class="text-secondary" :size="18" aria-hidden="true" />
                <span class="text-sm font-semibold text-on-surface">Deemix Integration</span>
              </div>
              <StatusBadge :tone="system.deemixStatus?.available && system.deemixStatus?.authenticated ? 'ok' : 'warn'">
                {{ system.deemixStatus?.available && system.deemixStatus?.authenticated ? "Ready" : "Unavailable" }}
              </StatusBadge>
            </div>
          </div>
        </section>

        <!-- Recent events -->
        <section class="rounded-xl border border-outline-variant bg-surface-container p-6">
          <div class="mb-4 flex items-center justify-between">
            <h3 class="text-lg font-bold text-on-surface">Recent Events</h3>
            <button
              class="rounded border border-outline bg-surface-container-high px-3 py-1.5 text-xs font-bold text-on-surface transition-colors hover:border-primary"
              type="button"
              @click="ui.navigateTo('events')"
            >
              Open Events
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
                {{ event.readyTracks }}/{{ event.totalTracks }} ready · {{ event.status }}
              </p>
            </div>
            <div v-if="recentEvents.length === 0" class="text-sm text-on-surface-variant">
              No events yet.
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
