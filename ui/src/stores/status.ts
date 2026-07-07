/* Status store (M4-PLAN §4): /api/status polled (interval + window focus +
   after any 423). RB banner, dashboard hero and "Rekordbox ouvert — bloqué"
   CTA variants ALL derive from here — no second source of truth. */

import { defineStore } from 'pinia'

import { NetworkError, api, setMutationBlockedHook } from '../api/client'
import { onBackendDown } from '../shell'

interface StatusPayload {
  rb_open: boolean
  spotify_connected: boolean
}

export const POLL_INTERVAL_MS = 30_000
/** The sidecar needs a couple of seconds to boot after the shell spawns it:
    quick retries absorb that window so launch never flashes the
    backend-down overlay (owner feedback 07/07). ~5 × 800 ms of grace. */
export const DOWN_AFTER_FAILURES = 5
export const RETRY_DELAY_MS = 800

export const useStatusStore = defineStore('status', {
  state: () => ({
    rbOpen: false,
    spotifyConnected: false,
    /** true once the supervisor exhausted its restarts (shell event) or the
        sidecar stops answering; the backend-down overlay reads this */
    backendDown: false,
    loaded: false,
    failures: 0,
  }),
  actions: {
    async refresh() {
      try {
        const status = await api.get<StatusPayload>('/api/status')
        this.rbOpen = status.rb_open
        this.spotifyConnected = status.spotify_connected
        this.backendDown = false
        this.failures = 0
        this.loaded = true
      } catch (error) {
        if (error instanceof NetworkError) {
          this.failures += 1
          if (this.failures >= DOWN_AFTER_FAILURES) this.backendDown = true
          // fast retry during the grace window (startup boot, blips)
          else setTimeout(() => void this.refresh(), RETRY_DELAY_MS)
        }
        /* ApiError: sidecar alive but unhappy — keep the last known status */
      }
    },
    /** Wire the poll loop + focus + 423 interceptor. Call once at app boot. */
    start() {
      setMutationBlockedHook(() => {
        this.rbOpen = true // immediate, then confirm
        void this.refresh()
      })
      onBackendDown(() => this.setBackendDown(true))
      window.addEventListener('focus', () => void this.refresh())
      setInterval(() => void this.refresh(), POLL_INTERVAL_MS)
      void this.refresh()
    },
    setBackendDown(down: boolean) {
      this.backendDown = down
    },
  },
})
