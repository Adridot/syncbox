<script setup lang="ts">
import { FileAudio, Plus } from "@lucide/vue";
import EventCard from "../components/EventCard.vue";
import EventCreatePanel from "../components/EventCreatePanel.vue";
import EventWorkspace from "../components/EventWorkspace.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { t } from "../i18n";
import { useEventsStore } from "../stores/events";
import { useUiStore } from "../stores/ui";

// Single "Events" tab. Sidebar = event list (master); the main area is the
// active event's workspace, or the creation screen when nothing is selected.
const ui = useUiStore();
const events = useEventsStore();

async function openDesktopPath(path: string): Promise<void> {
  if (!window.desktop) {
    ui.setMessage("success", t("events.openInFinder", { path }));
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
    <!-- Left sidebar: event list + Live Import -->
    <aside class="flex h-full w-64 shrink-0 flex-col border-r border-outline-variant bg-background">
      <div class="border-b border-outline-variant p-4">
        <button
          class="inline-flex w-full items-center justify-center gap-2 rounded bg-primary px-4 py-2 text-sm font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02]"
          type="button"
          @click="events.closeActiveEvent()"
        >
          <Plus :size="15" aria-hidden="true" />
          {{ $t("events.newEvent") }}
        </button>
      </div>

      <div class="flex-1 overflow-y-auto p-3">
        <div class="mb-2 flex items-center justify-between px-1">
          <span class="text-xs font-bold uppercase tracking-wider text-on-surface-variant">{{ $t("events.title") }}</span>
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
            {{ $t("events.noEvents") }}
          </div>
        </div>
      </div>

      <!-- Live Import (M3U8) -->
      <div class="border-t border-outline-variant p-4">
        <div class="mb-2 flex items-center gap-2">
          <FileAudio class="text-secondary" :size="15" aria-hidden="true" />
          <span class="text-xs font-bold text-on-surface">{{ $t("events.liveImport") }}</span>
        </div>
        <p class="mb-2 text-[11px] text-on-surface-variant">
          {{ $t("events.liveImportHint") }}
        </p>
        <!-- An event is open: target it directly, no name to retype. -->
        <div v-if="events.activeEvent" class="flex items-center gap-2">
          <span class="min-w-0 flex-1 truncate text-[11px] text-on-surface">
            {{ $t("events.liveImportFor", { name: events.activeEvent.eventName }) }}
          </span>
          <button
            class="shrink-0 rounded border border-outline bg-surface px-2.5 py-1 text-[11px] font-bold text-on-surface transition-colors hover:border-primary"
            type="button"
            @click="events.createLiveImportPackage()"
          >
            {{ $t("common.prepare") }}
          </button>
        </div>
        <!-- No event open: standalone live import needs a name. -->
        <div v-else class="flex gap-2">
          <input
            class="min-w-0 flex-1 rounded border border-outline bg-surface-container-high px-2.5 py-1 text-[11px] text-on-surface focus:border-primary focus:outline-none"
            v-model="events.importForm.eventName"
            type="text"
            :placeholder="$t('events.eventName')"
            @keyup.enter="events.createLiveImportPackage()"
          />
          <button
            class="shrink-0 rounded border border-outline bg-surface px-2.5 py-1 text-[11px] font-bold text-on-surface transition-colors hover:border-primary disabled:cursor-not-allowed disabled:opacity-50"
            type="button"
            :disabled="!events.importForm.eventName.trim()"
            @click="events.createLiveImportPackage()"
          >
            {{ $t("common.prepare") }}
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
              {{ $t("events.openAudio") }}
            </button>
            <button
              class="rounded border border-outline bg-surface-container px-2 py-1 font-bold text-on-surface transition-colors hover:border-primary"
              type="button"
              @click="openDesktopPath(events.liveImportPackage.playlistPath)"
            >
              {{ $t("events.openM3u8") }}
            </button>
          </div>
        </div>
      </div>
    </aside>

    <!-- Main: active event workspace, or the creation screen -->
    <EventWorkspace v-if="events.activeEvent" />
    <EventCreatePanel v-else />
  </div>
</template>
