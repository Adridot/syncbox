<script setup lang="ts">
import {
  CalendarDays,
  CircleUser,
  Cog,
  LayoutDashboard,
  Library,
  ListChecks,
  Search,
  Wifi
} from "@lucide/vue";
import type { ViewKey } from "../types/ui";
import { useSystemStore } from "../stores/system";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
const system = useSystemStore();

const navItems: Array<{ key: ViewKey; label: string; icon: unknown }> = [
  { key: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { key: "library", label: "My Library", icon: Library },
  { key: "events", label: "Event Imports", icon: CalendarDays },
  { key: "downloadCenter", label: "Download & Match", icon: ListChecks }
];
</script>

<template>
  <div class="flex h-screen w-full overflow-hidden bg-background text-on-surface">
    <nav
      class="hidden h-full w-64 shrink-0 flex-col overflow-y-auto border-r border-outline-variant bg-background md:flex"
      aria-label="Primary"
    >
      <div class="p-6">
        <div class="mb-8 flex items-center gap-2">
          <div class="grid h-8 w-8 place-items-center rounded bg-primary text-lg font-bold text-white">
            R
          </div>
          <h1 class="text-lg font-bold leading-none tracking-tight">
            Rekordbox <span class="text-primary">Studio</span>
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
              <span>{{ item.label }}</span>
            </button>
          </li>
        </ul>
      </div>

      <div class="mt-auto border-t border-outline-variant p-6">
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
          <span>Settings</span>
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
            API {{ system.health?.status ?? "starting" }}
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
            {{ system.rekordboxStatus?.rekordboxRunning ? "Rekordbox Live" : "Rekordbox Closed" }}
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
            {{ system.deemixStatus?.available ? "Deemix Available" : "Deemix Offline" }}
          </span>
        </div>
      </div>
    </nav>

    <div class="flex min-w-0 flex-1 flex-col overflow-hidden bg-surface">
      <header
        class="flex h-16 shrink-0 items-center justify-between border-b border-outline-variant bg-surface px-4 md:px-8"
      >
        <div class="flex min-w-0 items-center gap-4">
          <h2 class="truncate text-lg font-bold text-on-surface md:text-xl">{{ ui.pageTitle }}</h2>
        </div>

        <div class="ml-auto flex items-center gap-3">
          <div class="relative hidden sm:block">
            <Search
              class="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant"
              :size="16"
              aria-hidden="true"
            />
            <input
              class="w-56 rounded border border-outline bg-surface-container-high py-1.5 pl-9 pr-4 text-sm text-on-surface transition-colors focus:border-primary focus:outline-none lg:w-72"
              type="search"
              placeholder="Search library..."
              :value="ui.searchQuery"
              @input="ui.searchQuery = ($event.target as HTMLInputElement).value"
            />
          </div>
          <div
            class="hidden items-center gap-2 rounded border border-outline-variant bg-surface-container-high px-3 py-1.5 text-xs text-on-surface-variant lg:flex"
          >
            <Wifi :size="15" aria-hidden="true" />
            <span>{{ system.rekordboxStatus?.mutationAllowed ? "Writes allowed" : "Write locked" }}</span>
          </div>
          <button
            class="grid h-9 w-9 place-items-center rounded border border-outline bg-surface-container-high text-on-surface-variant transition-colors hover:border-primary hover:text-on-surface"
            type="button"
          >
            <CircleUser :size="18" aria-hidden="true" />
          </button>
        </div>
      </header>

      <main class="relative min-h-0 flex-1 overflow-hidden">
        <slot />
      </main>
    </div>
  </div>
</template>
