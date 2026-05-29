import { app, BrowserWindow, ipcMain, shell } from "electron";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync } from "node:fs";
import { isAbsolute, join } from "node:path";

let mainWindow: BrowserWindow | null = null;
let serviceProcess: ChildProcessWithoutNullStreams | null = null;

const servicePort = Number(process.env.RBSYNC_SERVICE_PORT ?? "8765");
const apiBaseUrl = `http://127.0.0.1:${servicePort}`;

function getServiceCwd(): string {
  const devPath = join(process.cwd(), "service");
  if (existsSync(devPath)) {
    return devPath;
  }
  return join(app.getAppPath(), "service");
}

function startPythonService(): void {
  if (process.env.RBSYNC_EXTERNAL_SERVICE === "1" || serviceProcess) {
    return;
  }

  const cwd = getServiceCwd();
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
    {
      cwd,
      env: {
        ...process.env,
        RBSYNC_DATA_DIR: app.getPath("userData")
      }
    }
  );

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
    title: "Rekordbox Sync Studio",
    backgroundColor: "#f7f8fb",
    webPreferences: {
      preload: join(__dirname, "../preload/preload.mjs"),
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

app.whenReady().then(() => {
  startPythonService();
  createWindow();

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
