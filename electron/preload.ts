import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("desktop", {
  getApiBaseUrl: () => ipcRenderer.invoke("app:get-api-base-url") as Promise<string>,
  getVersion: () => ipcRenderer.invoke("app:get-version") as Promise<string>,
  openExternal: (url: string) => ipcRenderer.invoke("app:open-external", url) as Promise<void>,
  openPath: (path: string) => ipcRenderer.invoke("app:open-path", path) as Promise<void>,
  openLogs: () => ipcRenderer.invoke("app:open-logs") as Promise<string>
});
