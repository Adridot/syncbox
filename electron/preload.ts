import { contextBridge, ipcRenderer, type IpcRendererEvent } from "electron";

contextBridge.exposeInMainWorld("desktop", {
  getApiBaseUrl: () => ipcRenderer.invoke("app:get-api-base-url") as Promise<string>,
  openExternal: (url: string) => ipcRenderer.invoke("app:open-external", url) as Promise<void>,
  openPath: (path: string) => ipcRenderer.invoke("app:open-path", path) as Promise<void>,
  openLogs: () => ipcRenderer.invoke("app:open-logs") as Promise<string>,
  settings: {
    get: () => ipcRenderer.invoke("settings:get"),
    set: (config: unknown) => ipcRenderer.invoke("settings:set", config),
    reload: () => ipcRenderer.invoke("settings:reload"),
  },
  deemix: {
    status: () => ipcRenderer.invoke("deemix:status"),
    launch: () => ipcRenderer.invoke("deemix:launch"),
    install: () => ipcRenderer.invoke("deemix:install"),
    onProgress: (cb: (p: { stage: string; percent: number | null }) => void) => {
      const handler = (_e: IpcRendererEvent, payload: { stage: string; percent: number | null }) =>
        cb(payload);
      ipcRenderer.on("deemix:progress", handler);
      return () => ipcRenderer.removeListener("deemix:progress", handler);
    }
  }
});
