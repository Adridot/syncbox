<script setup lang="ts">
import { ListMusic } from "@lucide/vue";
import type { SpotifyPlaylistSummary } from "../lib/api";

defineProps<{
  playlist: SpotifyPlaylistSummary;
  compact?: boolean;
}>();

defineEmits<{
  select: [playlist: SpotifyPlaylistSummary];
}>();
</script>

<template>
  <article
    class="group flex h-full flex-col rounded-lg border border-outline-variant bg-surface-container-high transition-all hover:border-primary"
    :class="compact ? 'p-2.5' : 'p-4'"
  >
    <div
      class="relative overflow-hidden rounded bg-surface-container aspect-square w-full"
      :class="compact ? 'mb-2' : 'mb-4'"
    >
      <img
        v-if="playlist.imageUrl"
        class="h-full w-full object-cover"
        :src="playlist.imageUrl"
        :alt="`${playlist.name} cover`"
      />
      <div v-else class="grid h-full w-full place-items-center text-on-surface-variant">
        <ListMusic :size="compact ? 24 : 40" aria-hidden="true" />
      </div>
      <div
        v-if="playlist.trackCount > 0"
        class="absolute right-1.5 top-1.5 rounded-full bg-secondary px-1.5 py-0.5 text-[10px] font-bold text-black shadow-sm"
      >
        {{ playlist.trackCount }}
      </div>
    </div>

    <div class="flex flex-1 flex-col">
      <h3
        class="truncate font-bold text-on-surface transition-colors group-hover:text-primary"
        :class="compact ? 'text-sm' : ''"
      >
        {{ playlist.name }}
      </h3>
      <p class="mt-0.5 truncate text-xs text-on-surface-variant">
        {{ playlist.owner }} - {{ playlist.public === false ? $t("playlist.private") : $t("playlist.spotify") }}
      </p>
      <template v-if="!compact">
        <div class="mt-auto flex items-center justify-between border-t border-outline-variant pt-3">
          <span class="font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
            {{ $t("playlist.playlist") }}
          </span>
          <button
            class="rounded border border-outline bg-surface px-3 py-1.5 text-xs font-bold text-on-surface transition-colors hover:border-primary"
            type="button"
            @click="$emit('select', playlist)"
          >
            {{ $t("playlist.select") }}
          </button>
        </div>
      </template>
      <button
        v-else
        class="mt-2 w-full rounded border border-outline bg-surface px-2 py-1 text-xs font-bold text-on-surface transition-colors hover:border-primary"
        type="button"
        @click="$emit('select', playlist)"
      >
        {{ $t("playlist.select") }}
      </button>
    </div>
  </article>
</template>

