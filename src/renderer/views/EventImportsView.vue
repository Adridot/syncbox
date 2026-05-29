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
import type {
  AcquisitionJob,
  DeemixStatus,
  EventReview,
  EventSummary,
  EventTrackReview,
  LiveImportPackage,
  RekordboxStatus,
  RekordboxTag,
  SpotifyPlaylistSummary
} from "../lib/api";
import type { ImportFormState } from "../types/ui";
import EventCard from "../components/EventCard.vue";
import MetricCard from "../components/MetricCard.vue";
import PlaylistCard from "../components/PlaylistCard.vue";
import StatusBadge from "../components/StatusBadge.vue";
import TrackReviewTable from "../components/TrackReviewTable.vue";

const props = defineProps<{
  importForm: ImportFormState;
  spotifyPlaylists: SpotifyPlaylistSummary[];
  eventSummaries: EventSummary[];
  activeEvent: EventReview | null;
  acquisitionJobs: AcquisitionJob[];
  acquisitionCounts: {
    queued: number;
    downloading: number;
    downloaded: number;
    ready: number;
    failed: number;
    ambiguous: number;
  };
  deemixStatus: DeemixStatus | null;
  reviewFilter: string;
  filteredEventTracks: EventTrackReview[];
  readyToApply: boolean;
  rekordboxStatus: RekordboxStatus | null;
  rekordboxTags: RekordboxTag[];
  liveImportPackage: LiveImportPackage | null;
  loading: boolean;
  searchQuery: string;
}>();

const emit = defineEmits<{
  analyzeImport: [];
  createLiveImportPackage: [];
  selectSpotifyPlaylist: [playlist: SpotifyPlaylistSummary];
  openEvent: [event: EventSummary];
  openDesktopPath: [path: string];
  refreshEventFolder: [];
  downloadMissingTracks: [];
  applyActiveEvent: [];
  deleteActiveEvent: [];
  updateReviewFilter: [filter: string];
  acceptSuggestedMatch: [track: EventTrackReview];
  assignStagingFile: [track: EventTrackReview, filePath: string];
  updatePermanent: [track: EventTrackReview, permanent: boolean];
  updateTrackTags: [track: EventTrackReview, tags: string];
}>();

const reviewFilters = ["all", "matched", "ready", "applied", "missing", "ambiguous", "ignored"];

