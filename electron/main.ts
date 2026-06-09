import { app, BrowserWindow, ipcMain, Menu, shell } from "electron";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { isAbsolute, join } from "node:path";
import {
  ensureDeemixRunning,
  getDeemixStatus,
  installDeemix,
  launchDeemix,
  findDeemixApp,
} from "./deemix.js";
import {
  type AppConfig,
  isInitialized,
  markInitialized,
  readConfig,
  writeConfig,
} from "./settings-store.js";

/**
 * Auto-update is scaffolded but dormant: it only runs in a packaged build when
 * RBSYNC_ENABLE_UPDATES=1 AND a publish provider is configured (package.json
 * build.publish -> generates app-update.yml). Until then we skip it so the app
 * never errors looking for a non-existent update feed. To enable: set
 * build.publish (e.g. GitHub/generic), sign + notarize, then flip the env flag.
 */
async function checkForUpdates(): Promise<void> {
  if (!app.isPackaged || process.env.RBSYNC_ENABLE_UPDATES !== "1") {
    return;
  }
  try {
    const { autoUpdater } = await import("electron-updater");
    autoUpdater.logger = console;
    autoUpdater.autoDownload = true;
    await autoUpdater.checkForUpdatesAndNotify();
  } catch (error) {
    console.warn("[updater] skipped:", (error as Error).message);
  }
}

let mainWindow: BrowserWindow | null = null;
let serviceProcess: ChildProcessWithoutNullStreams | null = null;

const servicePort = Number(process.env.RBSYNC_SERVICE_PORT ?? "8765");
const apiBaseUrl = `http://127.0.0.1:${servicePort}`;

// --- Settings reconciliation (electron-store <-> Python service) -----------
// electron-store is the durable, instant-read source of truth for the portable
// settings. The service's SQLite copy is kept in sync so the backend (downloads,
// Spotify, path resolution) always sees the same config the user configured.

const delay = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

async function waitForService(timeoutMs = 30_000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${apiBaseUrl}/api/health`);
      if (response.ok) return true;
    } catch {
      // Service still booting — retry until the deadline.
    }
    await delay(500);
  }
  return false;
}

async function pullSettingsFromService(): Promise<AppConfig | null> {
  try {
    const response = await fetch(`${apiBaseUrl}/api/settings`);
    if (!response.ok) return null;
    return (await response.json()) as AppConfig;
  } catch {
    return null;
  }
}

async function pushSettingsToService(config: AppConfig): Promise<boolean> {
  try {
    const response = await fetch(`${apiBaseUrl}/api/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
    return response.ok;
  } catch {
    return false;
  }
}

// Resolves once electron-store holds usable settings: either confirmed already
// initialised, or freshly migrated from the service DB. The renderer's
// "settings:get" awaits this so a first cold start reads real values (not empty
// defaults); every later start resolves instantly without touching the service.
let resolveSettingsReady: () => void = () => {};
const settingsReady = new Promise<void>((resolve) => {
  resolveSettingsReady = resolve;
});

async function reconcileSettings(): Promise<void> {
  try {
    if (isInitialized()) {
      // The JSON file is authoritative — unblock the UI now, then push to the
      // backend in the background so its SQLite copy matches once it's up.
      resolveSettingsReady();
      void (async () => {
        if (await waitForService()) {
          await pushSettingsToService(readConfig());
        }
      })();
      return;
    }
    // First launch with electron-store present: migrate existing users by
    // pulling whatever the service DB already holds, so nobody loses settings.
    if (await waitForService()) {
      const fromService = await pullSettingsFromService();
      if (fromService) {
        writeConfig(fromService);
        markInitialized();
      }
    }
  } finally {
    resolveSettingsReady();
  }
}

function getServiceCwd(): string {
  const devPath = join(process.cwd(), "service");
  if (existsSync(devPath)) {
    return devPath;
  }
  return join(app.getAppPath(), "service");
}

function seedDatabaseIfNeeded(dataDir: string): void {
  // First run of the packaged app: copy the snapshot of the library DB bundled
  // at build time so sources/events/settings are present immediately. Later
  // runs keep the live DB under userData untouched.
  if (!app.isPackaged) {
    return;
  }
  const target = join(dataDir, "syncbox.sqlite3");
  const seed = join(process.resourcesPath, "seed", "syncbox.sqlite3");
  if (!existsSync(target) && existsSync(seed)) {
    mkdirSync(dataDir, { recursive: true });
    copyFileSync(seed, target);
    console.log(`[seed] copied bundled DB -> ${target}`);
  }
}

