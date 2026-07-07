import { expect, test } from 'vitest'

import type { EventTrack } from '../../api/types'
import { eventCounts, filterEventTracks, isBaseApplied } from '../events'

const track = (id: number, status: string, delta = 0): EventTrack =>
  ({ id, event_id: 1, status, added_after_apply: delta }) as unknown as EventTrack

const TRACKS = [
  track(1, 'matched'),
  track(2, 'ready'),
  track(3, 'imported'),
  track(4, 'missing'),
  track(5, 'ambiguous'),
  track(6, 'ready', 1),
  track(7, 'missing', 1),
]

test('event counts drive the segmented bar and the reapply CTA (§11.2)', () => {
  const counts = eventCounts(TRACKS)
  expect(counts).toEqual({
    total: 7,
    ready: 4, // matched + ready + imported + delta-ready
    missing: 2,
    ambiguous: 1,
    pending: 2,
    pendReady: 1,
    pendMissing: 1,
  })
})

test('pending additions sort to the top of every filter (§11.2 staging)', () => {
  const all = filterEventTracks(TRACKS, 'all')
  expect(all.slice(0, 2).map((t) => t.id)).toEqual([6, 7])
  expect(filterEventTracks(TRACKS, 'pending').map((t) => t.id)).toEqual([6, 7])
  expect(filterEventTracks(TRACKS, 'ambiguous').map((t) => t.id)).toEqual([5])
  expect(filterEventTracks(TRACKS, 'missing').map((t) => t.id)).toEqual([7, 4])
})

test('applied and partially_applied both stay open to additions', () => {
  expect(isBaseApplied('applied')).toBe(true)
  expect(isBaseApplied('partially_applied')).toBe(true)
  expect(isBaseApplied('pending')).toBe(false)
})
