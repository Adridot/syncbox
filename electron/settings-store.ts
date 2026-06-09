import Store from "electron-store";

/**
 * Durable, instant-read app configuration — the deemix-style "config.json".
 *
 * The Python service keeps its own SQLite settings table (for runtime/derived
 * values like the Spotify OAuth tokens it mints), but the user-facing *portable*
 * settings also live here, in a plain JSON file under userData owned by the main
 * process. Because electron-store reads synchronously off disk, the renderer can
 * load settings the instant the window opens — it no longer races the slow
 * PyInstaller service boot and then shows blank fields (the old "I have to
 * re-import every launch" bug). The main process keeps this file and the service
 * DB in sync (see reconcileSettings/pushToService in main.ts).
 */
export type AppConfig = {
  spotifyClientId: string;
  spotifyClientSecret: string;
  spotifyUsername: string;
  rekordboxDatabaseDir: string;
  storageRoot: string;
  permanentPath: string;
  manualCollectionPath: string;
  deemixArl: string;
  backupRetention: number;
};

// Wire/JSON keys are camelCase to match the service's /api/settings payload, so
// a config object round-trips to the backend without any field renaming.
export const APP_CONFIG_KEYS: (keyof AppConfig)[] = [
  "spotifyClientId",
  "spotifyClientSecret",
  "spotifyUsername",
  "rekordboxDatabaseDir",
  "storageRoot",
  "permanentPath",
  "manualCollectionPath",
  "deemixArl",
  "backupRetention",
];

type StoredConfig = AppConfig & {
  // False until the first reconcile has seeded this file from the service DB
  // (migration for existing users) or the user has saved settings at least once.
  // Gates the one-time pull-from-service so we never clobber real settings with
  // empty defaults.
  _initialized: boolean;
};

const DEFAULT_CONFIG: StoredConfig = {
  spotifyClientId: "",
  spotifyClientSecret: "",
  spotifyUsername: "",
  rekordboxDatabaseDir: "",
  storageRoot: "",
  permanentPath: "",
  manualCollectionPath: "",
  deemixArl: "",
  backupRetention: 15,
  _initialized: false,
};

export const settingsStore = new Store<StoredConfig>({
  name: "syncbox-settings",
  defaults: DEFAULT_CONFIG,
  // A hand-edited or truncated JSON file should degrade to defaults, never crash
  // the app on boot.
  clearInvalidConfig: true,
});

/** The portable config (the nine settings fields), without internal flags. */
export function readConfig(): AppConfig {
  return {
    spotifyClientId: settingsStore.get("spotifyClientId"),
    spotifyClientSecret: settingsStore.get("spotifyClientSecret"),
    spotifyUsername: settingsStore.get("spotifyUsername"),
    rekordboxDatabaseDir: settingsStore.get("rekordboxDatabaseDir"),
    storageRoot: settingsStore.get("storageRoot"),
    permanentPath: settingsStore.get("permanentPath"),
    manualCollectionPath: settingsStore.get("manualCollectionPath"),
    deemixArl: settingsStore.get("deemixArl"),
    backupRetention: settingsStore.get("backupRetention"),
  };
}

/** Merge a (partial) config in and persist. Returns the full portable config. */
export function writeConfig(partial: Partial<AppConfig>): AppConfig {
  const next: Partial<AppConfig> = {};
  for (const key of APP_CONFIG_KEYS) {
    const value = partial[key];
    if (value !== undefined && value !== null) {
      Object.assign(next, { [key]: value });
    }
  }
  settingsStore.set(next);
  return readConfig();
}

export function isInitialized(): boolean {
  return settingsStore.get("_initialized") === true;
}

export function markInitialized(): void {
  settingsStore.set("_initialized", true);
}
