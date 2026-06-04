<script setup lang="ts">
import { AlertTriangle, Archive, CheckCircle2, CloudDownload, Download, ExternalLink, FolderOpen, Key, Loader2, LogOut, Play, Save, Settings2, Upload } from "@lucide/vue";
import { onMounted, onUnmounted, ref } from "vue";
import type { DeemixDesktopStatus } from "../types/electron";
import { useSettingsStore } from "../stores/settings";
import { useSystemStore } from "../stores/system";
import { useUiStore } from "../stores/ui";

const settings = useSettingsStore();
const system = useSystemStore();
const ui = useUiStore();

const settingsFileInput = ref<HTMLInputElement | null>(null);
const dataFileInput = ref<HTMLInputElement | null>(null);

// --- Deemix downloader provisioning (Electron desktop only) ---------------
const deemix = ref<DeemixDesktopStatus | null>(null);
const deemixBusy = ref(false);
const deemixStage = ref<string>("");
let deemixTimer: number | undefined;
let stopProgress: (() => void) | undefined;

async function refreshDeemix(): Promise<void> {
  if (!window.desktop) return;
  try {
    deemix.value = await window.desktop.deemix.status();
  } catch {
    /* ignore transient errors */
  }
}

async function launchDeemix(): Promise<void> {
  if (!window.desktop) return;
  deemixBusy.value = true;
  try {
    deemix.value = await window.desktop.deemix.launch();
    ui.setMessage("success", "Deemix is starting in the background.");
  } catch (error) {
    ui.setMessage("error", error instanceof Error ? error.message : String(error));
  } finally {
    deemixBusy.value = false;
    setTimeout(refreshDeemix, 2000);
  }
}

async function installDeemix(): Promise<void> {
  if (!window.desktop) return;
  deemixBusy.value = true;
  deemixStage.value = "Starting…";
  try {
    deemix.value = await window.desktop.deemix.install();
    ui.setMessage("success", "Deemix Remastered installed and started.");
  } catch (error) {
    ui.setMessage("error", error instanceof Error ? error.message : String(error));
  } finally {
    deemixBusy.value = false;
    deemixStage.value = "";
    setTimeout(refreshDeemix, 2000);
  }
}

onMounted(() => {
  // Load the current Spotify account state for the connection badge.
  system.refreshSpotifyStatus();
  if (!window.desktop) return;
  refreshDeemix();
  deemixTimer = window.setInterval(refreshDeemix, 5000);
  stopProgress = window.desktop.deemix.onProgress((p) => {
    deemixStage.value = p.percent !== null ? `${p.stage} ${p.percent}%` : p.stage;
  });
});

