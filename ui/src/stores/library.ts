/* Library store: sources master list + the selected source's review tracks.
   Review count per source = rows in new/conflict/missing (the states that
   need attention); pushed into the canonical health selector. */

import { defineStore } from 'pinia'

import { api } from '../api/client'

export interface Source {
  id: number
  spotify_playlist_id: string
  name: string
  tags: string[]
  enabled: number
  status: string | null
  snapshot_id: string | null
}

export interface LibraryTrack {
  id: number
  spotify_track_id: string
  title: string
  artist: string
  duration_ms: number | null
  isrc: string | null
  status: string
  content_id: string | null
  match_method: string | null
  confidence: number | null
  tags: string[]
}

const REVIEW_STATES = new Set(['new', 'conflict', 'missing'])

export const useLibraryStore = defineStore('library', {
  state: () => ({
    sources: [] as Source[],
    /** review tracks per source id, cached as loaded */
    tracksBySource: {} as Record<number, LibraryTrack[]>,
    loadedSources: false,
  }),
  getters: {
    reviewCountOf: (state) => (sourceId: number) =>
      (state.tracksBySource[sourceId] ?? []).filter((t) => REVIEW_STATES.has(t.status))
        .length,
    /** every track across sources, for the "Toutes les sources" aggregate */
    allTracks: (state) =>
      Object.entries(state.tracksBySource).flatMap(([sourceId, tracks]) =>
        tracks.map((track) => ({ ...track, sourceId: Number(sourceId) })),
      ),
    /** union of tags already used (source defaults + track tags) — the
        TagPicker catalog; the user can also type a fresh tag */
    knownTags(): string[] {
      const set = new Set<string>()
      this.sources.forEach((source) => source.tags.forEach((tag) => set.add(tag)))
      Object.values(this.tracksBySource).forEach((tracks) =>
        tracks.forEach((track) => track.tags.forEach((tag) => set.add(tag))),
      )
      return [...set].sort()
    },
  },
  actions: {
    async loadSources() {
      const { sources } = await api.get<{ sources: Source[] }>('/api/sources')
      this.sources = sources
      this.loadedSources = true
      await Promise.all(sources.map((source) => this.loadTracks(source.id)))
    },
    async loadTracks(sourceId: number) {
      const { tracks } = await api.get<{ tracks: LibraryTrack[] }>(
        `/api/sources/${sourceId}/tracks`,
      )
      this.tracksBySource[sourceId] = tracks
    },
    async addSource(playlistId: string, name: string, tags: string[]) {
      const source = await api.post<Source>('/api/sources', {
        spotify_playlist_id: playlistId,
        name,
        tags,
      })
      this.sources.push(source)
      this.tracksBySource[source.id] = []
      return source
    },
    replaceTrack(sourceId: number, updated: LibraryTrack) {
      const tracks = this.tracksBySource[sourceId]
      if (!tracks) return
      const index = tracks.findIndex((track) => track.id === updated.id)
      if (index >= 0) tracks[index] = updated
    },
  },
})
