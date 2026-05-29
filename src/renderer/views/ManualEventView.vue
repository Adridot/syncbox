<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { Link2, ListPlus, Plus } from "@lucide/vue";
import EventCard from "../components/EventCard.vue";
import EventWorkspace from "../components/EventWorkspace.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { useEventsStore } from "../stores/events";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
const events = useEventsStore();

const NEW_EVENT = "new" as const;

const trackUrl = ref("");
// Selected target event id (as a string) or NEW_EVENT. Kept in sync with the
// active event so opening/creating one preselects it, while still letting the
// user pick a different target in the dropdown.
const target = ref<string>(NEW_EVENT);
const newEventName = ref("");
const emptyEventName = ref("");

watch(
  () => events.activeEvent?.id,
  (id) => {
    target.value = id != null ? String(id) : NEW_EVENT;
  },
  { immediate: true }
);

const isNewEvent = computed(() => target.value === NEW_EVENT);

async function addTrack(): Promise<void> {
  await events.addTrackToEvent({
    url: trackUrl.value,
    targetEventId: isNewEvent.value ? null : Number(target.value),
    newEventName: isNewEvent.value ? newEventName.value : undefined,
  });
  if (!ui.errorMessage) {
    trackUrl.value = "";
    newEventName.value = "";
  }
}

async function createEmptyEvent(): Promise<void> {
  const created = await events.createManualEvent(emptyEventName.value);
  if (created) emptyEventName.value = "";
}
</script>

<template>
  <div class="flex h-full overflow-hidden">
    <!-- Left sidebar: add-by-link + create + event list -->
    <aside class="flex h-full w-72 shrink-0 flex-col border-r border-outline-variant bg-background">
      <div class="border-b border-outline-variant p-4">
        <h2 class="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-on-surface-variant">
          <ListPlus :size="15" aria-hidden="true" />
          Add a Spotify track
        </h2>
        <form class="flex flex-col gap-2" @submit.prevent="addTrack()">
          <div class="relative">
            <Link2
              class="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant"
              :size="14"
              aria-hidden="true"
            />
            <input
              class="w-full rounded border border-outline bg-surface-container py-2 pl-8 pr-3 text-xs text-on-surface transition-colors focus:border-primary focus:outline-none"
              v-model="trackUrl"
              type="text"
              placeholder="Spotify track link / URI"
              required
            />
          </div>

          <select
            class="rounded border border-outline bg-surface-container px-3 py-2 text-xs text-on-surface transition-colors focus:border-primary focus:outline-none"
            v-model="target"
          >
            <option :value="NEW_EVENT">＋ New event…</option>
            <option v-for="event in events.summaries" :key="event.id" :value="String(event.id)">
              {{ event.eventName }}
            </option>
          </select>

          <input
            v-if="isNewEvent"
            class="rounded border border-outline bg-surface-container px-3 py-2 text-xs text-on-surface transition-colors focus:border-primary focus:outline-none"
            v-model="newEventName"
            type="text"
            placeholder="New event name"
            :required="isNewEvent"
          />

          <button
            class="inline-flex items-center justify-center gap-2 rounded bg-primary px-4 py-2 text-xs font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-60"
            type="submit"
            :disabled="ui.loading"
          >
            <Plus :size="15" aria-hidden="true" />
            Add Track
          </button>
        </form>

        <!-- Create an empty event (no track) -->
        <form class="mt-3 flex gap-2 border-t border-outline-variant pt-3" @submit.prevent="createEmptyEvent()">
          <input
            class="min-w-0 flex-1 rounded border border-outline bg-surface-container px-3 py-2 text-xs text-on-surface transition-colors focus:border-primary focus:outline-none"
            v-model="emptyEventName"
            type="text"
            placeholder="Create empty event"
            required
          />
          <button
            class="shrink-0 rounded border border-outline bg-surface px-2.5 py-1 text-[11px] font-bold text-on-surface transition-colors hover:border-primary disabled:opacity-60"
            type="submit"
            :disabled="ui.loading"
          >
            Create
          </button>
        </form>
      </div>

      <div class="flex-1 overflow-y-auto p-3">
        <div class="mb-2 flex items-center justify-between px-1">
          <span class="text-xs font-bold text-on-surface-variant">Events</span>
          <StatusBadge tone="active">{{ events.summaries.length }}</StatusBadge>
        </div>
        <div class="flex flex-col gap-2">
          <EventCard
            v-for="event in events.summaries"
            :key="event.id"
            :event="event"
            :active="events.activeEvent?.id === event.id"
            @open="events.openEvent(event)"
          />
          <div
            v-if="events.summaries.length === 0"
            class="rounded-lg border border-dashed border-outline bg-surface-container p-4 text-xs text-on-surface-variant"
          >
            No events yet. Create one or add a track to a new event.
          </div>
        </div>
      </div>
    </aside>

    <!-- Main content: shared active-event workspace + Deezer panel -->
    <EventWorkspace />
  </div>
</template>
