<script setup lang="ts">
import {
  AreaChart,
  FileAudio,
  FolderOpen,
  Link2,
  RefreshCw,
  ShieldCheck,
  Trash2
} from "@lucide/vue";
import EventCard from "../components/EventCard.vue";
import StatusBadge from "../components/StatusBadge.vue";
import TrackReviewTable from "../components/TrackReviewTable.vue";
import { useEventsStore } from "../stores/events";
import { useSystemStore } from "../stores/system";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
const system = useSystemStore();
const events = useEventsStore();

const reviewFilters = ["all", "matched", "ready", "applied", "missing", "ambiguous", "ignored"];

function eventStatusTone(event: { status: string; readyTracks: number; totalTracks: number }): "ok" | "warn" | "active" {
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
  <div class="flex h-full overflow-hidden">
    <!-- Left sidebar: event list -->
    <aside class="flex h-full w-72 shrink-0 flex-col border-r border-outline-variant bg-background">
      <div class="border-b border-outline-variant p-4">
        <h2 class="mb-3 text-sm font-bold uppercase tracking-wider text-on-surface-variant">
          Event Imports
        </h2>
        <form class="flex flex-col gap-2" @submit.prevent="events.analyzeImport()">
          <div class="relative">
            <Link2
              class="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant"
              :size="14"
              aria-hidden="true"
            />
            <input
              class="w-full rounded border border-outline bg-surface-container py-2 pl-8 pr-3 text-xs text-on-surface transition-colors focus:border-primary focus:outline-none"
              v-model="events.importForm.playlistUrl"
              type="url"
              placeholder="Spotify playlist URL"
              required
            />
          </div>
          <input
            class="rounded border border-outline bg-surface-container px-3 py-2 text-xs text-on-surface transition-colors focus:border-primary focus:outline-none"
            v-model="events.importForm.eventName"
            type="text"
            placeholder="Event name"
            required
          />
          <button
            class="inline-flex items-center justify-center gap-2 rounded bg-primary px-4 py-2 text-xs font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-60"
            type="submit"
            :disabled="ui.loading"
          >
            <AreaChart :size="15" aria-hidden="true" />
            Analyze Import
          </button>
        </form>
      </div>

      <div class="flex-1 overflow-y-auto p-3">
        <div class="mb-2 flex items-center justify-between px-1">
          <span class="text-xs font-bold text-on-surface-variant">Temporary Playlists</span>
          <StatusBadge tone="active">{{ events.summaries.length }}</StatusBadge>
        </div>
        <div class="flex flex-col gap-2">
          <EventCard
            v-for="event in events.summaries"
            :key="event.id"
            :event="event"
            :active="events.activeEvent?.id === event.id"
            @open="events.openEvent(event)"
          />
          <div
            v-if="events.summaries.length === 0"
            class="rounded-lg border border-dashed border-outline bg-surface-container p-4 text-xs text-on-surface-variant"
          >
            No event imports yet.
          </div>
        </div>
      </div>

      <!-- Live Import section at bottom -->
      <div class="border-t border-outline-variant p-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <FileAudio class="text-secondary" :size="15" aria-hidden="true" />
            <span class="text-xs font-bold text-on-surface">Live Import (M3U8)</span>
          </div>
          <button
            class="rounded border border-outline bg-surface px-2.5 py-1 text-[11px] font-bold text-on-surface transition-colors hover:border-primary"
            type="button"
            @click="events.createLiveImportPackage()"
          >
            Prepare
          </button>
        </div>
        <div v-if="events.liveImportPackage" class="mt-2 space-y-2 text-[11px] text-on-surface-variant">
          <p class="break-all">{{ events.liveImportPackage.audioDir }}</p>
          <div class="flex gap-2">
            <button
              class="rounded border border-outline bg-surface-container px-2 py-1 font-bold text-on-surface transition-colors hover:border-primary"
              type="button"
              @click="openDesktopPath(events.liveImportPackage.audioDir)"
            >
              Open Audio
            </button>
            <button
              class="rounded border border-outline bg-surface-container px-2 py-1 font-bold text-on-surface transition-colors hover:border-primary"
              type="button"
              @click="openDesktopPath(events.liveImportPackage.playlistPath)"
            >
              Open M3U8
            </button>
          </div>
        </div>
      </div>
    </aside>

    <!-- Main content: active event -->
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
                class="inline-flex items-center gap-2 rounded border border-outline bg-surface-container-high px-3 py-1.5 text-xs font-bold text-on-surface transition-colors hover:border-primary disabled:opacity-60"
                type="button"
                :disabled="ui.loading"
                @click="events.downloadMissingTracks()"
              >
                <FileAudio :size="14" aria-hidden="true" />
                Download
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

        <!-- Filter tabs -->
        <div class="flex flex-wrap gap-1 border-b border-outline-variant bg-surface px-4 py-2">
          <button
            v-for="filter in reviewFilters"
            :key="filter"
            class="rounded border px-2.5 py-1 text-[11px] font-bold capitalize transition-colors"
            :class="
              events.reviewFilter === filter
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-outline bg-surface-container-high text-on-surface-variant hover:text-on-surface'
            "
            type="button"
            @click="events.reviewFilter = filter"
          >
            {{ filter }}
          </button>
        </div>

        <!-- Track table — takes remaining height -->
        <div class="min-h-0 flex-1 overflow-auto p-4">
          <TrackReviewTable
            :active-event="events.activeEvent"
            :tracks="events.filteredTracks"
            :acquisition-jobs="events.acquisitionJobs"
            @accept-suggested-match="events.acceptSuggestedMatch($event)"
            @assign-staging-file="(track, filePath) => events.assignStagingFile(track, filePath)"
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

      <div
        v-else
        class="flex h-full items-center justify-center text-sm text-on-surface-variant"
      >
        Select an event import to review tracks, files, and downloads.
      </div>
    </div>
  </div>
</template>
