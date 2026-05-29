<script setup lang="ts">
import { computed, ref } from "vue";
import { AreaChart, Disc3, Link2, ListPlus, Plus, Sparkles } from "@lucide/vue";
import { useEventsStore } from "../stores/events";
import { useUiStore } from "../stores/ui";

// Centered "create" screen shown in the main area when no event is selected.
const ui = useUiStore();
const events = useEventsStore();

const NEW_EVENT = "new" as const;

const emptyEventName = ref("");
const trackUrl = ref("");
const target = ref<string>(NEW_EVENT);
const newEventName = ref("");

const isNewEvent = computed(() => target.value === NEW_EVENT);

async function createEmptyEvent(): Promise<void> {
  const created = await events.createManualEvent(emptyEventName.value);
  if (created) emptyEventName.value = "";
}

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
</script>

<template>
  <div class="flex min-w-0 flex-1 flex-col overflow-y-auto">
    <div class="mx-auto w-full max-w-3xl p-8">
      <div class="mb-8 text-center">
        <h2 class="text-2xl font-bold text-on-surface">Create an event</h2>
        <p class="mt-1 text-sm text-on-surface-variant">
          Import a whole Spotify playlist, start an empty event, or add a single track by link.
        </p>
      </div>

      <!-- Two creation modes -->
      <div class="grid gap-4 md:grid-cols-2">
        <!-- From a Spotify playlist -->
        <form
          class="flex flex-col gap-3 rounded-xl border border-outline-variant bg-surface-container p-5"
          @submit.prevent="events.analyzeImport()"
        >
          <div class="flex items-center gap-2">
            <AreaChart class="text-primary" :size="18" aria-hidden="true" />
            <h3 class="text-sm font-bold text-on-surface">From a Spotify playlist</h3>
          </div>
          <div class="relative">
            <Link2 class="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant" :size="14" aria-hidden="true" />
            <input
              class="w-full rounded border border-outline bg-surface-container-high py-2 pl-8 pr-3 text-sm text-on-surface focus:border-primary focus:outline-none"
              v-model="events.importForm.playlistUrl"
              type="url"
              placeholder="Spotify playlist URL"
              required
            />
          </div>
          <input
            class="w-full rounded border border-outline bg-surface-container-high px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
            v-model="events.importForm.eventName"
            type="text"
            placeholder="Event name"
            required
          />
          <button
            class="mt-auto inline-flex items-center justify-center gap-2 rounded bg-primary px-4 py-2 text-sm font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-60"
            type="submit"
            :disabled="ui.loading"
          >
            <AreaChart :size="15" aria-hidden="true" />
            Analyze playlist
          </button>
        </form>

        <!-- Empty event -->
        <form
          class="flex flex-col gap-3 rounded-xl border border-outline-variant bg-surface-container p-5"
          @submit.prevent="createEmptyEvent()"
        >
          <div class="flex items-center gap-2">
            <Disc3 class="text-secondary" :size="18" aria-hidden="true" />
            <h3 class="text-sm font-bold text-on-surface">Empty event</h3>
          </div>
          <p class="text-xs text-on-surface-variant">
            Start blank and add tracks one by one.
          </p>
          <input
            class="w-full rounded border border-outline bg-surface-container-high px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
            v-model="emptyEventName"
            type="text"
            placeholder="Event name"
            required
          />
          <button
            class="mt-auto inline-flex items-center justify-center gap-2 rounded border border-outline bg-surface-container-high px-4 py-2 text-sm font-bold text-on-surface transition-colors hover:border-primary disabled:cursor-not-allowed disabled:opacity-60"
            type="submit"
            :disabled="ui.loading"
          >
            <Plus :size="15" aria-hidden="true" />
            Create empty event
          </button>
        </form>
      </div>

      <!-- Add a single track -->
      <div class="mt-6 rounded-xl border border-outline-variant bg-surface-container p-5">
        <div class="mb-3 flex items-center gap-2">
          <ListPlus class="text-primary" :size="18" aria-hidden="true" />
          <h3 class="text-sm font-bold text-on-surface">Add a track by Spotify link</h3>
        </div>
        <form class="flex flex-col gap-3 md:flex-row md:items-center" @submit.prevent="addTrack()">
          <div class="relative min-w-0 flex-1">
            <Link2 class="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant" :size="14" aria-hidden="true" />
            <input
              class="w-full rounded border border-outline bg-surface-container-high py-2 pl-8 pr-3 text-sm text-on-surface focus:border-primary focus:outline-none"
              v-model="trackUrl"
              type="text"
              placeholder="Spotify track link / URI"
              required
            />
          </div>
          <select
            class="rounded border border-outline bg-surface-container-high px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
            v-model="target"
          >
            <option :value="NEW_EVENT">＋ New event…</option>
            <option v-for="event in events.summaries" :key="event.id" :value="String(event.id)">
              {{ event.eventName }}
            </option>
          </select>
          <input
            v-if="isNewEvent"
            class="rounded border border-outline bg-surface-container-high px-3 py-2 text-sm text-on-surface focus:border-primary focus:outline-none"
            v-model="newEventName"
            type="text"
            placeholder="New event name"
            :required="isNewEvent"
          />
          <button
            class="inline-flex items-center justify-center gap-2 rounded bg-primary px-4 py-2 text-sm font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-60"
            type="submit"
            :disabled="ui.loading"
          >
            <Plus :size="15" aria-hidden="true" />
            Add
          </button>
        </form>
      </div>

      <p class="mt-6 flex items-center justify-center gap-2 text-xs text-on-surface-variant">
        <Sparkles :size="13" aria-hidden="true" />
        Missing tracks are downloaded automatically — you'll only be warned if one isn't on Deemix.
      </p>
    </div>
  </div>
</template>
