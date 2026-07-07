/* Pure helpers for the Events workspace (M4.8) — counts drive the segmented
   progress bar and the apply/reapply CTA, so they get direct unit tests. */

import type { EventTrack } from '../api/types'

/** Track statuses that read as "prêt" (mockup family). */
export const READY_FAMILY = new Set(['matched', 'ready', 'imported'])

/** Event lifecycle: applied/partially_applied stay open to additions (§11.2). */
export function isBaseApplied(status: string): boolean {
  return status === 'applied' || status === 'partially_applied'
}

export interface EventCounts {
  total: number
  ready: number
  missing: number
  ambiguous: number
  /** §11.2 delta: rows added after the last apply */
  pending: number
  pendReady: number
  pendMissing: number
}

export function eventCounts(tracks: EventTrack[]): EventCounts {
  const pendingRows = tracks.filter((track) => track.added_after_apply === 1)
  return {
    total: tracks.length,
    ready: tracks.filter((track) => READY_FAMILY.has(track.status)).length,
    missing: tracks.filter((track) => track.status === 'missing').length,
    ambiguous: tracks.filter((track) => track.status === 'ambiguous').length,
    pending: pendingRows.length,
    pendReady: pendingRows.filter((track) => READY_FAMILY.has(track.status)).length,
    pendMissing: pendingRows.filter((track) => track.status === 'missing').length,
  }
}

export const EVENT_FILTERS = ['all', 'ready', 'missing', 'ambiguous', 'pending'] as const
export type EventFilter = (typeof EVENT_FILTERS)[number]

export function filterEventTracks(tracks: EventTrack[], chip: EventFilter): EventTrack[] {
  const predicate: Record<EventFilter, (track: EventTrack) => boolean> = {
    all: () => true,
    ready: (track) => READY_FAMILY.has(track.status),
    missing: (track) => track.status === 'missing',
    ambiguous: (track) => track.status === 'ambiguous',
    pending: (track) => track.added_after_apply === 1,
  }
  // §11.2: pending (unapplied) additions sort to the top of the table
  return tracks
    .filter(predicate[chip])
    .sort((a, b) => b.added_after_apply - a.added_after_apply || a.id - b.id)
}
