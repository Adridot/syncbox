/* Pure helpers for the Library review surface (M4.7) — kept out of the
   component so the filter/selection rules have direct unit tests. */

import type { LibraryTrack } from '../api/types'

/** Rows that need the user's attention — the ONE review definition the
    source badges and the health selector share. */
export const REVIEW_STATUSES = new Set(['new', 'conflict', 'missing'])

export function isReview(track: LibraryTrack): boolean {
  return REVIEW_STATUSES.has(track.status)
}

export const FILTER_CHIPS = [
  'all',
  'matched',
  'conflict',
  'ready',
  'missing',
  'ignored',
  'removed_from_source',
] as const
export type FilterChip = (typeof FILTER_CHIPS)[number]

/** "Tous" hides ignored/removed_from_source (M4-PLAN M4.7); a specific chip
    shows exactly its status. */
export function filterByChip(tracks: LibraryTrack[], chip: FilterChip): LibraryTrack[] {
  if (chip === 'all')
    return tracks.filter((t) => t.status !== 'ignored' && t.status !== 'removed_from_source')
  return tracks.filter((t) => t.status === chip)
}

/** Confidence chip tone: ≥95 success, ≥ the configured threshold accent,
    anything lower warning (mirrors the matcher's G4 threshold). */
export function confTone(confidence: number, threshold: number): 'success' | 'accent' | 'warning' {
  if (confidence >= 95) return 'success'
  if (confidence >= threshold) return 'accent'
  return 'warning'
}

/** Statuses the re-match/manual-match/mark-missing flows accept (mirror of
    the sidecar's _REMATCH_REFUSED complement). */
export function isRematchable(track: LibraryTrack): boolean {
  return ['new', 'matched', 'conflict', 'missing'].includes(track.status)
}

/** §5.6: only matched/ready rows are applicable to Rekordbox. */
export function isApplicable(track: LibraryTrack): boolean {
  return track.status === 'matched' || track.status === 'ready'
}

export function formatDuration(ms: number | null | undefined): string {
  if (!ms) return '—'
  const total = Math.round(ms / 1000)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}
