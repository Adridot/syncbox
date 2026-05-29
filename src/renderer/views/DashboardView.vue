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
import MetricCard from "../components/MetricCard.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { useEventsStore } from "../stores/events";
import { useLibraryStore } from "../stores/library";
import { useProposalsStore } from "../stores/proposals";
import { useSpotifyStore } from "../stores/spotify";
import { useSystemStore } from "../stores/system";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
const system = useSystemStore();
const events = useEventsStore();
const library = useLibraryStore();
const spotify = useSpotifyStore();
const proposals = useProposalsStore();

const pendingProposals = computed(
  () => proposals.proposals.filter((p) => p.status === "pending").length
);
const activeDownloads = computed(
  () => events.globalAcquisitionJobs.filter((job) => ["queued", "downloading", "resolved"].includes(job.status)).length
);
const recentEvents = computed(() => events.summaries.slice(0, 4));
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
          :value="library.sources.length"
          detail="Followed Spotify sources"
          :icon="Library"
          tone="primary"
        />
        <MetricCard
          title="Event Imports"
          :value="events.summaries.length"
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
                    system.health?.status === 'ok'
                      ? 'bg-secondary shadow-[0_0_8px_var(--color-secondary)]'
                      : 'bg-tertiary shadow-[0_0_8px_var(--color-tertiary)]'
                  "
                />
                <span class="text-sm font-semibold text-on-surface">Local API</span>
              </div>
              <StatusBadge :tone="system.health?.status === 'ok' ? 'ok' : 'warn'">
                {{ system.health?.status ?? "starting" }}
              </StatusBadge>
            </div>

            <div
              class="flex items-center justify-between rounded border border-outline-variant bg-surface-container-high p-3"
            >
              <div class="flex items-center gap-3">
                <Database class="text-primary" :size="18" aria-hidden="true" />
                <span class="text-sm font-semibold text-on-surface">Rekordbox Database</span>
              </div>
              <StatusBadge :tone="system.rekordboxStatus?.mutationAllowed ? 'ok' : 'warn'">
                {{ system.rekordboxStatus?.mutationAllowed ? "Ready" : "Locked" }}
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
                :tone="system.deemixStatus?.available && system.deemixStatus?.authenticated ? 'ok' : 'warn'"
              >
                {{
                  system.deemixStatus?.available && system.deemixStatus?.authenticated
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
                {{ spotify.playlists.length }} Spotify playlists loaded,
                {{ library.sources.length }} permanent sources configured.
              </p>
            </div>
            <div class="flex flex-wrap gap-3">
              <button
                class="rounded bg-primary px-4 py-2 text-sm font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02]"
                type="button"
                @click="ui.navigateTo('library')"
              >
                Open My Library
              </button>
              <button
                class="rounded border border-outline bg-surface-container-high px-4 py-2 text-sm font-bold text-on-surface transition-colors hover:border-primary"
                type="button"
                @click="ui.navigateTo('downloadCenter')"
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
