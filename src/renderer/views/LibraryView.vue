<script setup lang="ts">
import {
  CheckCircle2,
  Library,
  ListFilter,
  RefreshCw,
  Search,
  Settings2,
  UploadCloud,
  X,
} from "@lucide/vue";
import { computed, ref } from "vue";
import DeezerSearchPanel from "../components/DeezerSearchPanel.vue";
import LibrarySetupModal from "../components/LibrarySetupModal.vue";
import StatusBadge from "../components/StatusBadge.vue";
import TrackReviewTable from "../components/TrackReviewTable.vue";
import type { LibrarySource } from "../lib/api";
import { useLibraryStore } from "../stores/library";
import { useProposalsStore } from "../stores/proposals";
import { useSpotifyStore } from "../stores/spotify";
import { useSystemStore } from "../stores/system";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
const system = useSystemStore();
const library = useLibraryStore();
const spotify = useSpotifyStore();
const proposals = useProposalsStore();

const drawerTagInput = ref("");
const sourceSearch = ref("");
const attentionOnly = ref(false);
const setupOpen = ref(false);

type SourceTone = "ok" | "warn" | "active" | "muted";

function sourceTone(source: LibrarySource): SourceTone {
  if (source.conflictTrackCount > 0) return "warn";
  if (source.newTrackCount > 0 || source.readyTrackCount > 0) return "active";
  if (source.importedTrackCount > 0) return "ok";
  return "muted";
}

// Higher = more urgent; drives both the "needs attention" filter and the sort.
function sourcePriority(source: LibrarySource): number {
  if (source.conflictTrackCount > 0) return 3;
  if (source.newTrackCount > 0) return 2;
  if (source.readyTrackCount > 0) return 1;
  return 0;
}

const filteredSources = computed(() => {
  const query = sourceSearch.value.trim().toLowerCase();
  return library.sources
    .filter((s) => !query || s.spotifyPlaylistName.toLowerCase().includes(query))
    .filter((s) => !attentionOnly.value || sourcePriority(s) > 0)
    .slice()
    .sort((a, b) => {
      const pri = sourcePriority(b) - sourcePriority(a);
      if (pri !== 0) return pri;
      return a.spotifyPlaylistName.localeCompare(b.spotifyPlaylistName);
    });
});

const attentionCount = computed(
  () => library.sources.filter((s) => sourcePriority(s) > 0).length
);

const dotClass: Record<SourceTone, string> = {
  warn: "bg-error",
  active: "bg-primary",
  ok: "bg-secondary",
  muted: "bg-on-surface-variant/40",
};

function sourceBadge(source: LibrarySource): { text: string; tone: SourceTone } | null {
  if (source.conflictTrackCount > 0)
    return { text: `${source.conflictTrackCount} conflict`, tone: "warn" };
  if (source.newTrackCount > 0) return { text: `+${source.newTrackCount} new`, tone: "active" };
  if (source.readyTrackCount > 0)
    return { text: `${source.readyTrackCount} ready`, tone: "active" };
  return null;
}

const selectedTagNames = computed(() => {
  const names = new Set<string>();
  for (const track of library.selectedTracks) {
    for (const tagName of track.tags) names.add(tagName);
  }
  return [...names].sort((a, b) => a.localeCompare(b));
});

const pendingLibraryProposals = computed(() =>
  proposals.proposals.filter(
    (p) => p.status === "pending" && p.payload?.sourceId === library.activeReview?.source.id
  )
);

const reviewStats = computed(() => {
  const r = library.activeReview;
  if (!r) return [];
  return [
    { label: "new", value: r.newTracks, accent: r.newTracks > 0 },
    { label: "matched", value: r.matchedTracks, accent: false },
    { label: "ready", value: r.readyTracks, accent: r.readyTracks > 0, tone: "ok" as const },
    { label: "imported", value: r.importedTracks, accent: false },
    { label: "conflict", value: r.conflictTracks, accent: r.conflictTracks > 0, tone: "warn" as const },
    { label: "removed", value: r.removedTracks, accent: false },
  ];
});

function applyDrawerTag(tagName: string): void {
  const trimmed = tagName.trim();
  if (!trimmed) return;
  const tags = new Set(selectedTagNames.value);
  tags.add(trimmed);
  drawerTagInput.value = "";
  library.updateSelectedTags([...tags]);
}

function removeDrawerTag(tagName: string): void {
  library.updateSelectedTags(selectedTagNames.value.filter((t) => t !== tagName));
}
</script>

