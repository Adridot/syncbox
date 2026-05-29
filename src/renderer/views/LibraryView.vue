<script setup lang="ts">
import {
  CheckCircle2,
  Download,
  Library,
  Plus,
  RefreshCw,
  Tags,
  UploadCloud,
  X
} from "@lucide/vue";
import { computed, ref } from "vue";
import type {
  LibraryReview,
  LibrarySource,
  LibraryTrackReview,
  RekordboxStatus,
  RekordboxTag,
  SpotifyPlaylistSummary,
  SyncProposal,
  TagPlaylistMapping
} from "../lib/api";
import type { MappingFormState, TagRuleFormState } from "../types/ui";
import PlaylistCard from "../components/PlaylistCard.vue";
import StatusBadge from "../components/StatusBadge.vue";

const props = defineProps<{
  spotifyPlaylists: SpotifyPlaylistSummary[];
  spotifyPlaylistTotal: number;
  librarySources: LibrarySource[];
  activeReview: LibraryReview | null;
  selectedTrackIds: string[];
  selectedTracks: LibraryTrackReview[];
  tagPlaylistMappings: TagPlaylistMapping[];
  rekordboxTags: RekordboxTag[];
  proposals: SyncProposal[];
  tagRuleForm: TagRuleFormState;
  mappingForm: MappingFormState;
  tagRuleTagInput: string;
  availableTagNames: string[];
  searchQuery: string;
  readyToApply: boolean;
  rekordboxStatus: RekordboxStatus | null;
  loading: boolean;
}>();

const emit = defineEmits<{
  selectTagRulePlaylist: [playlistId: string];
  selectMappingPlaylist: [playlistId: string];
  saveTagRule: [];
  saveTagPlaylistMapping: [];
  openSource: [source: LibrarySource];
  syncSource: [source: LibrarySource];
  toggleTrack: [track: LibraryTrackReview, selected: boolean];
  toggleAllTracks: [tracks: LibraryTrackReview[], selected: boolean];
  updateSelectedTags: [tags: string[]];
  updateTrackTags: [track: LibraryTrackReview, tags: string];
  downloadSelected: [];
  applySource: [];
  addTagRuleTag: [tagName?: string];
  removeTagRuleTag: [tagName: string];
  updateTagRuleTagInput: [value: string];
}>();

const reviewFilter = ref("actionable");
const drawerTagInput = ref("");

const filteredSpotifyPlaylists = computed(() => {
  const query = props.searchQuery.trim().toLowerCase();
  if (!query) return props.spotifyPlaylists;
  return props.spotifyPlaylists.filter((playlist) =>
    playlist.name.toLowerCase().includes(query)
  );
});

const filteredTracks = computed(() => {
  const tracks = props.activeReview?.tracks ?? [];
  if (reviewFilter.value === "actionable") {
    return tracks.filter((track) =>
      ["new", "missing", "ready", "matched", "conflict"].includes(track.status)
    );
  }
  if (reviewFilter.value === "all") return tracks;
  return tracks.filter((track) => track.status === reviewFilter.value);
});

const selectedTagNames = computed(() => {
  const names = new Set<string>();
  for (const track of props.selectedTracks) {
    for (const tagName of track.tags) names.add(tagName);
  }
  return [...names].sort((left, right) => left.localeCompare(right));
});

const allFilteredSelected = computed(() => {
  if (filteredTracks.value.length === 0) return false;
  const selected = new Set(props.selectedTrackIds);
  return filteredTracks.value.every((track) => selected.has(track.spotifyTrackId));
});

const pendingLibraryProposals = computed(() =>
  props.proposals.filter(
    (proposal) =>
      proposal.status === "pending" &&
      proposal.payload?.sourceId === props.activeReview?.source.id
  )
);

const reviewFilters = [
  "actionable",
  "new",
  "missing",
  "ready",
  "matched",
  "conflict",
  "imported",
  "removed_from_source",
  "all"
];

function sourceTone(source: LibrarySource): "ok" | "warn" | "active" | "muted" {
  if (source.conflictTrackCount > 0) return "warn";
  if (source.newTrackCount > 0 || source.readyTrackCount > 0) return "active";
  if (source.importedTrackCount > 0) return "ok";
  return "muted";
}

function statusTone(status: string): "ok" | "warn" | "active" | "muted" | "neutral" {
  if (["matched", "ready", "imported"].includes(status)) return "ok";
  if (["new", "missing", "conflict", "removed_from_source"].includes(status)) return "warn";
  if (status === "downloading") return "active";
  return "muted";
}

