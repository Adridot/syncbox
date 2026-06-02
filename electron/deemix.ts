import { execFile, execFileSync, spawn } from "node:child_process";
import { createWriteStream, existsSync, mkdirSync, rmSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";

// Syncbox drives Deemix Remastered over its local REST API; this module just
// makes sure that app is present and running so the user never has to launch
// (or even download) it by hand.

export const DEEMIX_PORT = 6595;
const DEEMIX_APP_NAME = "Deemix Remastered.app";
const RELEASES_API = "https://api.github.com/repos/DRAZY/deemix-remastered/releases/latest";

export interface DeemixStatus {
  installed: boolean;
  running: boolean;
  appPath: string | null;
  port: number;
}

export type ProgressFn = (stage: string, percent: number | null) => void;

function candidatePaths(homeDir: string): string[] {
  return [
    join("/Applications", DEEMIX_APP_NAME),
    join(homeDir, "Applications", DEEMIX_APP_NAME),
  ];
}

export function findDeemixApp(homeDir: string): string | null {
  return candidatePaths(homeDir).find((p) => existsSync(p)) ?? null;
}

export async function isDeemixRunning(): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 1500);
  try {
    const response = await fetch(`http://127.0.0.1:${DEEMIX_PORT}/api/health`, {
      signal: controller.signal,
    });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

export function launchDeemix(appPath: string): void {
  // `-g` keeps it in the background (no window stealing focus); it just needs to
  // serve the local API on 6595.
  spawn("open", ["-g", appPath], { detached: true, stdio: "ignore" }).unref();
}

export async function getDeemixStatus(homeDir: string): Promise<DeemixStatus> {
  const appPath = findDeemixApp(homeDir);
  return {
    installed: appPath !== null,
    running: await isDeemixRunning(),
    appPath,
    port: DEEMIX_PORT,
  };
}

/** On startup: if Deemix is installed but not running, launch it in the background. */
export async function ensureDeemixRunning(homeDir: string): Promise<void> {
  if (await isDeemixRunning()) return;
  const appPath = findDeemixApp(homeDir);
  if (appPath) {
    console.log(`[deemix] launching ${appPath}`);
    launchDeemix(appPath);
  }
}

async function fetchLatestDmgAsset(): Promise<{ name: string; url: string }> {
  const response = await fetch(RELEASES_API, {
    headers: { "User-Agent": "Syncbox", Accept: "application/vnd.github+json" },
  });
  if (!response.ok) {
    throw new Error(`GitHub releases unavailable (HTTP ${response.status}).`);
  }
  const release = (await response.json()) as {
    assets?: Array<{ name: string; browser_download_url: string }>;
  };
  const assets = release.assets ?? [];
  const dmgs = assets.filter((a) => a.name.toLowerCase().endsWith(".dmg"));
  const wantArm = process.arch === "arm64";
  const pick =
    (wantArm ? dmgs.find((a) => a.name.includes("arm64")) : undefined) ??
    dmgs.find((a) => a.name.toLowerCase().includes("universal")) ??
    dmgs[0];
  if (!pick) throw new Error("No macOS .dmg in the latest Deemix release.");
  return { name: pick.name, url: pick.browser_download_url };
}

async function downloadFile(url: string, dest: string, onProgress: ProgressFn): Promise<void> {
  const response = await fetch(url, { headers: { "User-Agent": "Syncbox" } });
  if (!response.ok || !response.body) {
    throw new Error(`Download failed (HTTP ${response.status}).`);
  }
  const total = Number(response.headers.get("content-length") ?? "0");
  let received = 0;
  const source = Readable.fromWeb(response.body as never);
  source.on("data", (chunk: Buffer) => {
    received += chunk.length;
    onProgress("Downloading Deemix…", total ? Math.round((received / total) * 100) : null);
  });
  await pipeline(source, createWriteStream(dest));
}

/**
 * Download the latest Deemix Remastered .dmg, mount it, copy the app into
 * ~/Applications, unmount, and launch it. macOS only.
 */
export async function installDeemix(
  homeDir: string,
  onProgress: ProgressFn
): Promise<DeemixStatus> {
  if (process.platform !== "darwin") {
    throw new Error("Automatic install is only supported on macOS.");
  }
  onProgress("Finding the latest release…", null);
  const asset = await fetchLatestDmgAsset();

  const tmpDmg = join(tmpdir(), asset.name);
  await downloadFile(asset.url, tmpDmg, onProgress);

  const mountPoint = join(tmpdir(), `deemix-mnt-${Date.now()}`);
  onProgress("Installing…", null);
  try {
    execFileSync("hdiutil", [
      "attach",
      tmpDmg,
      "-nobrowse",
      "-noverify",
      "-mountpoint",
      mountPoint,
    ]);
    try {
      const srcApp = join(mountPoint, DEEMIX_APP_NAME);
      if (!existsSync(srcApp)) {
        throw new Error("The downloaded disk image did not contain Deemix Remastered.");
      }
      const destDir = join(homeDir, "Applications");
      mkdirSync(destDir, { recursive: true });
      const destApp = join(destDir, DEEMIX_APP_NAME);
      rmSync(destApp, { recursive: true, force: true });
      // ditto preserves the app bundle's signature/metadata better than cp.
      execFileSync("ditto", [srcApp, destApp]);
      onProgress("Launching Deemix…", 100);
      launchDeemix(destApp);
      return { installed: true, running: true, appPath: destApp, port: DEEMIX_PORT };
    } finally {
      execFile("hdiutil", ["detach", mountPoint, "-force"], () => undefined);
    }
  } finally {
    try {
      unlinkSync(tmpDmg);
    } catch {
      /* best effort */
    }
  }
}
