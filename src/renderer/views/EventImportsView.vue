<script setup lang="ts">
import { AreaChart, FileAudio, Link2 } from "@lucide/vue";
import EventCard from "../components/EventCard.vue";
import EventWorkspace from "../components/EventWorkspace.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { useEventsStore } from "../stores/events";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
const events = useEventsStore();

async function openDesktopPath(path: string): Promise<void> {
  if (!window.desktop) {
    ui.setMessage("success", `Open this path in Finder: ${path}`);
    return;
  }
  try {
    await window.desktop.openPath(path);
  } catch (error) {
    ui.setMessage("error", error instanceof Error ? error.message : String(error));
  }
}
</script>

<template>
  <div class="flex h-full overflow-hidden">
    <!-- Left sidebar: event list -->
    <aside class="flex h-full w-72 shrink-0 flex-col border-r border-outline-variant bg-background">
      <div class="border-b border-outline-variant p-4">
        <h2 class="mb-3 text-sm font-bold uppercase tracking-wider text-on-surface-variant">
          Event Imports
        </h2>
        <form class="flex flex-col gap-2" @submit.prevent="events.analyzeImport()">
          <div class="relative">
            <Link2
              class="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant"
              :size="14"
              aria-hidden="true"
            />
            <input
              class="w-full rounded border border-outline bg-surface-container py-2 pl-8 pr-3 text-xs text-on-surface transition-colors focus:border-primary focus:outline-none"
              v-model="events.importForm.playlistUrl"
              type="url"
              placeholder="Spotify playlist URL"
              required
            />
          </div>
          <input
            class="rounded border border-outline bg-surface-container px-3 py-2 text-xs text-on-surface transition-colors focus:border-primary focus:outline-none"
            v-model="events.importForm.eventName"
            type="text"
            placeholder="Event name"
            required
          />
          <button
            class="inline-flex items-center justify-center gap-2 rounded bg-primary px-4 py-2 text-xs font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-60"
            type="submit"
            :disabled="ui.loading"
          >
            <AreaChart :size="15" aria-hidden="true" />
            Analyze Import
          </button>
        </form>
      </div>

      <div class="flex-1 overflow-y-auto p-3">
        <div class="mb-2 flex items-center justify-between px-1">
          <span class="text-xs font-bold text-on-surface-variant">Temporary Playlists</span>
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
            No event imports yet.
          </div>
        </div>
      </div>

      <!-- Live Import section at bottom -->
      <div class="border-t border-outline-variant p-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <FileAudio class="text-secondary" :size="15" aria-hidden="true" />
            <span class="text-xs font-bold text-on-surface">Live Import (M3U8)</span>
          </div>
          <button
            class="rounded border border-outline bg-surface px-2.5 py-1 text-[11px] font-bold text-on-surface transition-colors hover:border-primary"
            type="button"
            @click="events.createLiveImportPackage()"
          >
            Prepare
          </button>
        </div>
        <div v-if="events.liveImportPackage" class="mt-2 space-y-2 text-[11px] text-on-surface-variant">
          <p class="break-all">{{ events.liveImportPackage.audioDir }}</p>
          <div class="flex gap-2">
            <button
              class="rounded border border-outline bg-surface-container px-2 py-1 font-bold text-on-surface transition-colors hover:border-primary"
              type="button"
              @click="openDesktopPath(events.liveImportPackage.audioDir)"
            >
              Open Audio
            </button>
            <button
              class="rounded border border-outline bg-surface-container px-2 py-1 font-bold text-on-surface transition-colors hover:border-primary"
              type="button"
              @click="openDesktopPath(events.liveImportPackage.playlistPath)"
            >
              Open M3U8
            </button>
          </div>
        </div>
      </div>
    </aside>

    <!-- Main content: shared active-event workspace + Deezer panel -->
    <EventWorkspace />
  </div>
</template>
