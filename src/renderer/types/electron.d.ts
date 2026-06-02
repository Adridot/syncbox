export {};

export type DeemixDesktopStatus = {
  installed: boolean;
  running: boolean;
  appPath: string | null;
  port: number;
};

declare global {
  interface Window {
    desktop?: {
      getApiBaseUrl: () => Promise<string>;
      getVersion: () => Promise<string>;
      openExternal: (url: string) => Promise<void>;
      openPath: (path: string) => Promise<void>;
      openLogs: () => Promise<string>;
      deemix: {
        status: () => Promise<DeemixDesktopStatus>;
        launch: () => Promise<DeemixDesktopStatus>;
        install: () => Promise<DeemixDesktopStatus>;
        onProgress: (
          cb: (p: { stage: string; percent: number | null }) => void
        ) => () => void;
      };
    };
    syncboxStopAutoRefresh?: () => void;
  }
}
