<script setup lang="ts">
import {
  CheckCircle2,
  Library,
  Plus,
  RefreshCw,
  Tags,
  UploadCloud,
  X
} from "@lucide/vue";
import { computed, ref } from "vue";
import DeezerSearchPanel from "../components/DeezerSearchPanel.vue";
import PlaylistCard from "../components/PlaylistCard.vue";
import StatusBadge from "../components/StatusBadge.vue";
import TrackReviewTable from "../components/TrackReviewTable.vue";
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

// Playlists not yet followed as a permanent source (already-selected ones are
// hidden so you only see what you can still add).
const availableSpotifyPlaylists = computed(() => {
  const followedIds = new Set(library.sources.map((s) => s.spotifyPlaylistId));
  return spotify.playlists.filter((p) => !followedIds.has(p.id));
});

const filteredSpotifyPlaylists = computed(() => {
  const query = ui.searchQuery.trim().toLowerCase();
  if (!query) return availableSpotifyPlaylists.value;
  return availableSpotifyPlaylists.value.filter((p) => p.name.toLowerCase().includes(query));
});

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

function sourceTone(source: { conflictTrackCount: number; newTrackCount: number; readyTrackCount: number; importedTrackCount: number; status: string }): "ok" | "warn" | "active" | "muted" {
  if (source.conflictTrackCount > 0) return "warn";
  if (source.newTrackCount > 0 || source.readyTrackCount > 0) return "active";
  if (source.importedTrackCount > 0) return "ok";
  return "muted";
}

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
            {{ library.sources.length }} followed sources
          </StatusBadge>
        </div>

        <section class="mb-8 rounded-xl border border-outline-variant bg-surface-container-high p-6">
          <div class="mb-5 flex items-center gap-2">
            <Plus class="text-primary" :size="20" aria-hidden="true" />
            <h3 class="text-lg font-bold text-on-surface">Follow Permanent Playlist</h3>
          </div>
          <form class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]" @submit.prevent="library.saveTagRule()">
            <label class="grid gap-2">
              <span class="text-sm font-bold text-on-surface">Spotify source</span>
              <select
                class="rounded border border-outline bg-surface-container px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
                v-model="library.tagRuleForm.sourcePlaylistId"
                required
                @change="library.selectTagRulePlaylist(($event.target as HTMLSelectElement).value)"
              >
                <option value="">Select a Spotify playlist</option>
                <option v-for="playlist in availableSpotifyPlaylists" :key="playlist.id" :value="playlist.id">
                  {{ playlist.name }} - {{ playlist.trackCount }} tracks
                </option>
              </select>
            </label>

            <label class="grid gap-2">
              <span class="text-sm font-bold text-on-surface">Default MyTags <span class="font-normal text-on-surface-variant">(optional)</span></span>
              <div class="grid gap-2">
                <div v-if="library.tagRuleForm.tags.length > 0" class="flex flex-wrap gap-2">
                  <button
                    v-for="tagName in library.tagRuleForm.tags"
                    :key="tagName"
                    class="inline-flex items-center gap-2 rounded border border-outline bg-surface-variant px-2.5 py-1 text-xs font-bold text-on-surface"
                    type="button"
                    @click="library.removeTagRuleTag(tagName)"
                  >
                    {{ tagName }}
                    <X :size="12" aria-hidden="true" />
                  </button>
                </div>
                <div class="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
                  <input
                    class="rounded border border-outline bg-surface-container px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
                    :value="library.tagRuleTagInput"
                    list="library-source-tags"
                    placeholder="Existing Rekordbox MyTag (optional)"
                    @input="library.tagRuleTagInput = ($event.target as HTMLInputElement).value"
                    @change="library.addTagRuleTag()"
                    @keydown.enter.prevent="library.addTagRuleTag()"
                  />
                  <button
                    class="rounded border border-outline bg-surface px-3 py-2 text-xs font-bold text-on-surface transition-colors hover:border-primary"
                    type="button"
                    @click="library.addTagRuleTag()"
                  >
                    Add
                  </button>
                </div>
                <datalist id="library-source-tags">
                  <option v-for="tagName in spotify.availableTagNames" :key="tagName" :value="tagName" />
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
            <div class="flex items-center gap-3">
              <span class="text-xs text-on-surface-variant">{{ library.sources.length }} tracked</span>
              <button
                v-if="library.sources.length > 0"
                class="inline-flex items-center gap-1.5 rounded border border-outline bg-surface px-3 py-1.5 text-xs font-bold text-on-surface transition-colors hover:border-primary disabled:opacity-60"
                type="button"
                :disabled="ui.loading"
                @click="library.syncAllSources()"
              >
                <RefreshCw :size="13" aria-hidden="true" />
                Sync All
              </button>
            </div>
          </div>

          <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            <article
              v-for="source in library.sources"
              :key="source.id"
              class="group rounded-lg border border-outline-variant bg-surface-container-high p-4 transition-all hover:border-primary"
              :class="library.activeReview?.source.id === source.id ? 'border-primary bg-primary/5' : ''"
            >
              <button class="mb-4 flex w-full items-start gap-4 text-left" type="button" @click="library.openSource(source)">
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
                  :disabled="ui.loading"
                  @click="library.syncSource(source)"
                >
                  <RefreshCw :size="14" aria-hidden="true" />
                  Sync
                </button>
              </div>
            </article>

            <div
              v-if="library.sources.length === 0"
              class="rounded-lg border border-dashed border-outline bg-surface-container p-6 text-sm text-on-surface-variant"
            >
              No permanent sources configured.
            </div>
          </div>
        </section>

        <section
          v-if="library.activeReview"
          class="mb-8 rounded-xl border border-outline-variant bg-surface-container p-5 md:p-6"
        >
          <div class="mb-6 flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <div class="mb-2 flex flex-wrap items-center gap-3">
                <h3 class="text-xl font-bold text-on-surface">{{ library.activeReview.source.spotifyPlaylistName }}</h3>
                <StatusBadge :tone="sourceTone(library.activeReview.source)">
                  {{ library.activeReview.newTracks }} new
                </StatusBadge>
                <StatusBadge tone="muted">
                  {{ library.selectedTrackIds.length }} selected
                </StatusBadge>
              </div>
              <p class="text-sm text-on-surface-variant">
                {{ library.activeReview.totalTracks }} tracks tracked, {{ library.activeReview.readyTracks }} ready, {{ library.activeReview.conflictTracks }} conflicts.
              </p>
            </div>
            <div class="flex flex-wrap gap-2">
              <button
                class="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-xs font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                :disabled="ui.loading || !library.readyToApply || !system.rekordboxStatus?.mutationAllowed"
                @click="library.applySource()"
              >
                <UploadCloud :size="16" aria-hidden="true" />
                Import to Rekordbox
              </button>
            </div>
          </div>

          <div class="mb-6 grid grid-cols-2 gap-3 md:grid-cols-6">
            <div v-for="metric in [
              ['new', library.activeReview.newTracks],
              ['matched', library.activeReview.matchedTracks],
              ['ready', library.activeReview.readyTracks],
              ['imported', library.activeReview.importedTracks],
              ['conflict', library.activeReview.conflictTracks],
              ['removed', library.activeReview.removedTracks]
            ]" :key="metric[0]" class="rounded border border-outline-variant bg-surface-container-high p-3">
              <strong class="block text-2xl text-on-surface">{{ metric[1] }}</strong>
              <span class="text-xs text-on-surface-variant">{{ metric[0] }}</span>
            </div>
          </div>

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
          <form class="mb-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]" @submit.prevent="library.saveTagPlaylistMapping()">
            <label class="grid gap-2">
              <span class="text-sm font-bold text-on-surface">Existing MyTag</span>
              <input
                class="rounded border border-outline bg-surface-container px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
                v-model="library.mappingForm.tagName"
                list="mapping-tags"
                placeholder="MyTag"
              />
              <datalist id="mapping-tags">
                <option v-for="tagName in spotify.availableTagNames" :key="tagName" :value="tagName" />
              </datalist>
            </label>
            <label class="grid gap-2">
              <span class="text-sm font-bold text-on-surface">Spotify playlist</span>
              <select
                class="rounded border border-outline bg-surface-container px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
                v-model="library.mappingForm.spotifyPlaylistId"
                required
                @change="library.selectMappingPlaylist(($event.target as HTMLSelectElement).value)"
              >
                <option value="">Select playlist</option>
                <option v-for="playlist in spotify.playlists" :key="playlist.id" :value="playlist.id">
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
              v-for="mapping in library.tagPlaylistMappings"
              :key="mapping.id"
              class="rounded border border-outline-variant bg-surface-container p-3 text-sm"
            >
              <strong class="text-on-surface">{{ mapping.tagName }}</strong>
              <span class="text-on-surface-variant"> -> {{ mapping.spotifyPlaylistName }}</span>
            </div>
            <div v-if="library.tagPlaylistMappings.length === 0" class="text-sm text-on-surface-variant">
              No mappings configured.
            </div>
          </div>
        </section>

        <section>
          <div class="mb-4 flex items-center justify-between">
            <h3 class="text-lg font-bold text-on-surface">Available Spotify Playlists</h3>
            <span class="text-xs text-on-surface-variant">
              {{ filteredSpotifyPlaylists.length }} of {{ spotify.playlistTotal || spotify.playlists.length }}
            </span>
          </div>
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            <PlaylistCard
              v-for="playlist in filteredSpotifyPlaylists"
              :key="playlist.id"
              :playlist="playlist"
              @select="library.tagRuleForm.sourcePlaylistId = playlist.id; library.selectTagRulePlaylist(playlist.id);"
            />
          </div>
        </section>
      </div>
    </div>

    <aside
      v-if="library.selectedTrackIds.length > 0"
      class="hidden h-full w-[380px] shrink-0 flex-col border-l border-outline-variant bg-surface-container p-6 shadow-2xl xl:flex"
    >
      <div class="mb-6 flex items-center justify-between">
        <h2 class="text-lg font-bold text-on-surface">Batch Tagging</h2>
        <StatusBadge tone="active">{{ library.selectedTrackIds.length }} selected</StatusBadge>
      </div>

      <div class="mb-6 rounded border border-primary/20 bg-primary/5 p-4">
        <div class="mb-1 text-[10px] font-bold uppercase text-primary">Selected source</div>
        <div class="text-xl font-bold text-on-surface">
          {{ library.activeReview?.source.spotifyPlaylistName ?? "My Library" }}
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
          <option v-for="tagName in spotify.availableTagNames" :key="tagName" :value="tagName" />
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

    <!-- Deezer Search Panel — slides in from right, takes priority over batch tagging -->
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
