/* Pure helpers for the Events workspace (M4.8) — counts drive the segmented
   progress bar and the apply/reapply CTA, so they get direct unit tests. */

import type { EventTrack } from '../api/types'

/** Track statuses that read as "prêt" (mockup family). 'applied' is what the
    apply pipeline writes — the events vocabulary has no 'imported'. */
export const READY_FAMILY = new Set(['matched', 'ready', 'applied'])

/** Statuses the (re)apply pipeline will actually write next run. */
export const APPLIABLE = new Set(['matched', 'ready'])

/** Event lifecycle: applied/partially_applied stay open to additions (§11.2). */
export function isBaseApplied(status: string): boolean {
  return status === 'applied' || status === 'partially_applied'
}

export interface EventCounts {
  total: number
  ready: number
  missing: number
  ambiguous: number
  /** changes since the last apply: reappliable rows + new still-missing rows */
  pending: number
  pendReady: number
  pendMissing: number
}

/** ``baseApplied``: the 11.2 delta only exists once the event was applied —
    on it, EVERY matched/ready row is a pending change (owner bug report
    2026-07-07: a row matched after the apply was stuck un-reappliable). */
export function eventCounts(tracks: EventTrack[], baseApplied = false): EventCounts {
  const pendReady = baseApplied
    ? tracks.filter((track) => APPLIABLE.has(track.status)).length
    : 0
  const pendMissing = baseApplied
    ? tracks.filter(
        (track) => track.added_after_apply === 1 && track.status === 'missing',
      ).length
    : 0
  return {
    total: tracks.length,
    ready: tracks.filter((track) => READY_FAMILY.has(track.status)).length,
    missing: tracks.filter((track) => track.status === 'missing').length,
    ambiguous: tracks.filter((track) => track.status === 'ambiguous').length,
    pending: pendReady + pendMissing,
    pendReady,
    pendMissing,
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
    // pending = will be written next (re)apply, or added since the last one
    pending: (track) => APPLIABLE.has(track.status) || track.added_after_apply === 1,
  }
  // §11.2: pending (unapplied) additions sort to the top of the table
  return tracks
    .filter(predicate[chip])
    .sort((a, b) => b.added_after_apply - a.added_after_apply || a.id - b.id)
}
