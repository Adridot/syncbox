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
    apiPort: 8765,
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
      await Promise.all([loadStorage(), validatePaths()]);
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
    load,
    save,
    loadStorage,
    validatePaths,
    ensureStorage,
    openSpotifyAuth,
  };
});
