<script setup lang="ts">
import { Plus, Tags, X } from "@lucide/vue";
import { computed, onMounted, onUnmounted, ref } from "vue";
import PlaylistCard from "./PlaylistCard.vue";
import { useLibraryStore } from "../stores/library";
import { useSpotifyStore } from "../stores/spotify";

const props = defineProps<{ initialTab?: "follow" | "mappings" }>();
const emit = defineEmits<{ close: [] }>();

const library = useLibraryStore();
const spotify = useSpotifyStore();

const tab = ref<"follow" | "mappings">(props.initialTab ?? "follow");
const playlistSearch = ref("");

const availablePlaylists = computed(() => {
  const followed = new Set(library.sources.map((s) => s.spotifyPlaylistId));
  const query = playlistSearch.value.trim().toLowerCase();
  return spotify.playlists.filter(
    (p) => !followed.has(p.id) && (!query || p.name.toLowerCase().includes(query))
  );
});

function onKey(event: KeyboardEvent): void {
  if (event.key === "Escape") emit("close");
}
onMounted(() => window.addEventListener("keydown", onKey));
onUnmounted(() => window.removeEventListener("keydown", onKey));

const tabClass = (active: boolean) =>
  active
    ? "bg-surface-container-high text-on-surface"
    : "text-on-surface-variant hover:text-on-surface";
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
    @click.self="emit('close')"
  >
    <div
      class="flex max-h-[86vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-outline-variant bg-surface-container shadow-2xl"
    >
      <header class="flex items-center gap-3 border-b border-outline-variant px-5 py-3">
        <h2 class="text-base font-bold text-on-surface">Manage sources</h2>
        <div class="ml-auto flex gap-1 rounded-lg bg-surface p-1">
          <button
            type="button"
            class="rounded px-3 py-1 text-sm font-semibold transition-colors"
            :class="tabClass(tab === 'follow')"
            @click="tab = 'follow'"
          >
            Follow a playlist
          </button>
          <button
            type="button"
            class="rounded px-3 py-1 text-sm font-semibold transition-colors"
            :class="tabClass(tab === 'mappings')"
            @click="tab = 'mappings'"
          >
            Tag mappings
          </button>
        </div>
        <button
          type="button"
          class="rounded p-1 text-on-surface-variant hover:text-on-surface"
          aria-label="Close"
          @click="emit('close')"
        >
          <X :size="20" aria-hidden="true" />
        </button>
      </header>

      <div class="overflow-y-auto p-5">
        <!-- Follow a playlist -->
        <div v-if="tab === 'follow'" class="flex flex-col gap-6">
          <form
            class="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
            @submit.prevent="library.saveTagRule()"
          >
            <label class="grid gap-2">
              <span class="text-sm font-bold text-on-surface">Spotify source</span>
              <select
                class="rounded border border-outline bg-surface-container-high px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
                v-model="library.tagRuleForm.sourcePlaylistId"
                required
                @change="library.selectTagRulePlaylist(($event.target as HTMLSelectElement).value)"
              >
                <option value="">Select a Spotify playlist</option>
                <option v-for="playlist in availablePlaylists" :key="playlist.id" :value="playlist.id">
                  {{ playlist.name }} — {{ playlist.trackCount }} tracks
                </option>
              </select>
            </label>

            <label class="grid gap-2">
              <span class="text-sm font-bold text-on-surface">
                Default MyTags <span class="font-normal text-on-surface-variant">(optional)</span>
              </span>
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
                    class="rounded border border-outline bg-surface-container-high px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
                    :value="library.tagRuleTagInput"
                    list="setup-source-tags"
                    placeholder="Existing Rekordbox MyTag"
                    @input="library.tagRuleTagInput = ($event.target as HTMLInputElement).value"
                    @change="library.addTagRuleTag()"
                    @keydown.enter.prevent="library.addTagRuleTag()"
                  />
                  <button
                    class="rounded border border-outline bg-surface px-3 py-2 text-xs font-bold text-on-surface hover:border-primary"
                    type="button"
                    @click="library.addTagRuleTag()"
                  >
                    Add
                  </button>
                </div>
                <datalist id="setup-source-tags">
                  <option v-for="tagName in spotify.availableTagNames" :key="tagName" :value="tagName" />
                </datalist>
              </div>
            </label>

            <button
              class="self-end rounded bg-primary px-5 py-2 text-sm font-bold text-white hover:scale-[1.02]"
              type="submit"
            >
              <span class="inline-flex items-center gap-1.5"><Plus :size="15" aria-hidden="true" /> Follow</span>
            </button>
          </form>

          <div>
            <div class="mb-3 flex items-center justify-between gap-3">
              <h3 class="text-sm font-bold text-on-surface">Available Spotify playlists</h3>
              <input
                v-model="playlistSearch"
                type="search"
                placeholder="Search playlists…"
                class="w-48 rounded border border-outline bg-surface-container-high px-3 py-1.5 text-xs text-on-surface focus:border-primary focus:outline-none"
              />
            </div>
            <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              <PlaylistCard
                v-for="playlist in availablePlaylists"
                :key="playlist.id"
                :playlist="playlist"
                compact
                @select="
                  library.tagRuleForm.sourcePlaylistId = playlist.id;
                  library.selectTagRulePlaylist(playlist.id);
                "
              />
            </div>
            <p
              v-if="availablePlaylists.length === 0"
              class="py-6 text-center text-sm text-on-surface-variant"
            >
              All your playlists are already followed (or none loaded yet).
            </p>
          </div>
        </div>

        <!-- Tag → Spotify mappings -->
        <div v-else class="flex flex-col gap-5">
          <div class="flex items-center gap-2">
            <Tags class="text-secondary" :size="18" aria-hidden="true" />
            <p class="text-sm text-on-surface-variant">
              Permanent tracks carrying a MyTag are added to the mapped Spotify playlist.
            </p>
          </div>
          <form
            class="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
            @submit.prevent="library.saveTagPlaylistMapping()"
          >
            <label class="grid gap-2">
              <span class="text-sm font-bold text-on-surface">Existing MyTag</span>
              <input
                class="rounded border border-outline bg-surface-container-high px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
                v-model="library.mappingForm.tagName"
                list="setup-mapping-tags"
                placeholder="MyTag"
              />
              <datalist id="setup-mapping-tags">
                <option v-for="tagName in spotify.availableTagNames" :key="tagName" :value="tagName" />
              </datalist>
            </label>
            <label class="grid gap-2">
              <span class="text-sm font-bold text-on-surface">Spotify playlist</span>
              <select
                class="rounded border border-outline bg-surface-container-high px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
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
              Save
            </button>
          </form>
          <div class="grid gap-2 md:grid-cols-2">
            <div
              v-for="mapping in library.tagPlaylistMappings"
              :key="mapping.id"
              class="rounded border border-outline-variant bg-surface-container-high p-3 text-sm"
            >
              <strong class="text-on-surface">{{ mapping.tagName }}</strong>
              <span class="text-on-surface-variant"> → {{ mapping.spotifyPlaylistName }}</span>
            </div>
            <div v-if="library.tagPlaylistMappings.length === 0" class="text-sm text-on-surface-variant">
              No mappings configured.
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
