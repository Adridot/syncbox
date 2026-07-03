/* Jobs store (M4-PLAN §4): the single SSE stream lands here. JobRow progress
   only ever reads `pct` from this store (F16 — never tone/status). The
   app-wide jobRunning flag (mutating CTAs disabled while ANY job runs — one
   sidecar lock) combines SSE-active jobs and in-flight HTTP mutations. */

import { defineStore } from 'pinia'

import { onInFlightMutations } from '../api/client'
import { connectJobStream, type JobDoneEvent, type JobProgressEvent } from '../api/sse'

export const useJobsStore = defineStore('jobs', {
  state: () => ({
    /** one job of a kind at a time (sidecar lock) — keyed by kind */
    active: {} as Record<string, JobProgressEvent>,
    /** last job.done summaries, feeds the UI-local activity feed */
    lastDone: {} as Record<string, JobDoneEvent>,
    doneLog: [] as Array<JobDoneEvent & { at: number }>,
    inFlightMutations: 0,
    sseConnected: false,
  }),
  getters: {
    jobRunning: (state) =>
      state.inFlightMutations > 0 || Object.keys(state.active).length > 0,
    progressOf: (state) => (kind: string) => state.active[kind] ?? null,
  },
  actions: {
    /** Call once at app boot. */
    start() {
      onInFlightMutations((count) => {
        this.inFlightMutations = count
      })
      connectJobStream({
        onProgress: (event) => {
          this.active[event.kind] = event
        },
        onDone: (event) => {
          delete this.active[event.kind]
          this.lastDone[event.kind] = event
          this.doneLog.push({ ...event, at: Date.now() })
        },
        onOpen: () => {
          // no replay after reconnect: anything still "active" is stale —
          // the HTTP response (or a re-fetch) is the authority.
          this.sseConnected = true
          this.active = {}
        },
        onError: () => {
          this.sseConnected = false
          this.active = {}
        },
      })
    },
  },
})
