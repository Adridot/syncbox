<script setup lang="ts">
import {
  CalendarDays,
  Cog,
  Copy,
  FileSearch,
  LayoutDashboard,
  Library,
  ListChecks,
  Loader2,
  Stethoscope,
  Tag,
} from "@lucide/vue";
import type { ViewKey } from "../types/ui";
import { useEventsStore } from "../stores/events";
import { useSystemStore } from "../stores/system";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
const system = useSystemStore();
const events = useEventsStore();

const navItems: Array<{ key: ViewKey; labelKey: string; icon: unknown }> = [
  { key: "dashboard", labelKey: "nav.dashboard", icon: LayoutDashboard },
  { key: "library", labelKey: "nav.library", icon: Library },
  { key: "events", labelKey: "nav.events", icon: CalendarDays },
  { key: "downloadCenter", labelKey: "nav.downloadCenter", icon: ListChecks },
  { key: "duplicates", labelKey: "nav.duplicates", icon: Copy },
  { key: "missing", labelKey: "nav.missing", icon: FileSearch },
  { key: "untagged", labelKey: "nav.untagged", icon: Tag }
];
</script>

<template>
  <div class="flex h-screen w-full overflow-hidden bg-background text-on-surface">
    <nav
      class="hidden h-full w-64 shrink-0 flex-col overflow-y-auto border-r border-outline-variant bg-background md:flex"
      :aria-label="$t('shell.primaryNav')"
    >
      <div class="px-6 pb-6 pt-12">
        <!-- Draggable strip; sits below the floating macOS traffic lights. -->
        <div
          class="mb-8 flex items-center gap-2.5"
          style="-webkit-app-region: drag"
        >
          <img src="/favicon.png" alt="" class="h-9 w-9 shrink-0 rounded-lg" />
          <h1 class="text-xl font-bold leading-none tracking-tight">
            SYNC<span class="text-primary">BOX</span>
          </h1>
        </div>

        <ul class="space-y-1">
          <li v-for="item in navItems" :key="item.key">
            <button
              class="group flex w-full items-center gap-3 rounded-r p-3 text-sm font-medium transition-colors"
              :class="
                ui.activeView === item.key
                  ? '-ml-[2px] border-l-2 border-primary bg-surface-container-high text-primary'
                  : 'text-on-surface-variant hover:text-on-surface'
              "
              type="button"
              @click="ui.navigateTo(item.key)"
            >
              <component :is="item.icon" :size="20" aria-hidden="true" />
              <span>{{ $t(item.labelKey) }}</span>
            </button>
          </li>
        </ul>
      </div>

      <div class="mt-auto border-t border-outline-variant p-6">
        <button
          class="mb-1 flex w-full items-center gap-3 rounded-r p-3 text-sm font-medium transition-colors"
          :class="
            ui.activeView === 'doctor'
              ? '-ml-[2px] border-l-2 border-primary bg-surface-container-high text-primary'
              : 'text-on-surface-variant hover:text-on-surface'
          "
          type="button"
          @click="ui.navigateTo('doctor')"
        >
          <Stethoscope :size="20" aria-hidden="true" />
          <span>{{ $t("nav.doctor") }}</span>
        </button>
        <button
          class="mb-6 flex w-full items-center gap-3 rounded-r p-3 text-sm font-medium transition-colors"
          :class="
            ui.activeView === 'settings'
              ? '-ml-[2px] border-l-2 border-primary bg-surface-container-high text-primary'
              : 'text-on-surface-variant hover:text-on-surface'
          "
          type="button"
          @click="ui.navigateTo('settings')"
        >
          <Cog :size="20" aria-hidden="true" />
          <span>{{ $t("nav.settings") }}</span>
        </button>
        <button
          v-if="events.globalJobStats.inProgress > 0 || events.globalJobStats.failed > 0"
          type="button"
          class="mb-4 flex w-full items-center gap-2 rounded border border-outline-variant bg-surface-container-high px-3 py-2 text-left transition-colors hover:border-primary"
          @click="ui.navigateTo('downloadCenter')"
        >
          <Loader2
            v-if="events.globalJobStats.inProgress > 0"
            :size="14"
            class="shrink-0 animate-spin text-primary"
            aria-hidden="true"
          />
          <ListChecks v-else :size="14" class="shrink-0 text-tertiary" aria-hidden="true" />
          <span class="min-w-0 flex-1 truncate text-xs text-on-surface-variant">
            <template v-if="events.globalJobStats.inProgress > 0">
              {{ $t("shell.downloading", { count: events.globalJobStats.inProgress }) }}
            </template>
            <template v-else>
              {{ $t("shell.downloadsFailed", { count: events.globalJobStats.failed }) }}
            </template>
          </span>
        </button>

        <div class="mb-4 flex items-center gap-2">
          <div
            class="h-2 w-2 rounded-full"
            :class="
              system.health?.status === 'ok'
                ? 'bg-secondary shadow-[0_0_8px_var(--color-secondary)]'
                : 'bg-tertiary shadow-[0_0_8px_var(--color-tertiary)]'
            "
          />
          <span class="text-xs text-on-surface-variant">
            {{ $t("shell.apiStatus", { status: system.health?.status ?? $t("shell.starting") }) }}
          </span>
        </div>
        <div class="mb-4 flex items-center gap-2">
          <div
            class="h-2 w-2 rounded-full"
            :class="
              system.rekordboxStatus?.mutationAllowed
                ? 'bg-primary shadow-[0_0_8px_var(--color-primary)]'
                : 'bg-tertiary shadow-[0_0_8px_var(--color-tertiary)]'
            "
          />
          <span class="text-xs text-on-surface-variant">
            {{ system.rekordboxStatus?.rekordboxRunning ? $t("shell.rekordboxLive") : $t("shell.rekordboxClosed") }}
          </span>
        </div>
        <div class="flex items-center gap-2">
          <div
            class="h-2 w-2 rounded-full"
            :class="
              system.deemixStatus?.available && system.deemixStatus?.authenticated
                ? 'bg-secondary shadow-[0_0_8px_var(--color-secondary)]'
                : 'bg-outline'
            "
          />
          <span class="text-xs text-on-surface-variant">
            {{ system.deemixStatus?.available ? $t("shell.deemixAvailable") : $t("shell.deemixOffline") }}
          </span>
        </div>
      </div>
    </nav>

    <div class="flex min-w-0 flex-1 flex-col overflow-hidden bg-surface">
      <!-- Draggable: lets the window move from the title bar area. -->
      <header
        class="flex h-16 shrink-0 items-center justify-between border-b border-outline-variant bg-surface px-4 md:px-8"
        style="-webkit-app-region: drag"
      >
        <div class="flex min-w-0 items-center gap-4">
          <h2 class="truncate text-lg font-bold text-on-surface md:text-xl">{{ $t(ui.pageTitle) }}</h2>
        </div>

      </header>

      <main class="relative min-h-0 flex-1 overflow-hidden">
        <slot />
      </main>
    </div>
  </div>
</template>
