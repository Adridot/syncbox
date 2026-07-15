/* Status store (M4-PLAN §4): /api/status polled (interval + window focus +
   after any 423). RB banner, dashboard hero and "Rekordbox ouvert — bloqué"
   CTA variants ALL derive from here — no second source of truth. */

import { defineStore } from 'pinia'

import { NetworkError, api, setMutationBlockedHook } from '../api/client'
import { onBackendDown } from '../shell'

interface StatusPayload {
  rb_open: boolean
  spotify_connected: boolean
  spotify_authorization_pending?: boolean
  spotify_authorization_result?: 'ok' | 'error' | 'expired' | null
}

export const POLL_INTERVAL_MS = 30_000
/** The frozen sidecar measured 8.2 s on its first cold start. Quick retries
    give it a 12 s startup window; the shell event still reports exhausted
    restarts immediately. */
export const DOWN_AFTER_FAILURES = 15
export const RETRY_DELAY_MS = 800

export const useStatusStore = defineStore('status', {
  state: () => ({
    rbOpen: false,
    spotifyConnected: false,
    spotifyAuthorizationPending: false,
    spotifyAuthorizationResult: null as 'ok' | 'error' | 'expired' | null,
    /** true once the supervisor exhausted its restarts (shell event) or the
        sidecar stops answering; the backend-down overlay reads this */
    backendDown: false,
    backendDownReason: null as string | null,
    loaded: false,
    failures: 0,
  }),
  actions: {
    async refresh() {
      try {
        const status = await api.get<StatusPayload>('/api/status')
        this.rbOpen = status.rb_open
        this.spotifyConnected = status.spotify_connected
        this.spotifyAuthorizationPending = Boolean(status.spotify_authorization_pending)
        this.spotifyAuthorizationResult = status.spotify_authorization_result ?? null
        this.backendDown = false
        this.backendDownReason = null
        this.failures = 0
        this.loaded = true
      } catch (error) {
        if (error instanceof NetworkError) {
          this.failures += 1
          if (this.failures >= DOWN_AFTER_FAILURES) {
            this.backendDown = true
            this.backendDownReason = 'unreachable'
          }
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
      onBackendDown((reason) => this.setBackendDown(true, reason))
      window.addEventListener('focus', () => void this.refresh())
      setInterval(() => void this.refresh(), POLL_INTERVAL_MS)
      void this.refresh()
    },
    setBackendDown(down: boolean, reason: string | null = null) {
      this.backendDown = down
      this.backendDownReason = down ? reason : null
    },
  },
})
