import { ipcMain, app, shell, BrowserWindow, Menu } from "electron";
import { spawn } from "node:child_process";
import { mkdirSync, existsSync, copyFileSync } from "node:fs";
import { isAbsolute, join } from "node:path";
import __cjs_mod__ from "node:module";
const __filename = import.meta.filename;
const __dirname = import.meta.dirname;
const require2 = __cjs_mod__.createRequire(import.meta.url);
async function checkForUpdates() {
  if (!app.isPackaged || process.env.RBSYNC_ENABLE_UPDATES !== "1") {
    return;
  }
  try {
    const { autoUpdater } = await import("electron-updater");
    autoUpdater.logger = console;
    autoUpdater.autoDownload = true;
    await autoUpdater.checkForUpdatesAndNotify();
  } catch (error) {
    console.warn("[updater] skipped:", error.message);
  }
}
let mainWindow = null;
let serviceProcess = null;
const servicePort = Number(process.env.RBSYNC_SERVICE_PORT ?? "8765");
const apiBaseUrl = `http://127.0.0.1:${servicePort}`;
function getServiceCwd() {
  const devPath = join(process.cwd(), "service");
  if (existsSync(devPath)) {
    return devPath;
  }
  return join(app.getAppPath(), "service");
}
function seedDatabaseIfNeeded(dataDir) {
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
function startPythonService() {
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
    const bin = join(process.resourcesPath, "syncbox-service", "syncbox-service");
    serviceProcess = spawn(bin, [], { env });
  } else {
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
function stopPythonService() {
  if (!serviceProcess) {
    return;
  }
  serviceProcess.kill("SIGTERM");
  serviceProcess = null;
}
function createWindow() {
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
ipcMain.handle("app:get-version", () => app.getVersion());
ipcMain.handle("app:open-external", async (_event, url) => {
  const parsed = new URL(url);
  if (!["https:", "http:"].includes(parsed.protocol)) {
    throw new Error("Unsupported URL protocol");
  }
  await shell.openExternal(url);
});
ipcMain.handle("app:open-path", async (_event, path) => {
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
function buildAppMenu() {
  const isMac = process.platform === "darwin";
  const template = [
    ...isMac ? [{ role: "appMenu" }] : [],
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
  createWindow();
  void checkForUpdates();
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
