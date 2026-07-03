/* Events store: event cards (with n_tracks + pending_delta) and the loaded
   event's staging tracks. Apply-vs-reapply is decided here: an event with a
   prior apply AND a pending delta re-applies; otherwise it applies. */

import { defineStore } from 'pinia'

import { api } from '../api/client'

export interface EventCard {
  id: number
  name: string
  slug: string
  status: string
  spotify_playlist_id: string | null
  default_tag: string
  staging_dir: string | null
  applied_at: string | null
  n_tracks: number
  pending_delta: number
}

export interface EventTrack {
  id: number
  event_id: number
  spotify_track_id: string | null
  title: string | null
  artist: string | null
  duration_ms: number | null
  isrc: string | null
  status: string
  content_id: string | null
  confidence: number | null
  staging_file_path: string | null
  added_after_apply: number
  prior_status: string | null
}

export interface EventDetail extends EventCard {
  tracks: EventTrack[]
}

export const useEventsStore = defineStore('events', {
  state: () => ({
    events: [] as EventCard[],
    current: null as EventDetail | null,
    loaded: false,
  }),
  getters: {
    /** counts for the workspace progress bar + filters */
    counts(): { ready: number; missing: number; pending: number; total: number } {
      const tracks = this.current?.tracks ?? []
      return {
        ready: tracks.filter((t) => t.status === 'ready' || t.status === 'imported').length,
        missing: tracks.filter((t) => t.status === 'missing').length,
        pending: tracks.filter((t) => t.added_after_apply === 1).length,
        total: tracks.length,
      }
    },
    /** true once an event has been applied (has a Rekordbox footprint) */
    hasPriorApply(): boolean {
      const status = this.current?.status
      return status === 'applied' || status === 'partially_applied'
    },
    /** the workspace CTA flips apply -> reapply on a prior apply + delta */
    isReapply(): boolean {
      return this.hasPriorApply && (this.current?.pending_delta ?? 0) > 0
    },
  },
  actions: {
    async loadEvents() {
      const { events } = await api.get<{ events: EventCard[] }>('/api/events')
      this.events = events
      this.loaded = true
    },
    async loadEvent(id: number) {
      this.current = await api.get<EventDetail>(`/api/events/${id}`)
      await this.refreshCard(id)
    },
    async refreshCard(id: number) {
      // keep the card counters (n_tracks/pending_delta) in sync with detail
      await this.loadEvents()
      const card = this.events.find((e) => e.id === id)
      if (card && this.current) {
        this.current.pending_delta = card.pending_delta
        this.current.n_tracks = card.n_tracks
        this.current.status = card.status
      }
    },
    async createEvent(name: string, opts: { spotify_playlist_id?: string; manual?: boolean }) {
      const event = await api.post<EventCard>('/api/events', { name, ...opts })
      await this.loadEvents()
      return event
    },
    async reload() {
      if (this.current) await this.loadEvent(this.current.id)
    },
  },
})
