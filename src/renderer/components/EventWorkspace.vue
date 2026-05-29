<script setup lang="ts">
import { FileAudio, FolderOpen, RefreshCw, ShieldCheck, Trash2 } from "@lucide/vue";
import DeezerSearchPanel from "./DeezerSearchPanel.vue";
import StatusBadge from "./StatusBadge.vue";
import TrackReviewTable from "./TrackReviewTable.vue";
import { useEventsStore } from "../stores/events";
import { useSystemStore } from "../stores/system";
import { useUiStore } from "../stores/ui";

// Shared "active event" workspace used by both the Event Imports and Manual
// Event tabs. It reads the events store directly so the two tabs operate on the
// same active event.
const ui = useUiStore();
const system = useSystemStore();
const events = useEventsStore();

const emptyMessage = "Select or create an event to review tracks, files, and downloads.";

function eventStatusTone(event: {
  status: string;
  readyTracks: number;
  totalTracks: number;
}): "ok" | "warn" | "active" {
  if (event.status === "applied") return "ok";
  if (event.readyTracks < event.totalTracks) return "warn";
  return "active";
}

async function openDesktopPath(path: string): Promise<void> {
  if (!window.desktop) {
    ui.setMessage("success", `Open this path in Finder: ${path}`);
    return;
  }
  try {
    await window.desktop.openPath(path);
  } catch (error) {
    ui.setMessage("error", error instanceof Error ? error.message : String(error));
  }
}
</script>

<template>
  <div class="flex min-w-0 flex-1 flex-col overflow-hidden">
    <div v-if="events.activeEvent" class="flex h-full flex-col">
      <!-- Event header -->
      <div class="border-b border-outline-variant bg-surface p-4">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div class="flex items-center gap-3">
              <h3 class="text-lg font-bold text-on-surface">{{ events.activeEvent.eventName }}</h3>
              <StatusBadge :tone="eventStatusTone({
                status: events.activeEvent.status,
                readyTracks: events.activeEvent.readyTracks,
                totalTracks: events.activeEvent.totalTracks
              })">
                {{ events.activeEvent.status }}
              </StatusBadge>
            </div>
            <p class="text-sm text-on-surface-variant">{{ events.activeEvent.spotifyPlaylistName }}</p>
          </div>
          <div class="flex flex-wrap gap-2">
            <button
              class="inline-flex items-center gap-2 rounded border border-outline bg-surface-container-high px-3 py-1.5 text-xs font-bold text-on-surface transition-colors hover:border-primary"
              type="button"
              @click="openDesktopPath(events.activeEvent.audioDir)"
            >
              <FolderOpen :size="14" aria-hidden="true" />
              Audio
            </button>
            <button
              class="inline-flex items-center gap-2 rounded border border-outline bg-surface-container-high px-3 py-1.5 text-xs font-bold text-on-surface transition-colors hover:border-primary disabled:opacity-60"
              type="button"
              :disabled="ui.loading"
              @click="events.refreshEventFolder()"
            >
              <RefreshCw :size="14" aria-hidden="true" />
              Refresh
            </button>
            <button
              class="inline-flex items-center gap-2 rounded bg-primary px-3 py-1.5 text-xs font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02] disabled:opacity-60"
              type="button"
              :disabled="ui.loading || !events.readyToApply || !system.rekordboxStatus?.mutationAllowed"
              @click="events.applyActiveEvent()"
            >
              <ShieldCheck :size="14" aria-hidden="true" />
              Apply Ready Tracks
            </button>
            <button
              class="inline-flex items-center gap-2 rounded border border-error/60 bg-error/10 px-3 py-1.5 text-xs font-bold text-error transition-colors hover:border-error disabled:opacity-60"
              type="button"
              :disabled="ui.loading"
              @click="events.deleteActiveEvent()"
            >
              <Trash2 :size="14" aria-hidden="true" />
              Delete
            </button>
          </div>
        </div>

        <!-- Metrics -->
        <div class="mt-3 grid grid-cols-5 gap-2">
          <div v-for="[label, value] in [
            ['matched', events.activeEvent.matchedTracks],
            ['ready', events.activeEvent.readyTracks],
            ['applied', events.activeEvent.appliedTracks],
            ['missing', events.activeEvent.missingTracks],
            ['ambiguous', events.activeEvent.ambiguousTracks],
          ]" :key="label" class="rounded border border-outline-variant bg-surface-container-high p-2 text-center">
            <strong class="block text-xl text-on-surface">{{ value }}</strong>
            <span class="text-[10px] uppercase tracking-wide text-on-surface-variant">{{ label }}</span>
          </div>
        </div>
      </div>

      <!-- Track table with filters/pagination (Actionable/Ready/All) -->
      <div class="min-h-0 flex-1 overflow-auto p-4">
        <TrackReviewTable
          :tracks="events.activeEvent.tracks"
          :acquisition-jobs="events.acquisitionJobs"
          :staging-files="events.activeEvent.stagingFiles"
          @accept-suggested-match="events.acceptSuggestedMatch($event)"
          @assign-staging-file="(track, filePath) => events.assignStagingFile(track, filePath)"
          @search-deezer="events.openDeezerSearch($event)"
          @ignore="events.ignoreTrack($event)"
          @unignore="events.unignoreTrack($event)"
        />

        <div v-if="events.activeEvent.stagingFiles.length > 0" class="mt-4">
          <div class="mb-2 flex items-center gap-2">
            <FileAudio class="text-secondary" :size="15" aria-hidden="true" />
            <span class="text-sm font-bold text-on-surface">Staged Files</span>
          </div>
          <div class="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            <div
              v-for="file in events.activeEvent.stagingFiles"
              :key="file.filePath"
              class="rounded border border-outline-variant bg-surface-container-high p-3"
            >
              <strong class="block truncate text-xs text-on-surface">{{ file.title }}</strong>
              <span class="text-[11px] text-on-surface-variant">
                {{ file.artist || "Unknown artist" }} — {{ file.status }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="flex h-full items-center justify-center text-sm text-on-surface-variant">
      {{ emptyMessage }}
    </div>
  </div>

  <!-- Deezer Search Panel (shared) -->
  <DeezerSearchPanel
    v-if="events.deezerSearchTrack"
    :track="events.deezerSearchTrack"
    :query="events.deezerSearchQuery"
    :loading="events.deezerSearchLoading"
    :results="events.deezerSearchResults"
    @update:query="events.deezerSearchQuery = $event"
    @search="events.runDeezerSearch()"
    @queue="events.queueDeezerTrack($event)"
    @close="events.closeDeezerSearch()"
  />
</template>
