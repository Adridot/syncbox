import { onActivated, onMounted } from 'vue'

/** True when two payloads are structurally identical — silent refreshes use
    this to SKIP replacing refs (and re-rendering big tables) for identical
    data. ponytail: JSON round-trip compare, fine for our payload sizes. */
export function sameData(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

/** Load on mount, then refresh silently on every keep-alive re-entry.
    Inside <keep-alive>, activation follows mount immediately — that first
    activation is skipped so the initial load runs once. Outside keep-alive
    (unit tests, one-off mounts) it degrades to a plain onMounted load. */
export function useRefreshOnReturn(load: () => void | Promise<void>): void {
  let justMounted = false
  onMounted(() => {
    justMounted = true
    return load()
  })
  onActivated(() => {
    if (justMounted) {
      justMounted = false
      return
    }
    return load()
  })
}
