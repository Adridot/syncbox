<script setup lang="ts">
import { CalendarDays } from "@lucide/vue";
import type { EventSummary } from "../lib/api";
import StatusBadge from "./StatusBadge.vue";

defineProps<{
  event: EventSummary;
  active?: boolean;
}>();

defineEmits<{
  open: [event: EventSummary];
}>();
</script>

<template>
  <button
    class="group flex h-full flex-col rounded-lg border p-4 text-left transition-colors"
    :class="
      active
        ? 'border-primary bg-primary/5 shadow-[0_0_15px_rgba(0,112,255,0.08)]'
        : 'border-outline-variant bg-surface-container-high hover:border-primary'
    "
    type="button"
    @click="$emit('open', event)"
  >
    <div class="mb-4 flex items-start gap-4">
      <div
        class="grid h-14 w-14 shrink-0 place-items-center rounded border border-outline bg-surface-container"
      >
        <CalendarDays class="text-primary" :size="24" aria-hidden="true" />
      </div>
      <div class="min-w-0">
        <h3 class="truncate font-bold text-on-surface group-hover:text-primary">
          {{ event.eventName }}
        </h3>
        <p class="mt-1 font-mono text-xs text-on-surface-variant">
          {{ event.spotifyPlaylistName }}
        </p>
      </div>
    </div>
    <div class="mt-auto flex items-center justify-between border-t border-outline-variant pt-3">
      <span class="font-mono text-xs text-on-surface-variant">
        {{ event.readyTracks }}/{{ event.totalTracks }} ready
      </span>
      <StatusBadge :tone="event.status === 'applied' ? 'ok' : 'active'">
        {{ event.status }}
      </StatusBadge>
    </div>
  </button>
</template>

