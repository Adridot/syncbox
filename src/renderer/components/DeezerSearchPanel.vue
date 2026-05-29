<script setup lang="ts">
import { Disc3, Download, Loader2, Pause, Play, Search, X } from "@lucide/vue";
import { onUnmounted, ref, watch } from "vue";
import type { DeezerSearchResult, TrackReview } from "../lib/api";

const props = defineProps<{
  track: TrackReview;
  query: string;
  loading: boolean;
  results: DeezerSearchResult[];
}>();

const emit = defineEmits<{
  "update:query": [value: string];
  search: [];
  queue: [deezerTrackId: string];
  close: [];
}>();

const audioEl = ref<HTMLAudioElement | null>(null);
const playingId = ref<string | null>(null);

function togglePreview(result: DeezerSearchResult): void {
  const audio = audioEl.value;
  if (!audio || !result.previewUrl) return;
  if (playingId.value === result.id) {
    audio.pause();
    playingId.value = null;
    return;
  }
  audio.src = result.previewUrl;
  audio.play().then(() => {
    playingId.value = result.id;
  }).catch(() => {
    playingId.value = null;
  });
}

function stopPreview(): void {
  const audio = audioEl.value;
  if (audio) {
    audio.pause();
    audio.currentTime = 0;
  }
  playingId.value = null;
}

// Stop playback when the panel switches to another track or closes
watch(() => props.track?.spotifyTrackId, () => stopPreview());
onUnmounted(() => stopPreview());
</script>

<template>
  <aside class="flex h-full w-[420px] shrink-0 flex-col border-l border-outline-variant bg-surface-container shadow-2xl">
    <audio ref="audioEl" class="hidden" @ended="playingId = null" />
    <div class="flex items-center justify-between border-b border-outline-variant p-4">
      <div>
        <h2 class="text-base font-bold text-on-surface">Search Deezer</h2>
        <p class="mt-0.5 max-w-[280px] truncate text-xs text-on-surface-variant">
          {{ track.title }} — {{ track.artists.join(", ") }}
        </p>
      </div>
      <button
        class="grid h-8 w-8 place-items-center rounded border border-outline bg-surface text-on-surface-variant hover:border-primary"
        type="button"
        @click="emit('close')"
      >
        <X :size="16" aria-hidden="true" />
      </button>
    </div>

    <div class="border-b border-outline-variant p-4">
      <form class="flex gap-2" @submit.prevent="emit('search')">
        <input
          class="min-w-0 flex-1 rounded border border-outline bg-surface-container-high px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
          :value="query"
          type="text"
          placeholder="Search query…"
          @input="emit('update:query', ($event.target as HTMLInputElement).value)"
        />
        <button
          class="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
          type="submit"
          :disabled="loading"
        >
          <Loader2 v-if="loading" :size="15" class="animate-spin" aria-hidden="true" />
          <Search v-else :size="15" aria-hidden="true" />
          Search
        </button>
      </form>
    </div>

    <div class="flex-1 overflow-y-auto p-4">
      <div
        v-if="results.length === 0 && !loading"
        class="py-8 text-center text-sm text-on-surface-variant"
      >
        <p v-if="query">No results. Try a different query.</p>
        <p v-else>Enter a search query and press Search.</p>
      </div>

      <div class="flex flex-col gap-3">
        <div
          v-for="result in results"
          :key="result.id"
          class="rounded-lg border border-outline-variant bg-surface p-3"
        >
          <div class="flex items-start gap-3">
            <!-- Cover with play/pause overlay -->
            <div class="relative h-12 w-12 shrink-0 overflow-hidden rounded bg-surface-container-high">
              <img
                v-if="result.coverUrl"
                :src="result.coverUrl"
                :alt="result.album ?? result.title"
                class="h-full w-full object-cover"
              />
              <div v-else class="grid h-full w-full place-items-center text-on-surface-variant">
                <Disc3 :size="20" aria-hidden="true" />
              </div>
              <button
                v-if="result.previewUrl"
                class="absolute inset-0 grid place-items-center bg-black/40 text-white opacity-0 transition-opacity hover:opacity-100"
                :class="{ 'opacity-100': playingId === result.id }"
                type="button"
                :title="playingId === result.id ? 'Pause preview' : 'Play preview'"
                @click="togglePreview(result)"
              >
                <Pause v-if="playingId === result.id" :size="18" aria-hidden="true" />
                <Play v-else :size="18" aria-hidden="true" />
              </button>
            </div>

            <div class="min-w-0 flex-1">
              <strong class="block truncate text-sm text-on-surface">{{ result.title }}</strong>
              <span class="block truncate text-xs text-on-surface-variant">{{ result.artist }}</span>
              <span v-if="result.album" class="block truncate text-[11px] text-on-surface-variant">
                {{ result.album }}
              </span>
              <span v-if="result.durationMs" class="text-[10px] text-on-surface-variant">
                {{ Math.floor(result.durationMs / 60000) }}:{{ String(Math.floor((result.durationMs % 60000) / 1000)).padStart(2, "0") }}
              </span>
            </div>

            <button
              class="shrink-0 inline-flex items-center gap-1.5 rounded bg-primary px-3 py-1.5 text-xs font-bold text-white shadow-[0_2px_8px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02] disabled:opacity-60"
              type="button"
              @click="emit('queue', result.id)"
            >
              <Download :size="13" aria-hidden="true" />
              Download
            </button>
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>
