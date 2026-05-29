import { defineStore } from "pinia";
import { reactive, ref } from "vue";
import type { AppSettings, StorageLayout } from "../lib/api";
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
  });
  const storage = ref<StorageLayout | null>(null);

  async function load(): Promise<void> {
    const system = useSystemStore();
    if (!system.api) return;
    Object.assign(settings, await system.api.getSettings());
  }

  async function save(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoading(async () => {
      Object.assign(settings, await system.api!.saveSettings(settings));
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

  return { settings, storage, load, save, ensureStorage, openSpotifyAuth };
});