onUnmounted(() => {
  if (deemixTimer) window.clearInterval(deemixTimer);
  stopProgress?.();
});

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
                <span class="text-sm font-bold text-on-surface">Spotify Client Secret</span>
                <input
                  type="password"
                  autocomplete="off"
                  class="rounded border border-outline bg-surface-container px-4 py-2 font-mono text-sm text-on-surface focus:border-primary focus:outline-none"
                  v-model="settings.settings.spotifyClientSecret"
                />
                <small class="text-xs text-on-surface-variant">
                  Stored locally. Used with the Client ID for app authentication — no browser sign-in.
                </small>
              </label>
              <label class="grid gap-2">
                <span class="text-sm font-bold text-on-surface">Spotify Username</span>
                <input
                  class="rounded border border-outline bg-surface-container px-4 py-2 font-mono text-sm text-on-surface focus:border-primary focus:outline-none"
                  v-model="settings.settings.spotifyUsername"
                />
                <small class="text-xs text-on-surface-variant">
                  Your Spotify user ID — used to read your public playlists.
                </small>
              </label>
              <button
                class="inline-flex items-center gap-2 rounded border border-outline bg-surface px-4 py-2 text-sm font-bold text-on-surface transition-colors hover:border-primary disabled:opacity-60"
                type="button"
                :disabled="ui.loading"
                @click="settings.testSpotify()"
              >
                <CheckCircle2 :size="17" aria-hidden="true" />
                Test Connection
              </button>

              <!-- Optional: sign in with a real account to see private playlists. -->
              <div class="grid gap-3 rounded-lg border border-outline-variant bg-surface-container p-4">
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p class="text-sm font-bold text-on-surface">Connect your Spotify account</p>
                    <p class="text-xs text-on-surface-variant">
                      Optional — unlocks your private, collaborative and followed playlists in Manage sources.
                    </p>
                  </div>
                  <span
                    v-if="system.spotifyStatus"
                    class="inline-flex items-center gap-1.5 text-sm font-semibold"
                    :class="
                      system.spotifyStatus.connected && system.spotifyStatus.mode === 'oauth'
                        ? 'text-secondary'
                        : 'text-tertiary'
                    "
                  >
                    <CheckCircle2
                      v-if="system.spotifyStatus.connected && system.spotifyStatus.mode === 'oauth'"
                      :size="16"
                      aria-hidden="true"
                    />
                    <AlertTriangle v-else :size="16" aria-hidden="true" />
                    {{
                      system.spotifyStatus.connected && system.spotifyStatus.mode === "oauth"
                        ? `Connected as ${system.spotifyStatus.displayName || system.spotifyStatus.username}`
                        : "No account connected"
                    }}
                  </span>
                </div>
                <div class="flex flex-wrap items-center gap-3">
                  <button
                    class="inline-flex items-center gap-2 rounded border border-outline bg-surface px-4 py-2 text-sm font-bold text-on-surface transition-colors hover:border-primary disabled:opacity-60"
                    type="button"
                    :disabled="settings.spotifyConnecting"
                    @click="settings.connectSpotifyAccount()"
                  >
                    <Loader2 v-if="settings.spotifyConnecting" :size="17" class="animate-spin" aria-hidden="true" />
                    <ExternalLink v-else :size="17" aria-hidden="true" />
                    {{ settings.spotifyConnecting ? "Waiting for sign-in…" : "Connect my account" }}
                  </button>
                  <button
                    v-if="system.spotifyStatus?.connected && system.spotifyStatus.mode === 'oauth'"
                    class="inline-flex items-center gap-2 rounded px-3 py-2 text-sm font-semibold text-on-surface-variant transition-colors hover:text-on-surface disabled:opacity-60"
                    type="button"
                    :disabled="ui.loading"
                    @click="settings.disconnectSpotifyAccount()"
                  >
                    <LogOut :size="16" aria-hidden="true" />
                    Disconnect
                  </button>
                </div>
                <small v-if="system.spotifyStatus?.redirectUri" class="text-xs text-on-surface-variant">
                  In your Spotify app's settings, add this exact Redirect URI:
                  <code class="rounded bg-surface-container-high px-1.5 py-0.5 font-mono text-[11px]">{{
                    system.spotifyStatus.redirectUri
                  }}</code>
                </small>
                <small class="text-xs text-on-surface-variant">
                  Note: a Spotify app in Development mode only allows accounts you add under
                  “User Management” (max 25). Public access needs Spotify’s Extended Quota approval.
                </small>
              </div>
            </div>
          </section>

          <section
            v-if="deemix"
            class="rounded-xl border border-outline-variant bg-surface-container-high p-6"
          >
            <h3 class="mb-1 flex items-center gap-2 text-lg font-bold text-on-surface">
              <CloudDownload class="text-primary" :size="20" aria-hidden="true" />
              Deemix downloader
            </h3>
            <p class="mb-4 text-xs text-on-surface-variant">
              Syncbox downloads audio through Deemix&nbsp;Remastered. It starts automatically with
              Syncbox when installed — no need to launch it yourself.
            </p>

            <div class="flex flex-wrap items-center gap-3">
              <span
                class="inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-semibold"
                :class="
                  deemix.running
                    ? 'bg-secondary/15 text-secondary'
                    : deemix.installed
                      ? 'bg-tertiary/15 text-tertiary'
                      : 'bg-error/15 text-error'
                "
              >
                <CheckCircle2 v-if="deemix.running" :size="16" aria-hidden="true" />
                <AlertTriangle v-else :size="16" aria-hidden="true" />
                {{ deemix.running ? "Running" : deemix.installed ? "Installed, not running" : "Not installed" }}
              </span>

              <button
                v-if="deemix.installed && !deemix.running"
                type="button"
                class="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
                :disabled="deemixBusy"
                @click="launchDeemix"
              >
                <Play :size="16" aria-hidden="true" />
                Launch Deemix
              </button>

              <button
                v-if="!deemix.installed"
                type="button"
                class="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
                :disabled="deemixBusy"
                @click="installDeemix"
              >
                <Loader2 v-if="deemixBusy" :size="16" class="animate-spin" aria-hidden="true" />
                <CloudDownload v-else :size="16" aria-hidden="true" />
                Install Deemix
              </button>

              <span v-if="deemixBusy && deemixStage" class="text-xs text-on-surface-variant">
                {{ deemixStage }}
              </span>
            </div>
            <p v-if="!deemix.installed" class="mt-3 text-xs text-on-surface-variant">
              “Install Deemix” downloads the latest release from GitHub (~140&nbsp;MB) into your
              Applications folder.
            </p>

            <div class="mt-6 border-t border-outline-variant pt-5">
              <label class="grid gap-2">
                <span class="text-sm font-bold text-on-surface">Deezer ARL</span>
                <input
                  type="password"
                  autocomplete="off"
                  class="rounded border border-outline bg-surface-container px-4 py-2 font-mono text-sm text-on-surface focus:border-primary focus:outline-none"
                  v-model="settings.settings.deemixArl"
                />
                <small class="text-xs text-on-surface-variant">
                  Paste your Deezer ARL here — Syncbox configures Deemix for you, no need to open it.
                </small>
              </label>
              <div class="mt-3 flex flex-wrap items-center gap-3">
                <button
                  class="inline-flex items-center gap-2 rounded border border-outline bg-surface px-4 py-2 text-sm font-bold text-on-surface transition-colors hover:border-primary disabled:opacity-60"
                  type="button"
                  :disabled="ui.loading"
                  @click="settings.connectDeezer()"
                >
                  <Key :size="17" aria-hidden="true" />
                  Connect Deezer
                </button>
                <span
                  v-if="system.deemixStatus"
                  class="inline-flex items-center gap-1.5 text-sm font-semibold"
                  :class="system.deemixStatus.authenticated ? 'text-secondary' : 'text-tertiary'"
                >
                  <CheckCircle2 v-if="system.deemixStatus.authenticated" :size="16" aria-hidden="true" />
                  <AlertTriangle v-else :size="16" aria-hidden="true" />
                  {{ system.deemixStatus.authenticated ? "Deezer authenticated" : "Not authenticated" }}
                </span>
              </div>
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
            <h3 class="mb-1 flex items-center gap-2 text-lg font-bold text-on-surface">
              <Settings2 class="text-on-surface-variant" :size="20" aria-hidden="true" />
              Storage locations
            </h3>
            <p class="mb-4 text-xs text-on-surface-variant">
              Where Syncbox keeps downloads under your storage root. These folders are
              created automatically when you save settings or run your first download.
            </p>
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
              Save settings to resolve your storage folders.
            </p>
          </section>

          <section class="relative overflow-hidden rounded-xl border border-outline-variant bg-surface-container p-6">
            <div class="absolute left-0 top-0 h-full w-1 bg-error" />
            <h3 class="mb-2 text-base font-bold text-on-surface">Safety Model</h3>
            <p class="text-xs text-on-surface-variant">
              Rekordbox writes stay blocked while Rekordbox is running. Destructive changes remain proposal-based.
            </p>
          </section>
        </aside>
      </div>
    </div>
  </div>
</template>
