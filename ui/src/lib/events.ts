/* Pure helpers for the Events workspace (M4.8) — counts drive the segmented
   progress bar and the apply/reapply CTA, so they get direct unit tests. */

import type { EventTrack } from '../api/types'

/** Statuses the (re)apply pipeline will actually write next run — i.e. what
    reads as "prêt (à appliquer)". 'applied' is NOT here: a row already in
    Rekordbox is done, counted separately (owner feedback 07/07: applied
    tracks must not inflate the "prêts" count). */
export const APPLIABLE = new Set(['matched', 'ready'])
export const READY_FAMILY = APPLIABLE
const MISSING_FAMILY = new Set(['missing', 'acquisition_failed'])

/** Rows that are outstanding work for nobody — excluded here, ONCE, which
    keeps them out of every count AND every filter chip but the one that opts
    each back in:

    - §5.7 adoption: an `ignored` row is an adopted track the user rejected.
      It survives only so its staged file stays referenced and is not adopted
      again on the next claim — never matched, claimed nor applied.
    - playlist refresh: a `removed_upstream` row left the Spotify playlist.
      Nothing was written and nothing will be — it is a signal awaiting the
      user's decision, which is why it must never inflate the pending delta.
    - track removal: a `removed` row was withdrawn from the event by an
      executed removal. The decision is made and done; the row survives only
      so a staged file that was NOT trashed stays referenced (design.md
      "The removed track's row"). */
const SIDELINED = new Set(['ignored', 'removed_upstream', 'removed'])
const isCounted = (track: EventTrack) => !SIDELINED.has(track.status)

/** Event lifecycle: applied/partially_applied stay open to additions (§11.2). */
export function isBaseApplied(status: string): boolean {
  return status === 'applied' || status === 'partially_applied'
}

export interface EventCounts {
  total: number
  /** matched/ready — to apply next run */
  ready: number
  /** already in Rekordbox */
  applied: number
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
export function eventCounts(all: EventTrack[], baseApplied = false): EventCounts {
  const tracks = all.filter(isCounted)
  const pendReady = baseApplied
    ? tracks.filter((track) => APPLIABLE.has(track.status)).length
    : 0
  const pendMissing = baseApplied
    ? tracks.filter(
        (track) => track.added_after_apply === 1 && MISSING_FAMILY.has(track.status),
      ).length
    : 0
  return {
    total: tracks.length,
    ready: tracks.filter((track) => APPLIABLE.has(track.status)).length,
    applied: tracks.filter((track) => track.status === 'applied').length,
    missing: tracks.filter((track) => MISSING_FAMILY.has(track.status)).length,
    ambiguous: tracks.filter((track) => track.status === 'ambiguous').length,
    pending: pendReady + pendMissing,
    pendReady,
    pendMissing,
  }
}

// the two SIDELINED chips last: each is the only way back to its own rows,
// and the toolbar only shows it once there IS something to consult
export const EVENT_FILTERS = [
  'all',
  'ready',
  'missing',
  'ambiguous',
  'pending',
  'ignored',
  'removed',
] as const
export type EventFilter = (typeof EVENT_FILTERS)[number]

export function filterEventTracks(tracks: EventTrack[], chip: EventFilter): EventTrack[] {
  const predicate: Record<EventFilter, (track: EventTrack) => boolean> = {
    all: () => true,
    ready: (track) => READY_FAMILY.has(track.status),
    missing: (track) => MISSING_FAMILY.has(track.status),
    ambiguous: (track) => track.status === 'ambiguous',
    // pending = will be written next (re)apply, or added since the last one
    pending: (track) => APPLIABLE.has(track.status) || track.added_after_apply === 1,
    // §5.7 "A rejection can be undone": rejected rows stay reachable, here
    // and nowhere else
    ignored: (track) => track.status === 'ignored',
    // same deal for a departure: its chip is the one place to decide on it
    removed: (track) => track.status === 'removed_upstream',
  }
  // a SIDELINED chip opts its own rows back in — and only its own, since its
  // predicate matches nothing else
  return tracks
    .filter(
      (track) =>
        (isCounted(track) || chip === 'ignored' || chip === 'removed') &&
        predicate[chip](track),
    )
    // §11.2: pending (unapplied) additions sort to the top of the table
    .sort((a, b) => b.added_after_apply - a.added_after_apply || a.id - b.id)
}
