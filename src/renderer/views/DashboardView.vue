<script setup lang="ts">
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Download,
  Library,
  Music,
  RefreshCw
} from "@lucide/vue";
import { computed } from "vue";
import type {
  DeemixStatus,
  EventSummary,
  GlobalAcquisitionJob,
  HealthResponse,
  LibrarySource,
  RekordboxStatus,
  SpotifyPlaylistSummary,
  SyncProposal
} from "../lib/api";
import type { ViewKey } from "../types/ui";
import MetricCard from "../components/MetricCard.vue";
import StatusBadge from "../components/StatusBadge.vue";

const props = defineProps<{
  health: HealthResponse | null;
  rekordboxStatus: RekordboxStatus | null;
  deemixStatus: DeemixStatus | null;
  eventSummaries: EventSummary[];
  proposals: SyncProposal[];
  librarySources: LibrarySource[];
  spotifyPlaylists: SpotifyPlaylistSummary[];
  globalAcquisitionJobs: GlobalAcquisitionJob[];
}>();

defineEmits<{
  changeView: [view: ViewKey];
}>();

const pendingProposals = computed(
  () => props.proposals.filter((proposal) => proposal.status === "pending").length
);
const activeDownloads = computed(
  () =>
    props.globalAcquisitionJobs.filter((job) =>
      ["queued", "downloading", "resolved"].includes(job.status)
    ).length
);
const recentEvents = computed(() => props.eventSummaries.slice(0, 4));
</script>

<template>
  <div class="h-full overflow-y-auto p-6 md:p-8">
    <div class="mx-auto w-full max-w-7xl">
      <div class="mb-8">
        <h2 class="mb-2 text-2xl font-bold text-on-surface md:text-3xl">Dashboard</h2>
        <p class="text-sm text-on-surface-variant">
          Overview of Rekordbox sync status, Spotify activity, and downloads.
        </p>
      </div>

      <div class="mb-8 grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          title="Permanent Playlists"
          :value="librarySources.length"
          detail="Followed Spotify sources"
          :icon="Library"
          tone="primary"
        />
        <MetricCard
          title="Event Imports"
          :value="eventSummaries.length"
          detail="Temporary playlists"
          :icon="Music"
          tone="secondary"
        />
        <MetricCard
          title="Pending Actions"
          :value="pendingProposals"
          detail="Sync proposals"
          :icon="AlertTriangle"
          tone="tertiary"
        />
        <MetricCard
          title="Download Queue"
          :value="activeDownloads"
          detail="Active Deemix jobs"
          :icon="Download"
          tone="muted"
        />
      </div>

      <div class="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <section class="rounded-xl border border-outline-variant bg-surface-container p-6">
          <h3 class="mb-4 text-lg font-bold text-on-surface">System Status</h3>
          <div class="space-y-3">
            <div
              class="flex items-center justify-between rounded border border-outline-variant bg-surface-container-high p-3"
            >
              <div class="flex items-center gap-3">
                <div
                  class="h-2 w-2 rounded-full"
                  :class="
                    health?.status === 'ok'
                      ? 'bg-secondary shadow-[0_0_8px_var(--color-secondary)]'
                      : 'bg-tertiary shadow-[0_0_8px_var(--color-tertiary)]'
                  "
                />
                <span class="text-sm font-semibold text-on-surface">Local API</span>
              </div>
              <StatusBadge :tone="health?.status === 'ok' ? 'ok' : 'warn'">
                {{ health?.status ?? "starting" }}
              </StatusBadge>
            </div>

            <div
              class="flex items-center justify-between rounded border border-outline-variant bg-surface-container-high p-3"
            >
              <div class="flex items-center gap-3">
                <Database class="text-primary" :size="18" aria-hidden="true" />
                <span class="text-sm font-semibold text-on-surface">Rekordbox Database</span>
              </div>
              <StatusBadge :tone="rekordboxStatus?.mutationAllowed ? 'ok' : 'warn'">
                {{ rekordboxStatus?.mutationAllowed ? "Ready" : "Locked" }}
              </StatusBadge>
            </div>

            <div
              class="flex items-center justify-between rounded border border-outline-variant bg-surface-container-high p-3"
            >
              <div class="flex items-center gap-3">
                <RefreshCw class="text-secondary" :size="18" aria-hidden="true" />
                <span class="text-sm font-semibold text-on-surface">Deemix Integration</span>
              </div>
              <StatusBadge
                :tone="deemixStatus?.available && deemixStatus?.authenticated ? 'ok' : 'warn'"
              >
                {{
                  deemixStatus?.available && deemixStatus?.authenticated
                    ? "Ready"
                    : "Unavailable"
                }}
              </StatusBadge>
            </div>
          </div>
        </section>

        <section class="rounded-xl border border-outline-variant bg-surface-container p-6">
          <div class="mb-4 flex items-center justify-between">
            <h3 class="text-lg font-bold text-on-surface">Recent Event Imports</h3>
            <button
              class="rounded border border-outline bg-surface-container-high px-3 py-1.5 text-xs font-bold text-on-surface transition-colors hover:border-primary"
              type="button"
              @click="$emit('changeView', 'events')"
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
                {{ event.readyTracks }}/{{ event.totalTracks }} ready - {{ event.status }}
              </p>
            </div>
            <div v-if="recentEvents.length === 0" class="text-sm text-on-surface-variant">
              No event imports.
            </div>
          </div>
        </section>

        <section class="rounded-xl border border-outline-variant bg-surface-container p-6 xl:col-span-2">
          <div class="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h3 class="text-lg font-bold text-on-surface">Library Health</h3>
              <p class="mt-1 text-sm text-on-surface-variant">
                {{ spotifyPlaylists.length }} Spotify playlists loaded,
                {{ librarySources.length }} permanent sources configured.
              </p>
            </div>
            <div class="flex flex-wrap gap-3">
              <button
                class="rounded bg-primary px-4 py-2 text-sm font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02]"
                type="button"
                @click="$emit('changeView', 'library')"
              >
                Open My Library
              </button>
              <button
                class="rounded border border-outline bg-surface-container-high px-4 py-2 text-sm font-bold text-on-surface transition-colors hover:border-primary"
                type="button"
                @click="$emit('changeView', 'downloadCenter')"
              >
                Download Center
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
