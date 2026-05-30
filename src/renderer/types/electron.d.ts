export {};

declare global {
  interface Window {
    desktop?: {
      getApiBaseUrl: () => Promise<string>;
      getVersion: () => Promise<string>;
      openExternal: (url: string) => Promise<void>;
      openPath: (path: string) => Promise<void>;
      openLogs: () => Promise<string>;
    };
    syncboxStopAutoRefresh?: () => void;
  }
}
