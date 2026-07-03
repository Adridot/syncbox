/* Duplicates store: the spectral scan LOCKS the whole API, so it is never
   auto-run on mount — the tab shows a scan CTA until a scan has run
   (M4-PLAN §4). The scan's fingerprint is echoed back to resolve verbatim so
   the mutate freshness guard covers exactly what was displayed. */

import { defineStore } from 'pinia'

import { api } from '../api/client'

export interface DuplicateMember {
  content_id: string
  title: string
  artist: string
  bit_rate: number | null
  resolved_path: string | null
  file_missing: boolean
  playlist_count: number
  cue_count: number
  quality_verdict: 'ok' | 'lossy_source_probable' | 'incertain'
  quality_reason: string
}

export interface DuplicateGroup {
  key: string
  method: string
  confidence: number
  warning: boolean
  members: DuplicateMember[]
  keeper: { content_id: string; reason: string }
}

export const useDuplicatesStore = defineStore('duplicates', {
  state: () => ({
    groups: null as DuplicateGroup[] | null,
    fingerprint: null as unknown,
    scanning: false,
  }),
  actions: {
    async scan() {
      this.scanning = true
      try {
        const result = await api.post<{ groups: DuplicateGroup[]; fingerprint: unknown }>(
          '/api/duplicates/scan',
        )
        this.groups = result.groups
        this.fingerprint = result.fingerprint
      } finally {
        this.scanning = false
      }
    },
    async resolve(keeperContentId: string, loserContentIds: string[]) {
      // fingerprint echoed verbatim; a 409 stale_snapshot -> re-scan.
      await api.post('/api/duplicates/resolve', {
        keeper_content_id: keeperContentId,
        loser_content_ids: loserContentIds,
        fingerprint: this.fingerprint,
      })
      // drop the resolved group locally; the store never auto-rescans
      this.groups = (this.groups ?? []).filter((g) => g.keeper.content_id !== keeperContentId)
    },
    async dismiss(groupKey: string) {
      await api.post('/api/duplicates/dismiss', { group_key: groupKey })
      this.groups = (this.groups ?? []).filter((g) => g.key !== groupKey)
    },
  },
})