function eventStatusTone(event: EventSummary): "ok" | "warn" | "active" {
  if (event.status === "applied") return "ok";
  if (event.readyTracks < event.totalTracks) return "warn";
  return "active";
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
          <form class="grid gap-3 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_auto]" @submit.prevent="emit('analyzeImport')">
            <div class="relative">
              <Link2
                class="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant"
                :size="16"
                aria-hidden="true"
              />
              <input
                class="w-full rounded border border-outline bg-surface-container py-2 pl-9 pr-4 text-sm text-on-surface transition-colors focus:border-primary focus:outline-none"
                v-model="importForm.playlistUrl"
                type="url"
                placeholder="https://open.spotify.com/playlist/..."
                required
              />
            </div>
            <input
              class="rounded border border-outline bg-surface-container px-4 py-2 text-sm text-on-surface transition-colors focus:border-primary focus:outline-none"
              v-model="importForm.eventName"
              type="text"
              placeholder="Event name"
              required
            />
            <button
              class="inline-flex items-center justify-center gap-2 rounded bg-primary px-6 py-2 text-sm font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-60"
              type="submit"
              :disabled="loading"
            >
              <AreaChart :size="18" aria-hidden="true" />
              Analyze Import
            </button>
          </form>
        </section>

        <MetricCard
          title="Active Events"
          :value="eventSummaries.length"
          :detail="`${eventSummaries.reduce((total, event) => total + event.totalTracks, 0)} tracks tracked`"
          :icon="Cpu"
          tone="primary"
        />
      </div>

      <section class="mb-10" v-if="spotifyPlaylists.length > 0">
        <div class="mb-4 flex items-center justify-between">
          <h3 class="text-lg font-bold text-on-surface">Select a Spotify Playlist</h3>
          <span class="text-xs text-on-surface-variant">
            {{ spotifyPlaylists.length }} loaded
          </span>
        </div>
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          <PlaylistCard
            v-for="playlist in spotifyPlaylists.filter((playlist) => !searchQuery || playlist.name.toLowerCase().includes(searchQuery.toLowerCase()))"
            :key="playlist.id"
            :playlist="playlist"
            @select="emit('selectSpotifyPlaylist', playlist)"
          />
        </div>
      </section>

      <div class="grid grid-cols-1 gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
        <section>
          <div class="mb-4 flex items-center justify-between">
            <h3 class="text-lg font-bold text-on-surface">Temporary Playlists</h3>
            <StatusBadge tone="active">{{ eventSummaries.length }} events</StatusBadge>
          </div>
          <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-1">
            <EventCard
              v-for="event in eventSummaries"
              :key="event.id"
              :event="event"
              :active="activeEvent?.id === event.id"
              @open="emit('openEvent', event)"
            />
            <div
              v-if="eventSummaries.length === 0"
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
                @click="emit('createLiveImportPackage')"
              >
                Prepare
              </button>
            </div>
            <div v-if="liveImportPackage" class="space-y-3 text-xs text-on-surface-variant">
              <p class="break-all">{{ liveImportPackage.audioDir }}</p>
              <div class="flex flex-wrap gap-2">
                <button
                  class="rounded border border-outline bg-surface-container px-3 py-1.5 font-bold text-on-surface transition-colors hover:border-primary"
                  type="button"
                  @click="emit('openDesktopPath', liveImportPackage.audioDir)"
                >
                  Open Audio Folder
                </button>
                <button
                  class="rounded border border-outline bg-surface-container px-3 py-1.5 font-bold text-on-surface transition-colors hover:border-primary"
                  type="button"
                  @click="emit('openDesktopPath', liveImportPackage.playlistPath)"
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
          v-if="activeEvent"
          class="min-w-0 rounded-xl border border-outline-variant bg-surface-container p-5 md:p-6"
        >
          <div class="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div class="mb-2 flex items-center gap-3">
                <h3 class="text-xl font-bold text-on-surface">{{ activeEvent.eventName }}</h3>
                <StatusBadge :tone="eventStatusTone({
                  id: activeEvent.id,
                  eventName: activeEvent.eventName,
                  spotifyPlaylistName: activeEvent.spotifyPlaylistName,
                  status: activeEvent.status,
                  totalTracks: activeEvent.totalTracks,
                  readyTracks: activeEvent.readyTracks,
                  createdAt: ''
                })">
                  {{ activeEvent.status }}
                </StatusBadge>
              </div>
              <p class="text-sm text-on-surface-variant">{{ activeEvent.spotifyPlaylistName }}</p>
            </div>
            <div class="flex flex-wrap gap-2">
              <button
                class="inline-flex items-center gap-2 rounded border border-outline bg-surface-container-high px-3 py-2 text-xs font-bold text-on-surface transition-colors hover:border-primary"
                type="button"
                @click="emit('openDesktopPath', activeEvent.audioDir)"
              >
                <FolderOpen :size="16" aria-hidden="true" />
                Open Audio
              </button>
              <button
                class="inline-flex items-center gap-2 rounded border border-outline bg-surface-container-high px-3 py-2 text-xs font-bold text-on-surface transition-colors hover:border-primary disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                :disabled="loading"
                @click="emit('refreshEventFolder')"
              >
                <RefreshCw :size="16" aria-hidden="true" />
                Refresh Folder
              </button>
              <button
                class="inline-flex items-center gap-2 rounded border border-outline bg-surface-container-high px-3 py-2 text-xs font-bold text-on-surface transition-colors hover:border-primary disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                :disabled="loading"
                @click="emit('downloadMissingTracks')"
              >
                <FileAudio :size="16" aria-hidden="true" />
                Download
              </button>
              <button
                class="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-xs font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                :disabled="loading || !readyToApply || !rekordboxStatus?.mutationAllowed"
                @click="emit('applyActiveEvent')"
              >
                <ShieldCheck :size="16" aria-hidden="true" />
                Apply Ready Tracks
              </button>
              <button
                class="inline-flex items-center gap-2 rounded border border-error/60 bg-error/10 px-3 py-2 text-xs font-bold text-error transition-colors hover:border-error disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                :disabled="loading"
                @click="emit('deleteActiveEvent')"
              >
                <Trash2 :size="16" aria-hidden="true" />
                Delete Event
              </button>
            </div>
          </div>

          <div class="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <strong class="block text-2xl text-on-surface">{{ activeEvent.matchedTracks }}</strong>
              <span class="text-xs text-on-surface-variant">matched</span>
            </div>
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <strong class="block text-2xl text-on-surface">{{ activeEvent.readyTracks }}</strong>
              <span class="text-xs text-on-surface-variant">ready</span>
            </div>
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <strong class="block text-2xl text-on-surface">{{ activeEvent.appliedTracks }}</strong>
              <span class="text-xs text-on-surface-variant">applied</span>
            </div>
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <strong class="block text-2xl text-on-surface">{{ activeEvent.missingTracks }}</strong>
              <span class="text-xs text-on-surface-variant">missing</span>
            </div>
            <div class="rounded border border-outline-variant bg-surface-container-high p-3">
              <strong class="block text-2xl text-on-surface">{{ activeEvent.ambiguousTracks }}</strong>
              <span class="text-xs text-on-surface-variant">ambiguous</span>
            </div>
          </div>

          <div class="mb-6 rounded-lg border border-outline-variant bg-surface-container-high p-4">
            <div class="mb-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <h3 class="font-bold text-on-surface">Acquisition</h3>
                <p class="mt-1 text-xs text-on-surface-variant">
                  {{ deemixStatus?.detail ?? "Provider status not loaded." }}
                </p>
              </div>
              <StatusBadge :tone="deemixStatus?.available && deemixStatus?.authenticated ? 'ok' : 'warn'">
                {{ deemixStatus?.available && deemixStatus?.authenticated ? "Deemix ready" : "Deemix unavailable" }}
              </StatusBadge>
            </div>
            <div class="grid grid-cols-2 gap-2 text-center md:grid-cols-6">
              <div v-for="metric in [
                ['queued', acquisitionCounts.queued],
                ['downloading', acquisitionCounts.downloading],
                ['downloaded', acquisitionCounts.downloaded],
                ['ready', acquisitionCounts.ready],
                ['failed', acquisitionCounts.failed],
                ['ambiguous', acquisitionCounts.ambiguous]
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
                reviewFilter === filter
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-outline bg-surface-container-high text-on-surface-variant hover:text-on-surface'
              "
              type="button"
              @click="emit('updateReviewFilter', filter)"
            >
              {{ filter }}
            </button>
          </div>

          <TrackReviewTable
            :active-event="activeEvent"
            :tracks="filteredEventTracks"
            :acquisition-jobs="acquisitionJobs"
            :rekordbox-tags="rekordboxTags"
            @accept-suggested-match="emit('acceptSuggestedMatch', $event)"
            @assign-staging-file="(track, filePath) => emit('assignStagingFile', track, filePath)"
            @update-permanent="(track, permanent) => emit('updatePermanent', track, permanent)"
            @update-track-tags="(track, tags) => emit('updateTrackTags', track, tags)"
          />

          <div v-if="activeEvent.stagingFiles.length > 0" class="mt-6">
            <div class="mb-3 flex items-center gap-2">
              <FileAudio class="text-secondary" :size="18" aria-hidden="true" />
              <h3 class="font-bold text-on-surface">Staged Files</h3>
            </div>
            <div class="grid gap-2 md:grid-cols-2">
              <div
                v-for="file in activeEvent.stagingFiles"
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
