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

/** Reveal a local file's folder ("Ouvrir le dossier de logs") — same opener
    plugin; browser dev has no equivalent, so it degrades to a no-op. */
export async function revealInFolder(path: string): Promise<void> {
  try {
    const { revealItemInDir } = await import('@tauri-apps/plugin-opener')
    await revealItemInDir(path)
  } catch {
    /* browser dev: nothing sensible to open */
  }
}

/** Native file/folder pickers (Réglages + onboarding paths). Return null
    when cancelled — and in browser dev, where there is no dialog plugin. */
export async function pickFile(): Promise<string | null> {
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const picked = await open({ multiple: false, directory: false })
    return typeof picked === 'string' ? picked : null
  } catch {
    return null // browser dev: keyboard entry stays available
  }
}

export async function pickDirectory(): Promise<string | null> {
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const picked = await open({ multiple: false, directory: true })
    return typeof picked === 'string' ? picked : null
  } catch {
    return null
  }
}

/** True inside the Tauri shell — gates shell-only affordances (Parcourir…). */
export function hasShell(): boolean {
  return '__TAURI_INTERNALS__' in window
}

/** The shell emits `backend-down` when bounded restarts are exhausted. */
export function onBackendDown(handler: () => void): void {
  import('@tauri-apps/api/event')
    .then(({ listen }) => listen('backend-down', handler))
    .catch(() => {
      /* browser dev: NetworkError polling covers it */
    })
}
