/* Missing store: entries per scope (library/event/collection). Shared by the
   Missing center (M4.10) and the health hub's "Fichiers manquants" tab. */

import { defineStore } from 'pinia'

import { api } from '../api/client'

export interface RelinkCandidate {
  path: string
  score: number
  format: string
  duration_s?: number
}

export interface MissingEntry {
  scope: 'library' | 'event' | 'collection'
  id: number | string
  content_id: string | null
  title: string
  artist: string
  isrc: string | null
  status: string
  file_path?: string
  purchase_links: Array<{ store: string; url: string }>
  relink_candidates: RelinkCandidate[]
}

export const useMissingStore = defineStore('missing', {
  state: () => ({
    byScope: {} as Record<string, MissingEntry[]>,
  }),
  actions: {
    async load(scope: 'library' | 'event' | 'collection') {
      const { entries } = await api.get<{ entries: MissingEntry[] }>(`/api/missing/${scope}`)
      this.byScope[scope] = entries
      return entries
    },
    /** counts for the canonical health selector */
    async loadCounts() {
      const [library, event, collection] = await Promise.all([
        this.load('library'),
        this.load('event'),
        this.load('collection'),
      ])
      return { library: library.length, event: event.length, collection: collection.length }
    },
  },
})