function rekordboxTrackTitle(track: LibraryTrackReview): string {
  if (track.rekordboxTitle) return track.rekordboxTitle;
  if (track.stagingFilePath) return "Downloaded audio file";
  if (track.rekordboxContentId) return `Rekordbox ${track.rekordboxContentId}`;
  return "No Rekordbox match";
}

function rekordboxTrackDetail(track: LibraryTrackReview): string {
  if (track.rekordboxArtist) return track.rekordboxArtist;
  if (track.rekordboxFilePath) return track.rekordboxFilePath;
  if (track.stagingFilePath) return track.stagingFilePath;
  return track.reason;
}

function applyDrawerTag(tagName: string): void {
  const trimmed = tagName.trim();
  if (!trimmed) return;
  const tags = new Set(selectedTagNames.value);
  tags.add(trimmed);
  drawerTagInput.value = "";
  emit("updateSelectedTags", [...tags]);
}

function removeDrawerTag(tagName: string): void {
  emit(
    "updateSelectedTags",
    selectedTagNames.value.filter((item) => item !== tagName)
  );
}
</script>

<template>
  <div class="flex h-full overflow-hidden">
    <div class="min-w-0 flex-1 overflow-y-auto p-6 md:p-8">
      <div class="mx-auto w-full max-w-[1600px]">
        <div class="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <h2 class="mb-1 text-2xl font-bold text-on-surface md:text-3xl">My Library</h2>
            <p class="text-sm text-on-surface-variant">
              Permanent Spotify sources curated into Rekordbox MyTags.
            </p>
          </div>
          <StatusBadge tone="active">
            {{ librarySources.length }} followed sources
          </StatusBadge>
        </div>

        <section class="mb-8 rounded-xl border border-outline-variant bg-surface-container-high p-6">
          <div class="mb-5 flex items-center gap-2">
            <Plus class="text-primary" :size="20" aria-hidden="true" />
            <h3 class="text-lg font-bold text-on-surface">Follow Permanent Playlist</h3>
          </div>
          <form class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]" @submit.prevent="emit('saveTagRule')">
            <label class="grid gap-2">
              <span class="text-sm font-bold text-on-surface">Spotify source</span>
              <select
                class="rounded border border-outline bg-surface-container px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
                v-model="tagRuleForm.sourcePlaylistId"
                required
                @change="emit('selectTagRulePlaylist', ($event.target as HTMLSelectElement).value)"
              >
                <option value="">Select a Spotify playlist</option>
                <option v-for="playlist in spotifyPlaylists" :key="playlist.id" :value="playlist.id">
                  {{ playlist.name }} - {{ playlist.trackCount }} tracks
                </option>
              </select>
            </label>

            <label class="grid gap-2">
              <span class="text-sm font-bold text-on-surface">Default existing MyTags</span>
              <div class="grid gap-2">
                <div v-if="tagRuleForm.tags.length > 0" class="flex flex-wrap gap-2">
                  <button
                    v-for="tagName in tagRuleForm.tags"
                    :key="tagName"
                    class="inline-flex items-center gap-2 rounded border border-outline bg-surface-variant px-2.5 py-1 text-xs font-bold text-on-surface"
                    type="button"
                    @click="emit('removeTagRuleTag', tagName)"
                  >
                    {{ tagName }}
                    <X :size="12" aria-hidden="true" />
                  </button>
                </div>
                <div class="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
                  <input
                    class="rounded border border-outline bg-surface-container px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
                    :value="tagRuleTagInput"
                    list="library-source-tags"
                    placeholder="Existing Rekordbox MyTag"
                    @input="emit('updateTagRuleTagInput', ($event.target as HTMLInputElement).value)"
                    @change="emit('addTagRuleTag')"
                    @keydown.enter.prevent="emit('addTagRuleTag')"
                  />
                  <button
                    class="rounded border border-outline bg-surface px-3 py-2 text-xs font-bold text-on-surface transition-colors hover:border-primary"
                    type="button"
                    @click="emit('addTagRuleTag')"
                  >
                    Add
                  </button>
                </div>
                <datalist id="library-source-tags">
                  <option v-for="tagName in availableTagNames" :key="tagName" :value="tagName" />
                </datalist>
              </div>
            </label>

            <button
              class="self-end rounded bg-primary px-5 py-2 text-sm font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02]"
              type="submit"
            >
              Follow
            </button>
          </form>
        </section>

        <section class="mb-8">
          <div class="mb-4 flex items-center justify-between">
            <h3 class="text-lg font-bold text-on-surface">Permanent Sources</h3>
            <span class="text-xs text-on-surface-variant">
              {{ librarySources.length }} tracked
            </span>
          </div>

          <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            <article
              v-for="source in librarySources"
              :key="source.id"
              class="group rounded-lg border border-outline-variant bg-surface-container-high p-4 transition-all hover:border-primary"
              :class="activeReview?.source.id === source.id ? 'border-primary bg-primary/5' : ''"
            >
              <button class="mb-4 flex w-full items-start gap-4 text-left" type="button" @click="emit('openSource', source)">
                <div class="grid h-16 w-16 shrink-0 place-items-center rounded border border-outline bg-surface-container">
                  <img
                    v-if="source.imageUrl"
                    class="h-full w-full rounded object-cover"
                    :src="source.imageUrl"
                    :alt="`${source.spotifyPlaylistName} cover`"
                  />
                  <Library v-else class="text-primary" :size="28" aria-hidden="true" />
                </div>
                <div class="min-w-0">
                  <h4 class="truncate font-bold text-on-surface group-hover:text-primary">
                    {{ source.spotifyPlaylistName }}
                  </h4>
                  <p class="mt-1 text-xs text-on-surface-variant">
                    {{ source.trackCount }} tracks - {{ source.tags.join(", ") }}
                  </p>
                  <p class="mt-1 text-[10px] uppercase text-on-surface-variant">
                    {{ source.lastSyncedAt ? `Synced ${source.lastSyncedAt}` : "Never synced" }}
                  </p>
                </div>
              </button>
              <div class="flex items-center justify-between border-t border-outline-variant pt-3">
                <StatusBadge :tone="sourceTone(source)">
                  {{ source.newTrackCount > 0 ? `+${source.newTrackCount} new` : source.status }}
                </StatusBadge>
                <button
                  class="inline-flex items-center gap-2 rounded border border-outline bg-surface px-3 py-1.5 text-xs font-bold text-on-surface transition-colors hover:border-primary"
                  type="button"
                  :disabled="loading"
                  @click="emit('syncSource', source)"
                >
                  <RefreshCw :size="14" aria-hidden="true" />
                  Sync
                </button>
              </div>
            </article>

            <div
              v-if="librarySources.length === 0"
              class="rounded-lg border border-dashed border-outline bg-surface-container p-6 text-sm text-on-surface-variant"
            >
              No permanent sources configured.
            </div>
          </div>
        </section>

        <section
          v-if="activeReview"
          class="mb-8 rounded-xl border border-outline-variant bg-surface-container p-5 md:p-6"
        >
          <div class="mb-6 flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <div class="mb-2 flex flex-wrap items-center gap-3">
                <h3 class="text-xl font-bold text-on-surface">{{ activeReview.source.spotifyPlaylistName }}</h3>
                <StatusBadge :tone="sourceTone(activeReview.source)">
                  {{ activeReview.newTracks }} new
                </StatusBadge>
                <StatusBadge tone="muted">
                  {{ selectedTrackIds.length }} selected
                </StatusBadge>
              </div>
              <p class="text-sm text-on-surface-variant">
                {{ activeReview.totalTracks }} tracks tracked, {{ activeReview.readyTracks }} ready, {{ activeReview.conflictTracks }} conflicts.
              </p>
            </div>
            <div class="flex flex-wrap gap-2">
              <button
                class="inline-flex items-center gap-2 rounded border border-outline bg-surface-container-high px-3 py-2 text-xs font-bold text-on-surface transition-colors hover:border-primary disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                :disabled="loading"
                @click="emit('downloadSelected')"
              >
                <Download :size="16" aria-hidden="true" />
                Download
              </button>
              <button
                class="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-xs font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                :disabled="loading || !readyToApply || !rekordboxStatus?.mutationAllowed"
                @click="emit('applySource')"
              >
                <UploadCloud :size="16" aria-hidden="true" />
                Import to Rekordbox
              </button>
            </div>
          </div>

          <div class="mb-6 grid grid-cols-2 gap-3 md:grid-cols-6">
            <div v-for="metric in [
              ['new', activeReview.newTracks],
              ['matched', activeReview.matchedTracks],
              ['ready', activeReview.readyTracks],
              ['imported', activeReview.importedTracks],
              ['conflict', activeReview.conflictTracks],
              ['removed', activeReview.removedTracks]
            ]" :key="metric[0]" class="rounded border border-outline-variant bg-surface-container-high p-3">
              <strong class="block text-2xl text-on-surface">{{ metric[1] }}</strong>
              <span class="text-xs text-on-surface-variant">{{ metric[0] }}</span>
            </div>
          </div>

          <div class="mb-4 flex flex-wrap items-center gap-2">
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
              @click="reviewFilter = filter"
            >
              {{ filter.replaceAll("_", " ") }}
            </button>
          </div>

          <div class="overflow-auto rounded-lg border border-outline-variant">
            <table class="w-full min-w-[1120px] border-collapse whitespace-nowrap text-left">
              <thead class="sticky top-0 z-10 border-b border-outline-variant bg-surface-container-high font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
                <tr>
                  <th class="px-4 py-3">
                    <input
                      class="h-4 w-4 rounded border-outline-variant bg-surface accent-primary"
                      type="checkbox"
                      :checked="allFilteredSelected"
                      @change="emit('toggleAllTracks', filteredTracks, ($event.target as HTMLInputElement).checked)"
                    />
                  </th>
                  <th class="px-4 py-3">Requested Track</th>
                  <th class="px-4 py-3">Rekordbox / File</th>
                  <th class="px-4 py-3">Status</th>
                  <th class="px-4 py-3">Tags</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-outline-variant/50 text-sm">
                <tr
                  v-for="track in filteredTracks"
                  :key="track.id"
                  class="border-l-2 border-transparent bg-surface transition-colors hover:bg-surface-container-high"
                  :class="{
                    'border-l-primary bg-primary/5': track.status === 'ready' || track.status === 'matched',
                    'border-l-tertiary bg-tertiary/5': track.status === 'new' || track.status === 'missing' || track.status === 'conflict'
                  }"
                >
                  <td class="px-4 py-3 align-top">
                    <input
                      class="h-4 w-4 rounded border-outline-variant bg-surface accent-primary"
                      type="checkbox"
                      :checked="selectedTrackIds.includes(track.spotifyTrackId)"
                      @change="emit('toggleTrack', track, ($event.target as HTMLInputElement).checked)"
                    />
                  </td>
                  <td class="px-4 py-3 align-top">
                    <strong class="block max-w-[300px] truncate text-on-surface">{{ track.title }}</strong>
                    <span class="block max-w-[300px] truncate text-xs text-on-surface-variant">
                      {{ track.artists.join(", ") }}
                    </span>
                  </td>
                  <td class="px-4 py-3 align-top">
                    <strong class="block max-w-[340px] truncate text-on-surface">{{ rekordboxTrackTitle(track) }}</strong>
                    <span class="block max-w-[340px] truncate text-xs text-on-surface-variant">
                      {{ rekordboxTrackDetail(track) }}
                    </span>
                    <span v-if="track.rekordboxContentId" class="text-xs text-on-surface-variant">
                      {{ track.matchMethod ?? "match" }} - {{ track.confidence }}%
                    </span>
                  </td>
                  <td class="px-4 py-3 align-top">
                    <StatusBadge :tone="statusTone(track.status)">
                      {{ track.status.replaceAll("_", " ") }}
                    </StatusBadge>
                  </td>
                  <td class="px-4 py-3 align-top">
                    <input
                      class="w-64 rounded border border-outline bg-surface-container px-3 py-2 text-xs text-on-surface focus:border-primary focus:outline-none"
                      :value="track.tags.join(', ')"
                      list="library-review-tags"
                      placeholder="Existing MyTags"
                      @change="emit('updateTrackTags', track, ($event.target as HTMLInputElement).value)"
                    />
                  </td>
                </tr>
                <tr v-if="filteredTracks.length === 0">
                  <td class="px-4 py-6 text-on-surface-variant" colspan="5">
                    No tracks for this filter.
                  </td>
                </tr>
              </tbody>
            </table>
            <datalist id="library-review-tags">
              <option v-for="tagItem in rekordboxTags" :key="tagItem.id" :value="tagItem.name" />
            </datalist>
          </div>

          <div v-if="pendingLibraryProposals.length > 0" class="mt-6 rounded-lg border border-tertiary/30 bg-tertiary/5 p-4">
            <h3 class="mb-2 font-bold text-on-surface">Pending Removal Proposals</h3>
            <p class="text-xs text-on-surface-variant">
              {{ pendingLibraryProposals.length }} track(s) were removed from Spotify and need manual review.
            </p>
          </div>
        </section>

        <section class="mb-8 rounded-xl border border-outline-variant bg-surface-container-high p-6">
          <div class="mb-5 flex items-center gap-2">
            <Tags class="text-secondary" :size="20" aria-hidden="true" />
            <h3 class="text-lg font-bold text-on-surface">Tag to Spotify Playlist Mappings</h3>
          </div>
          <form class="mb-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]" @submit.prevent="emit('saveTagPlaylistMapping')">
            <label class="grid gap-2">
              <span class="text-sm font-bold text-on-surface">Existing MyTag</span>
              <input
                class="rounded border border-outline bg-surface-container px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
                v-model="mappingForm.tagName"
                list="mapping-tags"
                placeholder="MyTag"
              />
              <datalist id="mapping-tags">
                <option v-for="tagName in availableTagNames" :key="tagName" :value="tagName" />
              </datalist>
            </label>
            <label class="grid gap-2">
              <span class="text-sm font-bold text-on-surface">Spotify playlist</span>
              <select
                class="rounded border border-outline bg-surface-container px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
                v-model="mappingForm.spotifyPlaylistId"
                required
                @change="emit('selectMappingPlaylist', ($event.target as HTMLSelectElement).value)"
              >
                <option value="">Select playlist</option>
                <option v-for="playlist in spotifyPlaylists" :key="playlist.id" :value="playlist.id">
                  {{ playlist.name }}
                </option>
              </select>
            </label>
            <button class="self-end rounded bg-primary px-5 py-2 text-sm font-bold text-white" type="submit">
              Save Mapping
            </button>
          </form>
          <div class="grid gap-2 md:grid-cols-2">
            <div
              v-for="mapping in tagPlaylistMappings"
              :key="mapping.id"
              class="rounded border border-outline-variant bg-surface-container p-3 text-sm"
            >
              <strong class="text-on-surface">{{ mapping.tagName }}</strong>
              <span class="text-on-surface-variant"> -> {{ mapping.spotifyPlaylistName }}</span>
            </div>
            <div v-if="tagPlaylistMappings.length === 0" class="text-sm text-on-surface-variant">
              No mappings configured.
            </div>
          </div>
        </section>

        <section>
          <div class="mb-4 flex items-center justify-between">
            <h3 class="text-lg font-bold text-on-surface">Available Spotify Playlists</h3>
            <span class="text-xs text-on-surface-variant">
              {{ filteredSpotifyPlaylists.length }} of {{ spotifyPlaylistTotal || spotifyPlaylists.length }}
            </span>
          </div>
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            <PlaylistCard
              v-for="playlist in filteredSpotifyPlaylists"
              :key="playlist.id"
              :playlist="playlist"
              @select="
                tagRuleForm.sourcePlaylistId = playlist.id;
                emit('selectTagRulePlaylist', playlist.id);
              "
            />
          </div>
        </section>
      </div>
    </div>

    <aside
      v-if="selectedTrackIds.length > 0"
      class="hidden h-full w-[380px] shrink-0 flex-col border-l border-outline-variant bg-surface-container p-6 shadow-2xl xl:flex"
    >
      <div class="mb-6 flex items-center justify-between">
        <h2 class="text-lg font-bold text-on-surface">Batch Tagging</h2>
        <StatusBadge tone="active">{{ selectedTrackIds.length }} selected</StatusBadge>
      </div>

      <div class="mb-6 rounded border border-primary/20 bg-primary/5 p-4">
        <div class="mb-1 text-[10px] font-bold uppercase text-primary">Selected source</div>
        <div class="text-xl font-bold text-on-surface">
          {{ activeReview?.source.spotifyPlaylistName ?? "My Library" }}
        </div>
      </div>

      <div class="mb-6">
        <h3 class="mb-3 text-sm font-bold text-on-surface">Applied MyTags</h3>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="tagName in selectedTagNames"
            :key="tagName"
            class="inline-flex items-center gap-2 rounded border border-outline bg-surface-variant px-2.5 py-1 text-xs font-bold text-on-surface"
            type="button"
            @click="removeDrawerTag(tagName)"
          >
            {{ tagName }}
            <X :size="12" aria-hidden="true" />
          </button>
          <span v-if="selectedTagNames.length === 0" class="text-sm text-on-surface-variant">
            No tags selected.
          </span>
        </div>
      </div>

      <div class="grid gap-2">
        <input
          class="rounded border border-outline bg-surface-container-high px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
          v-model="drawerTagInput"
          list="drawer-tags"
          placeholder="Add existing MyTag"
          @change="applyDrawerTag(drawerTagInput)"
          @keydown.enter.prevent="applyDrawerTag(drawerTagInput)"
        />
        <datalist id="drawer-tags">
          <option v-for="tagName in availableTagNames" :key="tagName" :value="tagName" />
        </datalist>
        <button
          class="inline-flex items-center justify-center gap-2 rounded bg-primary px-4 py-2 text-sm font-bold text-white"
          type="button"
          @click="applyDrawerTag(drawerTagInput)"
        >
          <CheckCircle2 :size="16" aria-hidden="true" />
          Apply Tag
        </button>
      </div>
    </aside>
  </div>
</template>
