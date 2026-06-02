<script setup lang="ts">
import { AlertTriangle, Archive, CheckCircle2, Database, Download, ExternalLink, FileAudio, FolderOpen, Key, Save, Settings2, Upload } from "@lucide/vue";
import { ref } from "vue";
import { useSettingsStore } from "../stores/settings";

const settings = useSettingsStore();

const settingsFileInput = ref<HTMLInputElement | null>(null);
const dataFileInput = ref<HTMLInputElement | null>(null);

async function onSettingsFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file) await settings.importSettingsFromFile(file);
  input.value = "";
}

async function onDataFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (
    file &&
    window.confirm(
      "Restore ALL app data from this file? This replaces your current sources, events, tag rules and settings. A safety backup of the current data is made first."
    )
  ) {
    await settings.importDataFromFile(file);
  }
  input.value = "";
}
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
              <label class="grid gap-2">
                <span class="text-sm font-bold text-on-surface">
                  Permanent downloads path
                  <span class="font-normal text-on-surface-variant">(optional)</span>
                </span>
                <input
                  class="rounded border border-outline bg-surface-container px-4 py-2 font-mono text-sm text-on-surface focus:border-primary focus:outline-none"
                  v-model="settings.settings.permanentPath"
                  placeholder="{storageRoot}/_rekordbox_sync/permanent"
                  @blur="settings.validatePaths()"
                />
                <small v-if="settings.pathChecks.permanent" class="flex items-center gap-1.5 text-xs">
                  <template v-if="!settings.pathChecks.permanent.configured">
                    <span class="text-on-surface-variant">Using default folder.</span>
                  </template>
                  <template v-else-if="settings.pathChecks.permanent.isDir">
                    <CheckCircle2 :size="13" class="text-secondary" aria-hidden="true" />
                    <span class="text-secondary">Folder found.</span>
                  </template>
                  <template v-else>
                    <AlertTriangle :size="13" class="text-error" aria-hidden="true" />
                    <span class="text-error">Folder not found — check the path.</span>
                  </template>
                </small>
              </label>
              <label class="grid gap-2">
                <span class="text-sm font-bold text-on-surface">
                  Manual collection path
                  <span class="font-normal text-on-surface-variant">(optional)</span>
                </span>
                <input
                  class="rounded border border-outline bg-surface-container px-4 py-2 font-mono text-sm text-on-surface focus:border-primary focus:outline-none"
                  v-model="settings.settings.manualCollectionPath"
                  placeholder="{storageRoot}/_rekordbox_sync/manual_collection"
                  @blur="settings.validatePaths()"
                />
                <small v-if="settings.pathChecks.manual" class="flex items-center gap-1.5 text-xs">
                  <template v-if="!settings.pathChecks.manual.configured">
                    <span class="text-on-surface-variant">Using default folder.</span>
                  </template>
                  <template v-else-if="settings.pathChecks.manual.isDir">
                    <CheckCircle2 :size="13" class="text-secondary" aria-hidden="true" />
                    <span class="text-secondary">Folder found.</span>
                  </template>
                  <template v-else>
                    <AlertTriangle :size="13" class="text-error" aria-hidden="true" />
                    <span class="text-error">Folder not found — check the path.</span>
                  </template>
                </small>
              </label>
            </div>
          </section>

          <section class="rounded-xl border border-outline-variant bg-surface-container-high p-6">
            <h3 class="mb-1 flex items-center gap-2 text-lg font-bold text-on-surface">
              <Archive class="text-primary" :size="20" aria-hidden="true" />
              Backup &amp; Restore
            </h3>
            <p class="mb-5 text-xs text-on-surface-variant">
              Settings live in <span class="font-mono">Application&nbsp;Support</span> and survive app
              updates. Export a portable copy to recover after a clean reinstall or move to another Mac.
            </p>

            <div class="grid gap-5 sm:grid-cols-2">
              <div class="rounded-lg border border-outline-variant bg-surface p-4">
                <h4 class="mb-1 text-sm font-bold text-on-surface">Settings only</h4>
                <p class="mb-3 text-xs text-on-surface-variant">
                  Paths, Spotify client&nbsp;ID + tokens, backup retention. Small JSON file.
                </p>
                <div class="flex flex-wrap gap-2">
                  <button
                    type="button"
                    class="inline-flex items-center gap-1.5 rounded bg-primary px-3 py-1.5 text-xs font-bold text-white disabled:opacity-60"
                    :disabled="settings.backupBusy"
                    @click="settings.exportSettings()"
                  >
                    <Download :size="14" aria-hidden="true" /> Export
                  </button>
                  <button
                    type="button"
                    class="inline-flex items-center gap-1.5 rounded border border-outline px-3 py-1.5 text-xs font-semibold text-on-surface hover:border-primary disabled:opacity-60"
                    :disabled="settings.backupBusy"
                    @click="settingsFileInput?.click()"
                  >
                    <Upload :size="14" aria-hidden="true" /> Import
                  </button>
                  <input
                    ref="settingsFileInput"
                    type="file"
                    accept="application/json,.json"
                    class="hidden"
                    @change="onSettingsFile"
                  />
                </div>
              </div>

              <div class="rounded-lg border border-outline-variant bg-surface p-4">
                <h4 class="mb-1 text-sm font-bold text-on-surface">All data</h4>
                <p class="mb-3 text-xs text-on-surface-variant">
                  Everything: sources, events, tag rules, mappings + settings. Full database file.
                </p>
                <div class="flex flex-wrap gap-2">
                  <button
                    type="button"
                    class="inline-flex items-center gap-1.5 rounded bg-primary px-3 py-1.5 text-xs font-bold text-white disabled:opacity-60"
                    :disabled="settings.backupBusy"
                    @click="settings.exportData()"
                  >
                    <Download :size="14" aria-hidden="true" /> Export
                  </button>
                  <button
                    type="button"
                    class="inline-flex items-center gap-1.5 rounded border border-outline px-3 py-1.5 text-xs font-semibold text-on-surface hover:border-error hover:text-error disabled:opacity-60"
                    :disabled="settings.backupBusy"
                    @click="dataFileInput?.click()"
                  >
                    <Upload :size="14" aria-hidden="true" /> Restore
                  </button>
                  <input
                    ref="dataFileInput"
                    type="file"
                    accept=".sqlite3,application/octet-stream"
                    class="hidden"
                    @change="onDataFile"
                  />
                </div>
              </div>
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
