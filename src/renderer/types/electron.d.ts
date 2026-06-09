import type { AppSettings } from "../lib/api";

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
      openExternal: (url: string) => Promise<void>;
      openPath: (path: string) => Promise<void>;
      openLogs: () => Promise<string>;
      settings: {
        get: () => Promise<AppSettings>;
        set: (config: AppSettings) => Promise<AppSettings>;
        reload: () => Promise<AppSettings>;
      };
      deemix: {
        status: () => Promise<DeemixDesktopStatus>;
        launch: () => Promise<DeemixDesktopStatus>;
        install: () => Promise<DeemixDesktopStatus>;
        onProgress: (
          cb: (p: { stage: string; percent: number | null }) => void
        ) => () => void;
      };
    };
  }
}
