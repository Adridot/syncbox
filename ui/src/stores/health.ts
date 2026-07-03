/* THE canonical health selector (SPEC-DESIGN §3.4, corrects T4/T5).
   Sidebar badges, dashboard tiles, health-hub tab badges and the HealthPill
   ALL derive from the getters below — there is exactly ONE definition of
   "connected", "ready" and "active" in the app. Domain screens push their
   counts here; null = not known yet (tiles show "—" + a scan affordance:
   the duplicates scan is never auto-run, it locks the whole API). */

import { defineStore } from 'pinia'

import { api } from '../api/client'
import { useJobsStore } from './jobs'
import { useStatusStore } from './status'

export type PillTone = 'ok' | 'warn' | 'idle'

export const useHealthStore = defineStore('health', {
  state: () => ({
    /** last duplicates scan result — never auto-scanned on mount */
    duplicateGroups: null as number | null,
    missingCounts: null as { library: number; event: number; collection: number } | null,
    untaggedCount: null as number | null,
    /** library rows needing review (new/conflict/missing), per source total */
    libraryReviewCount: null as number | null,
    /** events with a pending delta or ready work */
    eventsAttentionCount: null as number | null,
  }),
  getters: {
    /* the ONE definition of each state (HealthPill + everywhere else) */
    spotifyConnected(): boolean {
      return useStatusStore().spotifyConnected
    },
    rekordboxReady(): boolean {
      return !useStatusStore().rbOpen
    },
    jobsActive(): boolean {
      return useJobsStore().jobRunning
    },
    pill(): { spotify: PillTone; rekordbox: PillTone; jobs: PillTone } {
      return {
        spotify: this.spotifyConnected ? 'ok' : 'idle',
        rekordbox: this.rekordboxReady ? 'ok' : 'warn',
        jobs: this.jobsActive ? 'ok' : 'idle',
      }
    },
    missingTotal(): number | null {
      if (this.missingCounts === null) return null
      const { library, event, collection } = this.missingCounts
      return library + event + collection
    },
    /* nav + health-tab badges (null -> no badge / em dash on tiles) */
    badges(): {
      library: number | null
      events: number | null
      missing: number | null
      duplicates: number | null
      untagged: number | null
    } {
      return {
        library: this.libraryReviewCount,
        events: this.eventsAttentionCount,
        missing: this.missingTotal,
        duplicates: this.duplicateGroups,
        untagged: this.untaggedCount,
      }
    },
  },
  actions: {
    /** Cheap read-only counts (missing scopes + untagged). Caller must gate
        on settings.configured (400 otherwise). The duplicates scan is NEVER
        run here — it locks the whole API (M4-PLAN §4). */
    async loadCounts() {
      const [library, event, collection, untagged] = await Promise.all([
        api.get<{ entries: unknown[] }>('/api/missing/library'),
        api.get<{ entries: unknown[] }>('/api/missing/event'),
        api.get<{ entries: unknown[] }>('/api/missing/collection'),
        api.get<{ tracks: unknown[] }>('/api/untagged'),
      ])
      this.setMissingCounts({
        library: library.entries.length,
        event: event.entries.length,
        collection: collection.entries.length,
      })
      this.setUntaggedCount(untagged.tracks.length)
    },
    setDuplicateGroups(count: number) {
      this.duplicateGroups = count
    },
    setMissingCounts(counts: { library: number; event: number; collection: number }) {
      this.missingCounts = counts
    },
    setUntaggedCount(count: number) {
      this.untaggedCount = count
    },
    setLibraryReviewCount(count: number) {
      this.libraryReviewCount = count
    },
    setEventsAttentionCount(count: number) {
      this.eventsAttentionCount = count
    },
  },
})
