/* Bridge to the Tauri shell. Every call degrades gracefully in plain
   browser dev (pnpm dev without the shell): dynamic imports + fallbacks. */

/** Manual "Relancer" after the supervisor exhausted its restarts. */
export async function restartSidecar(): Promise<void> {
  try {
    const { invoke } = await import('@tauri-apps/api/core')
    await invoke('restart_sidecar')
  } catch {
    /* browser dev: no shell to ask */
  }
}

/** External links (purchase, Spotify authorize, logs folder) MUST go
    through the opener plugin — target=_blank is not a system browser in a
    webview (M4-PLAN §3). */
export async function openExternal(url: string): Promise<void> {
  try {
    const { openUrl } = await import('@tauri-apps/plugin-opener')
    await openUrl(url)
  } catch {
    window.open(url, '_blank', 'noopener') // browser dev fallback
  }
}

/** The shell emits `backend-down` when bounded restarts are exhausted. */
export function onBackendDown(handler: () => void): void {
  import('@tauri-apps/api/event')
    .then(({ listen }) => listen('backend-down', handler))
    .catch(() => {
      /* browser dev: NetworkError polling covers it */
    })
}
