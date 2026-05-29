<script setup lang="ts">
import {
  AreaChart,
  Cpu,
  FileAudio,
  FolderOpen,
  Link2,
  RefreshCw,
  ShieldCheck,
  Trash2
} from "@lucide/vue";
import EventCard from "../components/EventCard.vue";
import MetricCard from "../components/MetricCard.vue";
import PlaylistCard from "../components/PlaylistCard.vue";
import StatusBadge from "../components/StatusBadge.vue";
import TrackReviewTable from "../components/TrackReviewTable.vue";
import { useEventsStore } from "../stores/events";
import { useSpotifyStore } from "../stores/spotify";
import { useSystemStore } from "../stores/system";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
const system = useSystemStore();
const events = useEventsStore();
const spotify = useSpotifyStore();

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
  <div class="h-full overflow-y-auto p-6 md:p-8">
    <div class="mx-auto w-full max-w-[1600px]">
      <div class="mb-8">
        <h2 class="mb-1 text-2xl font-bold text-on-surface md:text-3xl">Event Imports</h2>
        <p class="text-sm text-on-surface-variant">
          Temporary playlists for client requests and live events.
        </p>
      </div>

      <div class="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section
          class="lg:col-span-2 rounded-xl border border-outline-variant bg-surface-container-high p-6"
        >
          <div class="mb-6">
            <h3 class="mb-2 flex items-center text-lg font-bold text-on-surface">
              <Link2 class="mr-2 text-primary" :size="20" aria-hidden="true" />
              New Event Import
            </h3>
            <p class="text-sm text-on-surface-variant">
              Paste or select a Spotify playlist, then analyze the event.
            </p>
          </div>
          <form class="grid gap-3 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_auto]" @submit.prevent="events.analyzeImport()">
            <div class="relative">
              <Link2
                class="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant"
                :size="16"
                aria-hidden="true"
              />
              <input
                class="w-full rounded border border-outline bg-surface-container py-2 pl-9 pr-4 text-sm text-on-surface transition-colors focus:border-primary focus:outline-none"
                v-model="events.importForm.playlistUrl"
                type="url"
                placeholder="https://open.spotify.com/playlist/..."
                required
              />
            </div>
            <input
              class="rounded border border-outline bg-surface-container px-4 py-2 text-sm text-on-surface transition-colors focus:border-primary focus:outline-none"
              v-model="events.importForm.eventName"
              type="text"
              placeholder="Event name"
              required
            />
            <button
              class="inline-flex items-center justify-center gap-2 rounded bg-primary px-6 py-2 text-sm font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-60"
              type="submit"
              :disabled="ui.loading"
            >
              <AreaChart :size="18" aria-hidden="true" />
              Analyze Import
            </button>
          </form>
        </section>

        <MetricCard
          title="Active Events"
          :value="events.summaries.length"
          :detail="`${events.summaries.reduce((total, event) => total + event.totalTracks, 0)} tracks tracked`"
          :icon="Cpu"
          tone="primary"
        />
      </div>

      <section class="mb-10" v-if="spotify.playlists.length > 0">
        <div class="mb-4 flex items-center justify-between">
          <h3 class="text-lg font-bold text-on-surface">Select a Spotify Playlist</h3>
          <span class="text-xs text-on-surface-variant">
            {{ spotify.playlists.length }} loaded
          </span>
        </div>
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          <PlaylistCard
            v-for="playlist in spotify.playlists.filter((p) => !ui.searchQuery || p.name.toLowerCase().includes(ui.searchQuery.toLowerCase()))"
            :key="playlist.id"
            :playlist="playlist"
            @select="events.selectSpotifyPlaylist(playlist)"
          />
        </div>
      </section>

      <div class="grid grid-cols-1 gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
        <section>
          <div class="mb-4 flex items-center justify-between">
            <h3 class="text-lg font-bold text-on-surface">Temporary Playlists</h3>
            <StatusBadge tone="active">{{ events.summaries.length }} events</StatusBadge>
          </div>
          <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-1">
            <EventCard
              v-for="event in events.summaries"
              :key="event.id"
              :event="event"
              :active="events.activeEvent?.id === event.id"
              @open="events.openEvent(event)"
            />
            <div
              v-if="events.summaries.length === 0"
              class="rounded-lg border border-dashed border-outline bg-surface-container p-6 text-sm text-on-surface-variant"
            >
              No event imports.
            </div>
          </div>

          <section class="mt-6 rounded-xl border border-outline-variant bg-surface-container-high p-5">
            <div class="mb-4 flex items-center justify-between">
              <div class="flex items-center gap-2">
                <FileAudio class="text-secondary" :size="18" aria-hidden="true" />
                <h3 class="font-bold text-on-surface">Live Rekordbox Import</h3>
              </div>
              <button
                class="rounded border border-outline bg-surface px-3 py-1.5 text-xs font-bold text-on-surface transition-colors hover:border-primary"
                type="button"
                @click="events.createLiveImportPackage()"
              >
                Prepare
              </button>
            </div>
            <div v-if="events.liveImportPackage" class="space-y-3 text-xs text-on-surface-variant">
              <p class="break-all">{{ events.liveImportPackage.audioDir }}</p>
              <div class="flex flex-wrap gap-2">
                <button
                  class="rounded border border-outline bg-surface-container px-3 py-1.5 font-bold text-on-surface transition-colors hover:border-primary"
                  type="button"
                  @click="openDesktopPath(events.liveImportPackage.audioDir)"
                >
                  Open Audio Folder
                </button>
                <button
                  class="rounded border border-outline bg-surface-container px-3 py-1.5 font-bold text-on-surface transition-colors hover:border-primary"
                  type="button"
                  @click="openDesktopPath(events.liveImportPackage.playlistPath)"
                >
                  Open M3U8
                </button>
              </div>
            </div>
            <p v-else class="text-xs text-on-surface-variant">
              Prepare an M3U8 package for tracks already staged in the event folder.
            </p>
          </section>
        </section>

        <section
          v-if="events.activeEvent"
          class="min-w-0 rounded-xl border border-outline-variant bg-surface-container p-5 md:p-6"
        >
          <div class="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div class="mb-2 flex items-center gap-3">
                <h3 class="text-xl font-bold text-on-surface">{{ events.activeEvent.eventName }}</h3>
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
                class="inline-flex items-center gap-2 rounded border border-outline bg-surface-container-high px-3 py-2 text-xs font-bold text-on-surface transition-colors hover:border-primary"
                type="button"
                @click="openDesktopPath(events.activeEvent.audioDir)"
              >
                <FolderOpen :size="16" aria-hidden="true" />
                Open Audio
              </button>
              <button
                class="inline-flex items-center gap-2 rounded border border-outline bg-surface-container-high px-3 py-2 text-xs font-bold text-on-surface transition-colors hover:border-primary disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                :disabled="ui.loading"
                @click="events.refreshEventFolder()"
              >
                <RefreshCw :size="16" aria-hidden="true" />
                Refresh Folder
              </button>
              <button
                class="inline-flex items-center gap-2 rounded border border-outline bg-surface-container-high px-3 py-2 text-xs font-bold text-on-surface transition-colors hover:border-primary disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                :disabled="ui.loading"
                @click="events.downloadMissingTracks()"
              >
                <FileAudio :size="16" aria-hidden="true" />
                Download
              </button>
              <button
                class="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-xs font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                :disabled="ui.loading || !events.readyToApply || !system.rekordboxStatus?.mutationAllowed"
                @click="events.applyActiveEvent()"
              >
                <ShieldCheck :size="16" aria-hidden="true" />
                Apply Ready Tracks
              </button>
              <button
                class="inline-flex items-center gap-2 rounded border border-error/60 bg-error/10 px-3 py-2 text-xs font-bold text-error transition-colors hover:border-error disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                :disabled="ui.loading"
                @click="events.deleteActiveEvent()"
              >
                <Trash2 :size="16" aria-hidden="true" />
                Delete Event
              </button>
            </div>
          </div>

          <div class="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <strong class="block text-2xl text-on-surface">{{ events.activeEvent.matchedTracks }}</strong>
              <span class="text-xs text-on-surface-variant">matched</span>
            </div>
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <strong class="block text-2xl text-on-surface">{{ events.activeEvent.readyTracks }}</strong>
              <span class="text-xs text-on-surface-variant">ready</span>
            </div>
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <strong class="block text-2xl text-on-surface">{{ events.activeEvent.appliedTracks }}</strong>
              <span class="text-xs text-on-surface-variant">applied</span>
            </div>
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <strong class="block text-2xl text-on-surface">{{ events.activeEvent.missingTracks }}</strong>
              <span class="text-xs text-on-surface-variant">missing</span>
            </div>
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <strong class="block text-2xl text-on-surface">{{ events.activeEvent.ambiguousTracks }}</strong>
              <span class="text-xs text-on-surface-variant">ambiguous</span>
            </div>
          </div>

          <div class="mb-6 rounded-lg border border-outline-variant bg-surface-container-high p-4">
            <div class="mb-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <h3 class="font-bold text-on-surface">Acquisition</h3>
                <p class="mt-1 text-xs text-on-surface-variant">
                  {{ system.deemixStatus?.detail ?? "Provider status not loaded." }}
                </p>
              </div>
              <StatusBadge :tone="system.deemixStatus?.available && system.deemixStatus?.authenticated ? 'ok' : 'warn'">
                {{ system.deemixStatus?.available && system.deemixStatus?.authenticated ? "Deemix ready" : "Deemix unavailable" }}
              </StatusBadge>
            </div>
            <div class="grid grid-cols-2 gap-2 text-center md:grid-cols-6">
              <div v-for="metric in [
                ['queued', events.acquisitionCounts.queued],
                ['downloading', events.acquisitionCounts.downloading],
                ['downloaded', events.acquisitionCounts.downloaded],
                ['ready', events.acquisitionCounts.ready],
                ['failed', events.acquisitionCounts.failed],
                ['ambiguous', events.acquisitionCounts.ambiguous]
              ]" :key="metric[0]" class="rounded bg-surface p-3">
                <strong class="block text-lg text-on-surface">{{ metric[1] }}</strong>
                <span class="text-[10px] uppercase text-on-surface-variant">{{ metric[0] }}</span>
              </div>
            </div>
          </div>

          <div class="mb-4 flex flex-wrap gap-2">
            <button
              v-for="filter in reviewFilters"
              :key="filter"
              class="rounded border px-3 py-1.5 text-xs font-bold capitalize transition-colors"
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

          <TrackReviewTable
            :active-event="events.activeEvent"
            :tracks="events.filteredTracks"
            :acquisition-jobs="events.acquisitionJobs"
            :rekordbox-tags="spotify.rekordboxTags"
            @accept-suggested-match="events.acceptSuggestedMatch($event)"
            @assign-staging-file="(track, filePath) => events.assignStagingFile(track, filePath)"
            @update-permanent="(track, permanent) => events.updatePermanent(track, permanent)"
            @update-track-tags="(track, tags) => events.updateTrackTags(track, tags)"
          />

          <div v-if="events.activeEvent.stagingFiles.length > 0" class="mt-6">
            <div class="mb-3 flex items-center gap-2">
              <FileAudio class="text-secondary" :size="18" aria-hidden="true" />
              <h3 class="font-bold text-on-surface">Staged Files</h3>
            </div>
            <div class="grid gap-2 md:grid-cols-2">
              <div
                v-for="file in events.activeEvent.stagingFiles"
                :key="file.filePath"
                class="rounded border border-outline-variant bg-surface-container-high p-3"
              >
                <strong class="block truncate text-sm text-on-surface">{{ file.title }}</strong>
                <span class="text-xs text-on-surface-variant">
                  {{ file.artist || "Unknown artist" }} - {{ file.status }}
                </span>
              </div>
            </div>
          </div>
        </section>

        <section
          v-else
          class="rounded-xl border border-outline-variant bg-surface-container p-8 text-on-surface-variant"
        >
          Select an event import to review tracks, files, downloads, and tags.
        </section>
      </div>
    </div>
  </div>
</template>
