<script setup lang="ts">
import { Library, Plus, Trash2, X } from "@lucide/vue";
import { computed, onMounted, onUnmounted, ref } from "vue";
import PlaylistCard from "./PlaylistCard.vue";
import { useLibraryStore } from "../stores/library";
import { useSpotifyStore } from "../stores/spotify";

const emit = defineEmits<{ close: [] }>();

const library = useLibraryStore();
const spotify = useSpotifyStore();

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
        <h2 class="text-base font-bold text-on-surface">{{ $t("setup.title") }}</h2>
        <button
          type="button"
          class="ml-auto rounded p-1 text-on-surface-variant hover:text-on-surface"
          :aria-label="$t('common.close')"
          @click="emit('close')"
        >
          <X :size="20" aria-hidden="true" />
        </button>
      </header>

      <div class="overflow-y-auto p-5">
        <!-- Follow a playlist -->
        <div class="flex flex-col gap-6">
          <form
            class="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
            @submit.prevent="library.saveTagRule()"
          >
            <label class="grid gap-2">
              <span class="text-sm font-bold text-on-surface">{{ $t("setup.spotifySource") }}</span>
              <select
                class="rounded border border-outline bg-surface-container-high px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
                v-model="library.tagRuleForm.sourcePlaylistId"
                required
                @change="library.selectTagRulePlaylist(($event.target as HTMLSelectElement).value)"
              >
                <option value="">{{ $t("setup.selectPlaylist") }}</option>
                <option v-for="playlist in availablePlaylists" :key="playlist.id" :value="playlist.id">
                  {{ $t("setup.playlistOption", { name: playlist.name, count: playlist.trackCount }) }}
                </option>
              </select>
            </label>

            <label class="grid gap-2">
              <span class="text-sm font-bold text-on-surface">
                {{ $t("setup.defaultTags") }} <span class="font-normal text-on-surface-variant">{{ $t("setup.optional") }}</span>
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
                    :placeholder="$t('setup.existingTag')"
                    @input="library.tagRuleTagInput = ($event.target as HTMLInputElement).value"
                    @change="library.addTagRuleTag()"
                    @keydown.enter.prevent="library.addTagRuleTag()"
                  />
                  <button
                    class="rounded border border-outline bg-surface px-3 py-2 text-xs font-bold text-on-surface hover:border-primary"
                    type="button"
                    @click="library.addTagRuleTag()"
                  >
                    {{ $t("common.add") }}
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
              <span class="inline-flex items-center gap-1.5"><Plus :size="15" aria-hidden="true" /> {{ $t("setup.follow") }}</span>
            </button>
          </form>

          <div v-if="library.sources.length > 0">
            <h3 class="mb-3 text-sm font-bold text-on-surface">
              {{ $t("setup.followedSources") }}
              <span class="font-normal text-on-surface-variant">({{ library.sources.length }})</span>
            </h3>
            <ul class="flex flex-col gap-1.5">
              <li
                v-for="source in library.sources"
                :key="source.id"
                class="flex items-center gap-3 rounded-lg border border-outline-variant bg-surface px-3 py-2"
              >
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
                    {{ $t("library.tracksCount", { count: source.trackCount }) }}<template v-if="source.tags.length"> · {{ source.tags.join(", ") }}</template>
                  </span>
                </span>
                <button
                  type="button"
                  class="inline-flex shrink-0 items-center gap-1.5 rounded border border-outline px-2.5 py-1.5 text-xs font-semibold text-on-surface-variant hover:border-error hover:text-error"
                  :title="$t('setup.stopFollowing', { name: source.spotifyPlaylistName })"
                  @click="library.deleteSource(source)"
                >
                  <Trash2 :size="14" aria-hidden="true" /> {{ $t("common.remove") }}
                </button>
              </li>
            </ul>
          </div>

          <div>
            <div class="mb-3 flex items-center justify-between gap-3">
              <h3 class="text-sm font-bold text-on-surface">{{ $t("setup.availablePlaylists") }}</h3>
              <input
                v-model="playlistSearch"
                type="search"
                :placeholder="$t('setup.searchPlaylists')"
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
              {{ $t("setup.allFollowed") }}
            </p>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>
