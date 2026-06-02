import { defineStore } from "pinia";
import { reactive, ref } from "vue";
import type { AppSettings, PathValidation, StorageLayout } from "../lib/api";
import { useSystemStore } from "./system";
import { useUiStore } from "./ui";

export const useSettingsStore = defineStore("settings", () => {
  const settings = reactive<AppSettings>({
    spotifyClientId: "",
    spotifyRedirectUri: "http://127.0.0.1:8765/api/spotify/callback",
    rekordboxDatabaseDir: "/Users/adriendidot/Library/Pioneer/rekordbox",
    storageRoot:
      "/Users/adriendidot/Library/CloudStorage/Dropbox-CloudOptionDJteam/Jockey Tricolore/Musique",
    permanentPath: "",
    manualCollectionPath: "",
    backupRetention: 15,
  });
  const storage = ref<StorageLayout | null>(null);
  // Folder-exists status for the two configurable path fields.
  const pathChecks = reactive<{ permanent: PathValidation | null; manual: PathValidation | null }>({
    permanent: null,
    manual: null,
  });

  // Read-only refresh of the resolved storage layout (no folder creation).
  async function loadStorage(): Promise<void> {
    const system = useSystemStore();
    if (!system.api) return;
    storage.value = await system.api.getStorageLayout();
  }

  // Validate that the configured Permanent / Manual collection folders exist.
  async function validatePaths(): Promise<void> {
    const system = useSystemStore();
    if (!system.api) return;
    [pathChecks.permanent, pathChecks.manual] = await Promise.all([
      system.api.validatePath(settings.permanentPath),
      system.api.validatePath(settings.manualCollectionPath),
    ]);
  }

  async function load(): Promise<void> {
    const system = useSystemStore();
    if (!system.api) return;
    Object.assign(settings, await system.api.getSettings());
    await Promise.all([loadStorage(), validatePaths()]);
  }

  async function save(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoading(async () => {
      Object.assign(settings, await system.api!.saveSettings(settings));
      // Create the managed storage folders on save so they always exist without
      // a separate manual step, then refresh the resolved layout + path checks.
      storage.value = await system.api!.ensureStorage();
      await validatePaths();
      ui.setMessage("success", "Settings saved.");
    });
  }

  async function ensureStorage(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoading(async () => {
      storage.value = await system.api!.ensureStorage();
      ui.setMessage("success", "Storage folders are ready.");
    });
  }

  const backupBusy = ref(false);

  function triggerDownload(filename: string, blob: Blob): void {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function stamp(): string {
    return new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
  }

  // Export the portable settings backup (paths, Spotify client id + tokens).
  async function exportSettings(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoading(async () => {
      const backup = await system.api!.exportSettings();
      triggerDownload(
        `syncbox-settings-${stamp()}.json`,
        new Blob([JSON.stringify(backup, null, 2)], { type: "application/json" })
      );
      ui.setMessage("success", "Settings exported.");
    });
  }

  async function importSettingsFromFile(file: File): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    try {
      const backup = JSON.parse(await file.text());
      const result = await system.api.importSettings(backup);
      Object.assign(settings, result.settings);
      await Promise.all([loadStorage(), validatePaths()]);
      ui.setMessage("success", `Imported ${result.applied} setting(s).`);
    } catch (error) {
      ui.setMessage("error", error instanceof Error ? error.message : String(error));
    }
  }

  // Export / import the entire app database (sources, events, tag rules…).
  async function exportData(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    backupBusy.value = true;
    try {
      const response = await fetch(system.api.dataExportUrl());
      if (!response.ok) throw new Error("Export failed.");
      triggerDownload(`syncbox-data-${stamp()}.sqlite3`, await response.blob());
      ui.setMessage("success", "All data exported.");
    } catch (error) {
      ui.setMessage("error", error instanceof Error ? error.message : String(error));
    } finally {
      backupBusy.value = false;
    }
  }

  async function importDataFromFile(file: File): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    backupBusy.value = true;
    try {
      const result = await system.api.importData(file);
      ui.setMessage("success", result.message);
      await load();
    } catch (error) {
      ui.setMessage("error", error instanceof Error ? error.message : String(error));
    } finally {
      backupBusy.value = false;
    }
  }

  async function openSpotifyAuth(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoading(async () => {
      const response = await system.api!.getSpotifyAuthUrl(
        settings.spotifyClientId,
        settings.spotifyRedirectUri
      );
      if (window.desktop) {
        await window.desktop.openExternal(response.authorizationUrl);
      } else {
        window.open(response.authorizationUrl, "_blank", "noopener,noreferrer");
      }
      ui.setMessage("success", "Spotify authorization opened in the browser.");
    });
  }

  return {
    settings,
    storage,
    pathChecks,
    backupBusy,
    load,
    save,
    loadStorage,
    validatePaths,
    ensureStorage,
    exportSettings,
    importSettingsFromFile,
    exportData,
    importDataFromFile,
    openSpotifyAuth,
  };
});