function startPythonService(): void {
  if (process.env.RBSYNC_EXTERNAL_SERVICE === "1" || serviceProcess) {
    return;
  }

  const dataDir = app.getPath("userData");
  seedDatabaseIfNeeded(dataDir);
  const env = {
    ...process.env,
    RBSYNC_DATA_DIR: dataDir,
    RBSYNC_SERVICE_PORT: String(servicePort),
    // Single source of version (package.json) + shared log directory so the
    // service writes where the "Open Logs" menu points.
    RBSYNC_APP_VERSION: app.getVersion(),
    RBSYNC_LOG_DIR: app.getPath("logs")
  };

  if (app.isPackaged) {
    // Standalone PyInstaller binary bundled under Resources/syncbox-service.
    const bin = join(process.resourcesPath, "syncbox-service", "syncbox-service");
    serviceProcess = spawn(bin, [], { env });
  } else {
    // Dev: run the service from source via uv.
    serviceProcess = spawn(
      "uv",
      [
        "run",
        "--group",
        "dev",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        String(servicePort)
      ],
      { cwd: getServiceCwd(), env }
    );
  }

  serviceProcess.stdout.on("data", (chunk) => {
    console.log(`[service] ${chunk.toString().trimEnd()}`);
  });
  serviceProcess.stderr.on("data", (chunk) => {
    console.error(`[service] ${chunk.toString().trimEnd()}`);
  });
  serviceProcess.on("exit", (code, signal) => {
    console.log(`[service] exited with code ${code ?? "none"} signal ${signal ?? "none"}`);
    serviceProcess = null;
  });
}

function stopPythonService(): void {
  if (!serviceProcess) {
    return;
  }
  serviceProcess.kill("SIGTERM");
  serviceProcess = null;
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 980,
    minHeight: 680,
    show: false,
    title: "Syncbox",
    icon: join(app.getAppPath(), "public/favicon.png"),
    backgroundColor: "#0d0d0d",
    // Hide the native title bar; keep the macOS traffic lights floating over
    // the app's dark sidebar. The renderer marks its top areas as draggable.
    titleBarStyle: "hiddenInset",
    trafficLightPosition: { x: 18, y: 24 },
    webPreferences: {
      preload: join(__dirname, "../preload/preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://") || url.startsWith("http://127.0.0.1")) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });

  if (process.env.ELECTRON_RENDERER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL);
  } else {
    mainWindow.loadFile(join(__dirname, "../renderer/index.html"));
  }
}

ipcMain.handle("app:get-api-base-url", () => apiBaseUrl);

// --- Settings bridge (electron-store) --------------------------------------
ipcMain.handle("settings:get", async () => {
  // Block only until the one-time migration has run; instant on every later boot.
  await settingsReady;
  return readConfig();
});
ipcMain.handle("settings:set", async (_event, partial: Partial<AppConfig>) => {
  // The renderer's saveSettings() already POSTed to the service (canonical
  // values + folder creation); here we just durably mirror the result so the
  // next cold start reads it without waiting for the backend.
  const config = writeConfig(partial);
  markInitialized();
  return config;
});
ipcMain.handle("settings:reload", async () => {
  // After a full-data import the service DB was replaced under us — re-pull so
  // the JSON mirror reflects the restored settings.
  const fromService = await pullSettingsFromService();
  if (fromService) {
    writeConfig(fromService);
    markInitialized();
  }
  return readConfig();
});
ipcMain.handle("app:open-external", async (_event, url: string) => {
  const parsed = new URL(url);
  if (!["https:", "http:"].includes(parsed.protocol)) {
    throw new Error("Unsupported URL protocol");
  }
  await shell.openExternal(url);
});
ipcMain.handle("app:open-path", async (_event, path: string) => {
  if (!isAbsolute(path)) {
    throw new Error("Only absolute paths can be opened");
  }
  const error = await shell.openPath(path);
  if (error) {
    throw new Error(error);
  }
});
ipcMain.handle("app:open-logs", async () => {
  const dir = app.getPath("logs");
  mkdirSync(dir, { recursive: true });
  await shell.openPath(dir);
  return dir;
});

// --- Deemix provisioning ---------------------------------------------------
ipcMain.handle("deemix:status", () => getDeemixStatus(app.getPath("home")));
ipcMain.handle("deemix:launch", async () => {
  const appPath = findDeemixApp(app.getPath("home"));
  if (!appPath) throw new Error("Deemix Remastered is not installed.");
  launchDeemix(appPath);
  return getDeemixStatus(app.getPath("home"));
});
ipcMain.handle("deemix:install", async (event) => {
  const status = await installDeemix(
    app.getPath("home"),
    (stage: string, percent: number | null) => {
      event.sender.send("deemix:progress", { stage, percent });
    }
  );
  return status;
});

function buildAppMenu(): void {
  const isMac = process.platform === "darwin";
  const template: Electron.MenuItemConstructorOptions[] = [
    ...(isMac
      ? [{ role: "appMenu" as const }]
      : []),
    { role: "editMenu" },
    { role: "viewMenu" },
    {
      label: "Help",
      submenu: [
        {
          label: "Open Logs",
          click: async () => {
            const dir = app.getPath("logs");
            mkdirSync(dir, { recursive: true });
            await shell.openPath(dir);
          }
        }
      ]
    }
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

app.whenReady().then(() => {
  buildAppMenu();
  startPythonService();
  void reconcileSettings();
  createWindow();
  void checkForUpdates();
  // Start the Deemix downloader in the background if it's installed, so its
  // local API (port 6595) is ready without the user launching it by hand.
  void ensureDeemixRunning(app.getPath("home"));

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  stopPythonService();
});
