import { expect, test } from 'vitest'

import type { EventTrack } from '../../api/types'
import { eventCounts, filterEventTracks, isBaseApplied } from '../events'

const track = (id: number, status: string, delta = 0): EventTrack =>
  ({ id, event_id: 1, status, added_after_apply: delta }) as unknown as EventTrack

const TRACKS = [
  track(1, 'matched'), // matched AFTER the apply: not a delta row, still pending
  track(2, 'ready'),
  track(3, 'applied'), // what the apply pipeline writes ('imported' n'existe pas)
  track(4, 'missing'),
  track(5, 'ambiguous'),
  track(6, 'ready', 1),
  track(7, 'missing', 1),
]

test('event counts drive the segmented bar and the reapply CTA (§11.2)', () => {
  const counts = eventCounts(TRACKS, true)
  expect(counts).toEqual({
    total: 7,
    ready: 3, // matched + ready + delta-ready — NOT applied (owner feedback 07/07)
    applied: 1, // already in Rekordbox, counted separately
    missing: 2,
    ambiguous: 1,
    // owner amendment 07/07: EVERY reappliable row is a pending change —
    // including track 1, matched after the apply without the delta flag
    pending: 4,
    pendReady: 3,
    pendMissing: 1,
  })
})

test('a never-applied event has no pending delta (nothing to REapply)', () => {
  const counts = eventCounts(TRACKS, false)
  expect(counts.pending).toBe(0)
  expect(counts.pendReady).toBe(0)
  expect(counts.pendMissing).toBe(0)
})

test('pending additions sort to the top of every filter (§11.2 staging)', () => {
  const all = filterEventTracks(TRACKS, 'all')
  expect(all.slice(0, 2).map((t) => t.id)).toEqual([6, 7])
  // pending = reappliable rows + post-apply additions, additions first
  expect(filterEventTracks(TRACKS, 'pending').map((t) => t.id)).toEqual([6, 7, 1, 2])
  expect(filterEventTracks(TRACKS, 'ambiguous').map((t) => t.id)).toEqual([5])
  expect(filterEventTracks(TRACKS, 'missing').map((t) => t.id)).toEqual([7, 4])
})

test('applied and partially_applied both stay open to additions', () => {
  expect(isBaseApplied('applied')).toBe(true)
  expect(isBaseApplied('partially_applied')).toBe(true)
  expect(isBaseApplied('pending')).toBe(false)
})
