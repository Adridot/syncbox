import { defineStore } from "pinia";
import { reactive, ref } from "vue";
import type { AppSettings, PathValidation, StorageLayout } from "../lib/api";
import { useSpotifyStore } from "./spotify";
import { useSystemStore } from "./system";
import { useUiStore } from "./ui";

export const useSettingsStore = defineStore("settings", () => {
  const settings = reactive<AppSettings>({
    spotifyClientId: "",
    spotifyClientSecret: "",
    spotifyUsername: "",
    rekordboxDatabaseDir: "/Users/adriendidot/Library/Pioneer/rekordbox",
    storageRoot:
      "/Users/adriendidot/Library/CloudStorage/Dropbox-CloudOptionDJteam/Jockey Tricolore/Musique",
    permanentPath: "",
    manualCollectionPath: "",
    deemixArl: "",
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
    await ui.withLoadingFlag(backupBusy, async () => {
      const blob = await system.api!.exportData();
      triggerDownload(`syncbox-data-${stamp()}.sqlite3`, blob);
      ui.setMessage("success", "All data exported.");
    });
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

  // Save settings (incl. the Deezer ARL), then push the ARL to Deemix so the
  // user configures Deezer here instead of in Deemix's own UI.
  async function connectDeezer(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoading(async () => {
      Object.assign(settings, await system.api!.saveSettings(settings));
      const status = await system.api!.loginDeemixArl();
      system.deemixStatus = status;
      ui.setMessage(
        status.authenticated ? "success" : "error",
        status.authenticated
          ? "Deezer connected — Deemix is authenticated."
          : `Deezer not authenticated: ${status.detail}`
      );
    });
  }

  // Save the Spotify credentials, then verify them with an app token + username
  // (Client-Credentials flow — no browser sign-in).
  async function testSpotify(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoading(async () => {
      Object.assign(settings, await system.api!.saveSettings(settings));
      const status = await system.api!.testSpotifyConnection();
      ui.setMessage(
        "success",
        `Connected to Spotify as ${status.displayName || status.username}.`
      );
    });
  }

  // Optional: sign in with a real Spotify account (Authorization Code flow) to
  // unlock private/collaborative/followed playlists. Save the client id/secret,
  // open the consent page in the browser, then poll until the local callback has
  // stored the tokens.
  const spotifyConnecting = ref(false);

  async function connectSpotifyAccount(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || spotifyConnecting.value) return;
    spotifyConnecting.value = true;
    try {
      Object.assign(settings, await system.api.saveSettings(settings));
      const { authorizationUrl } = await system.api.getSpotifyAuthUrl(
        settings.spotifyClientId
      );
      if (window.desktop) {
        await window.desktop.openExternal(authorizationUrl);
      } else {
        window.open(authorizationUrl, "_blank", "noopener,noreferrer");
      }
      ui.setMessage("info", "Finish signing in to Spotify in your browser…");

      // Poll the local callback's result: every 1.5s for up to ~2 minutes.
      const deadline = Date.now() + 120_000;
      while (Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        const status = await system.api.getSpotifyStatus().catch(() => null);
        if (status?.connected && status.mode === "oauth") {
          system.spotifyStatus = status;
          ui.setMessage(
            "success",
            `Connected to Spotify as ${status.displayName || status.username}.`
          );
          // Re-fetch "Manage sources" so private playlists show up immediately.
          await useSpotifyStore().fetchAllPlaylists();
          return;
        }
      }
      ui.setMessage(
        "error",
        "Spotify sign-in timed out. Make sure the redirect URI is registered in your Spotify app, then try again."
      );
    } catch (error) {
      ui.setMessage("error", error instanceof Error ? error.message : String(error));
    } finally {
      spotifyConnecting.value = false;
    }
  }

  async function disconnectSpotifyAccount(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoading(async () => {
      system.spotifyStatus = await system.api!.disconnectSpotify();
      ui.setMessage("success", "Disconnected your Spotify account.");
      // Fall back to public playlists (app token).
      await useSpotifyStore().fetchAllPlaylists();
    });
  }

  return {
    settings,
    storage,
    pathChecks,
    backupBusy,
    spotifyConnecting,
    load,
    save,
    loadStorage,
    validatePaths,
    ensureStorage,
    exportSettings,
    importSettingsFromFile,
    exportData,
    importDataFromFile,
    testSpotify,
    connectSpotifyAccount,
    disconnectSpotifyAccount,
    connectDeezer,
  };
});
