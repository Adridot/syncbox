<script setup lang="ts">
import { Database, ExternalLink, FileAudio, FolderOpen, Key, Save, Settings2 } from "@lucide/vue";
import { useSettingsStore } from "../stores/settings";

const settings = useSettingsStore();
</script>

<template>
  <div class="h-full overflow-y-auto p-6 md:p-8">
    <div class="mx-auto w-full max-w-5xl">
      <div class="mb-8 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 class="mb-1 text-2xl font-bold text-on-surface md:text-3xl">
            Configuration & Settings
          </h2>
          <p class="text-sm text-on-surface-variant">
            Manage connections, paths, and local storage.
          </p>
        </div>
        <button
          class="inline-flex items-center gap-2 rounded bg-primary px-5 py-2 text-sm font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02]"
          type="button"
          @click="settings.save()"
        >
          <Save :size="18" aria-hidden="true" />
          Save Changes
        </button>
      </div>

      <div class="grid grid-cols-1 gap-8 lg:grid-cols-12">
        <div class="flex flex-col gap-8 lg:col-span-8">
          <section class="rounded-xl border border-outline-variant bg-surface-container-high p-6">
            <h3 class="mb-6 flex items-center gap-2 text-lg font-bold text-on-surface">
              <Key class="text-primary" :size="20" aria-hidden="true" />
              Spotify Integration
            </h3>
            <div class="space-y-6">
              <label class="grid gap-2">
                <span class="text-sm font-bold text-on-surface">Spotify Client ID</span>
                <input
                  class="rounded border border-outline bg-surface-container px-4 py-2 font-mono text-sm text-on-surface focus:border-primary focus:outline-none"
                  v-model="settings.settings.spotifyClientId"
                />
              </label>
              <label class="grid gap-2">
                <span class="text-sm font-bold text-on-surface">Spotify Redirect URI</span>
                <input
                  class="rounded border border-outline bg-surface-container px-4 py-2 font-mono text-sm text-on-surface focus:border-primary focus:outline-none"
                  v-model="settings.settings.spotifyRedirectUri"
                />
                <small class="text-xs text-on-surface-variant">
                  Add this exact value in the Spotify Developer Dashboard.
                </small>
              </label>
              <button
                class="inline-flex items-center gap-2 rounded border border-outline bg-surface px-4 py-2 text-sm font-bold text-on-surface transition-colors hover:border-primary"
                type="button"
                @click="settings.openSpotifyAuth()"
              >
                <ExternalLink :size="17" aria-hidden="true" />
                Connect Spotify
              </button>
            </div>
          </section>

          <section class="rounded-xl border border-outline-variant bg-surface-container-high p-6">
            <h3 class="mb-6 flex items-center gap-2 text-lg font-bold text-on-surface">
              <FolderOpen class="text-secondary" :size="20" aria-hidden="true" />
              Local Directories & Paths
            </h3>
            <div class="space-y-6">
              <label class="grid gap-2">
                <span class="text-sm font-bold text-on-surface">Rekordbox database directory</span>
                <input
                  class="rounded border border-outline bg-surface-container px-4 py-2 font-mono text-sm text-on-surface focus:border-primary focus:outline-none"
                  v-model="settings.settings.rekordboxDatabaseDir"
                />
              </label>
              <label class="grid gap-2">
                <span class="text-sm font-bold text-on-surface">Storage root</span>
                <input
                  class="rounded border border-outline bg-surface-container px-4 py-2 font-mono text-sm text-on-surface focus:border-primary focus:outline-none"
                  v-model="settings.settings.storageRoot"
                />
              </label>
            </div>
          </section>
        </div>

        <aside class="flex flex-col gap-6 lg:col-span-4">
          <section class="rounded-xl border border-outline-variant bg-surface-container-high p-6">
            <h3 class="mb-4 flex items-center gap-2 text-lg font-bold text-on-surface">
              <Settings2 class="text-on-surface-variant" :size="20" aria-hidden="true" />
              Managed Storage
            </h3>
            <button
              class="mb-5 inline-flex w-full items-center justify-center gap-2 rounded border border-outline bg-surface px-4 py-2 text-sm font-bold text-on-surface transition-colors hover:border-primary"
              type="button"
              @click="settings.ensureStorage()"
            >
              <FileAudio :size="17" aria-hidden="true" />
              Ensure Folders
            </button>
            <dl v-if="settings.storage" class="grid gap-3 text-xs">
              <div>
                <dt class="font-bold text-on-surface">Inbox</dt>
                <dd class="break-all text-on-surface-variant">{{ settings.storage.inbox }}</dd>
              </div>
              <div>
                <dt class="font-bold text-on-surface">Permanent</dt>
                <dd class="break-all text-on-surface-variant">{{ settings.storage.permanent }}</dd>
              </div>
              <div>
                <dt class="font-bold text-on-surface">Events</dt>
                <dd class="break-all text-on-surface-variant">{{ settings.storage.events }}</dd>
              </div>
              <div>
                <dt class="font-bold text-on-surface">Manual</dt>
                <dd class="break-all text-on-surface-variant">{{ settings.storage.manualCollection }}</dd>
              </div>
            </dl>
            <p v-else class="text-xs text-on-surface-variant">
              Storage folders have not been checked yet.
            </p>
          </section>

          <section class="relative overflow-hidden rounded-xl border border-outline-variant bg-surface-container p-6">
            <div class="absolute left-0 top-0 h-full w-1 bg-error" />
            <h3 class="mb-2 text-base font-bold text-on-surface">Safety Model</h3>
            <p class="text-xs text-on-surface-variant">
              Rekordbox writes stay blocked while Rekordbox is running. Destructive changes remain proposal-based.
            </p>
          </section>

          <section class="rounded-xl border border-outline-variant bg-surface-container p-6">
            <h3 class="mb-3 flex items-center gap-2 text-base font-bold text-on-surface">
              <Database class="text-primary" :size="18" aria-hidden="true" />
              Local API Port
            </h3>
            <input
              class="rounded border border-outline bg-surface-container-high px-4 py-2 font-mono text-sm text-on-surface focus:border-primary focus:outline-none"
              v-model.number="settings.settings.apiPort"
              type="number"
            />
          </section>
        </aside>
      </div>
    </div>
  </div>
</template>