<template>
  <div class="flex h-full overflow-hidden">
    <!-- LEFT: sources list -->
    <aside class="flex w-[340px] shrink-0 flex-col border-r border-outline-variant bg-background">
      <div class="border-b border-outline-variant px-4 py-3">
        <div class="mb-3 flex items-center gap-2">
          <h2 class="text-sm font-bold uppercase tracking-wide text-on-surface-variant">
            Sources
          </h2>
          <StatusBadge tone="muted">{{ library.sources.length }}</StatusBadge>
        </div>
        <div class="mb-3 flex items-stretch gap-2">
          <button
            type="button"
            class="inline-flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded border border-outline bg-surface px-3 py-1.5 text-xs font-semibold text-on-surface hover:border-primary disabled:opacity-60"
            :disabled="ui.loading || library.sources.length === 0"
            title="Sync all sources"
            @click="library.syncAllSources()"
          >
            <RefreshCw :size="13" aria-hidden="true" /> Sync all
          </button>
          <button
            type="button"
            class="inline-flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded bg-primary px-3 py-1.5 text-xs font-bold text-white"
            title="Follow a playlist / manage mappings"
            @click="setupOpen = true"
          >
            <Settings2 :size="13" aria-hidden="true" /> Manage
          </button>
        </div>

        <div class="relative">
          <Search
            :size="14"
            class="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-on-surface-variant"
            aria-hidden="true"
          />
          <input
            v-model="sourceSearch"
            type="search"
            placeholder="Search sources…"
            class="w-full rounded border border-outline bg-surface-container px-3 py-1.5 pl-8 text-sm text-on-surface focus:border-primary focus:outline-none"
          />
        </div>

        <button
          v-if="attentionCount > 0 || attentionOnly"
          type="button"
          class="mt-2 inline-flex items-center gap-1.5 rounded px-1 text-xs font-semibold transition-colors"
          :class="attentionOnly ? 'text-primary' : 'text-on-surface-variant hover:text-on-surface'"
          @click="attentionOnly = !attentionOnly"
        >
          <ListFilter :size="13" aria-hidden="true" />
          {{ attentionOnly ? "Showing needs-attention" : `Needs attention (${attentionCount})` }}
        </button>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto p-2">
        <button
          v-for="source in filteredSources"
          :key="source.id"
          type="button"
          class="group mb-1 flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left transition-colors"
          :class="
            library.activeReview?.source.id === source.id
              ? 'bg-primary/10 ring-1 ring-primary/40'
              : 'hover:bg-surface-container-high'
          "
          @click="library.openSource(source)"
        >
          <span class="h-2 w-2 shrink-0 rounded-full" :class="dotClass[sourceTone(source)]" aria-hidden="true" />
          <span class="grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded border border-outline bg-surface-container">
            <img
              v-if="source.imageUrl"
              class="h-full w-full object-cover"
              :src="source.imageUrl"
              :alt="`${source.spotifyPlaylistName} cover`"
            />
            <Library v-else class="text-primary" :size="16" aria-hidden="true" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-semibold text-on-surface">
              {{ source.spotifyPlaylistName }}
            </span>
            <span class="block truncate text-xs text-on-surface-variant">
              {{ source.trackCount }} tracks<template v-if="source.tags.length"> · {{ source.tags.join(", ") }}</template>
            </span>
          </span>
          <span class="flex shrink-0 items-center gap-1.5">
            <StatusBadge v-if="sourceBadge(source)" :tone="sourceBadge(source)!.tone">
              {{ sourceBadge(source)!.text }}
            </StatusBadge>
            <RefreshCw
              :size="14"
              class="shrink-0 text-on-surface-variant opacity-0 transition-opacity hover:text-primary group-hover:opacity-100"
              role="button"
              aria-label="Sync source"
              @click.stop="library.syncSource(source)"
            />
          </span>
        </button>

        <p
          v-if="filteredSources.length === 0"
          class="px-3 py-8 text-center text-sm text-on-surface-variant"
        >
          <template v-if="library.sources.length === 0">No sources yet — click <strong>Manage</strong> to follow a playlist.</template>
          <template v-else>No sources match.</template>
        </p>
      </div>
    </aside>

    <!-- RIGHT: selected source review -->
    <div class="flex min-w-0 flex-1 flex-col overflow-hidden">
      <template v-if="library.activeReview">
        <div
          class="shrink-0 border-b border-outline-variant bg-surface-container px-6 py-4"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <h3 class="truncate text-xl font-bold text-on-surface">
                {{ library.activeReview.source.spotifyPlaylistName }}
              </h3>
              <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                <span v-for="stat in reviewStats" :key="stat.label" class="inline-flex items-baseline gap-1">
                  <strong
                    class="text-base"
                    :class="
                      stat.accent
                        ? stat.tone === 'warn'
                          ? 'text-error'
                          : stat.tone === 'ok'
                            ? 'text-secondary'
                            : 'text-primary'
                        : 'text-on-surface'
                    "
                  >{{ stat.value }}</strong>
                  <span class="text-xs text-on-surface-variant">{{ stat.label }}</span>
                </span>
              </div>
            </div>
            <button
              class="inline-flex shrink-0 items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-60"
              type="button"
              :disabled="ui.loading || !library.readyToApply || !system.rekordboxStatus?.mutationAllowed"
              :title="!system.rekordboxStatus?.mutationAllowed ? 'Close Rekordbox to import' : ''"
              @click="library.applySource()"
            >
              <UploadCloud :size="16" aria-hidden="true" />
              Import to Rekordbox
            </button>
          </div>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto px-6 pb-10 pt-4">
          <TrackReviewTable
            :tracks="library.activeReview?.tracks ?? []"
            :selected-ids="library.selectedTrackIds"
            :show-tag-column="true"
            @search-deezer="library.openDeezerSearch($event)"
            @ignore="library.ignoreTrack($event)"
            @unignore="library.unignoreTrack($event)"
            @toggle-select="(track, checked) => library.toggleTrack(track, checked)"
            @toggle-select-all="(tracks, checked) => library.toggleAllTracks(tracks, checked)"
          />

          <div
            v-if="pendingLibraryProposals.length > 0"
            class="mt-6 rounded-lg border border-tertiary/30 bg-tertiary/5 p-4"
          >
            <h3 class="mb-2 font-bold text-on-surface">Pending removal proposals</h3>
            <p class="text-xs text-on-surface-variant">
              {{ pendingLibraryProposals.length }} track(s) were removed from Spotify and need manual review.
            </p>
          </div>
        </div>

        <!-- Batch tagging bar (does not steal width from the track list) -->
        <div
          v-if="library.selectedTrackIds.length > 0"
          class="shrink-0 border-t border-outline-variant bg-surface-container px-6 py-3"
        >
          <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
            <StatusBadge tone="active">{{ library.selectedTrackIds.length }} selected</StatusBadge>

            <div class="flex min-w-0 flex-1 flex-wrap items-center gap-2">
              <span class="text-xs font-semibold text-on-surface-variant">Tags:</span>
              <button
                v-for="tagName in selectedTagNames"
                :key="tagName"
                class="inline-flex items-center gap-1.5 rounded border border-outline bg-surface-variant px-2 py-0.5 text-xs font-bold text-on-surface"
                type="button"
                title="Remove tag"
                @click="removeDrawerTag(tagName)"
              >
                {{ tagName }}
                <X :size="11" aria-hidden="true" />
              </button>
              <span v-if="selectedTagNames.length === 0" class="text-xs text-on-surface-variant">
                none
              </span>
            </div>

            <div class="flex shrink-0 items-center gap-2">
              <input
                class="w-48 rounded border border-outline bg-surface-container-high px-3 py-1.5 text-sm text-on-surface focus:border-primary focus:outline-none"
                v-model="drawerTagInput"
                list="drawer-tags"
                placeholder="Add existing MyTag"
                @change="applyDrawerTag(drawerTagInput)"
                @keydown.enter.prevent="applyDrawerTag(drawerTagInput)"
              />
              <datalist id="drawer-tags">
                <option v-for="tagName in spotify.availableTagNames" :key="tagName" :value="tagName" />
              </datalist>
              <button
                class="inline-flex items-center gap-1.5 whitespace-nowrap rounded bg-primary px-3 py-1.5 text-sm font-bold text-white disabled:opacity-60"
                type="button"
                :disabled="!drawerTagInput.trim()"
                @click="applyDrawerTag(drawerTagInput)"
              >
                <CheckCircle2 :size="15" aria-hidden="true" />
                Apply
              </button>
            </div>
          </div>
        </div>
      </template>

      <div v-else class="grid h-full place-items-center p-8 text-center">
        <div class="max-w-sm">
          <div class="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-full bg-surface-container-high">
            <Library class="text-primary" :size="26" aria-hidden="true" />
          </div>
          <h3 class="mb-1 text-lg font-bold text-on-surface">Select a source</h3>
          <p class="text-sm text-on-surface-variant">
            Pick a playlist on the left to review its tracks, download what's missing, and import to Rekordbox.
          </p>
          <button
            v-if="library.sources.length === 0"
            type="button"
            class="mt-4 inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-bold text-white"
            @click="setupOpen = true"
          >
            <Settings2 :size="15" aria-hidden="true" /> Follow a playlist
          </button>
        </div>
      </div>
    </div>

    <LibrarySetupModal v-if="setupOpen" @close="setupOpen = false" />

    <!-- Deezer search panel — slides in from the right -->
    <DeezerSearchPanel
      v-if="library.deezerSearchTrack"
      :track="library.deezerSearchTrack"
      :query="library.deezerSearchQuery"
      :loading="library.deezerSearchLoading"
      :results="library.deezerSearchResults"
      @update:query="library.deezerSearchQuery = $event"
      @search="library.runDeezerSearch()"
      @queue="library.queueDeezerTrack($event)"
      @close="library.closeDeezerSearch()"
    />
  </div>
</template>
