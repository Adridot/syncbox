import { expect, test } from 'vitest'

import type { EventTrack } from '../../api/types'
import { EVENT_FILTERS, eventCounts, filterEventTracks, isBaseApplied } from '../events'

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

test('acquisition failures stay visible in the missing recovery family', () => {
  const failed = track(8, 'acquisition_failed', 1)
  const counts = eventCounts([...TRACKS, failed], true)
  expect(counts.missing).toBe(3)
  expect(counts.pendMissing).toBe(2)
  expect(filterEventTracks([...TRACKS, failed], 'missing').map((t) => t.id)).toEqual([7, 8, 4])
})

test('pending additions sort to the top of every filter (§11.2 staging)', () => {
  const all = filterEventTracks(TRACKS, 'all')
  expect(all.slice(0, 2).map((t) => t.id)).toEqual([6, 7])
  // pending = reappliable rows + post-apply additions, additions first
  expect(filterEventTracks(TRACKS, 'pending').map((t) => t.id)).toEqual([6, 7, 1, 2])
  expect(filterEventTracks(TRACKS, 'ambiguous').map((t) => t.id)).toEqual([5])
  expect(filterEventTracks(TRACKS, 'missing').map((t) => t.id)).toEqual([7, 4])
})

test('§5.7: a rejected adoption is outstanding work for nobody', () => {
  // the row survives only so its staged file is not re-adopted — it must not
  // show up in the total, in any count, nor in a single chip but its own
  const ignored = [track(9, 'ignored'), track(10, 'ignored', 1)]
  expect(eventCounts([...TRACKS, ...ignored], true)).toEqual(eventCounts(TRACKS, true))
  for (const chip of EVENT_FILTERS.filter((c) => c !== 'ignored'))
    expect(filterEventTracks([...TRACKS, ...ignored], chip).map((t) => t.id)).toEqual(
      filterEventTracks(TRACKS, chip).map((t) => t.id),
    )
})

test('§5.7: the ignored chip lists exactly the rejected rows and nothing else', () => {
  const ignored = [track(9, 'ignored'), track(10, 'ignored', 1)]
  // the one place they are reachable — post-apply additions still sort first
  expect(filterEventTracks([...TRACKS, ...ignored], 'ignored').map((t) => t.id)).toEqual([10, 9])
  // and nothing else leaks in through it
  expect(filterEventTracks(TRACKS, 'ignored')).toEqual([])
})

test('a track that left the playlist is a decision, not outstanding work', () => {
  // it keeps everything it had — including a ready status and the delta flag
  // — but nothing will be written for it, so no count may move
  const departed = [track(11, 'removed_upstream'), track(12, 'removed_upstream', 1)]
  expect(eventCounts([...TRACKS, ...departed], true)).toEqual(eventCounts(TRACKS, true))
  for (const chip of EVENT_FILTERS.filter((c) => c !== 'removed'))
    expect(filterEventTracks([...TRACKS, ...departed], chip).map((t) => t.id)).toEqual(
      filterEventTracks(TRACKS, chip).map((t) => t.id),
    )
})

test('the removed chip is the one place a departure is reachable', () => {
  const departed = [track(11, 'removed_upstream'), track(12, 'removed_upstream', 1)]
  const all = [...TRACKS, ...departed, track(9, 'ignored')]
  // post-apply additions still sort first, and the rejected rows do NOT leak
  // in through the neighbouring opt-in chip
  expect(filterEventTracks(all, 'removed').map((t) => t.id)).toEqual([12, 11])
  expect(filterEventTracks(all, 'ignored').map((t) => t.id)).toEqual([9])
  expect(filterEventTracks(TRACKS, 'removed')).toEqual([])
})

test('applied and partially_applied both stay open to additions', () => {
  expect(isBaseApplied('applied')).toBe(true)
  expect(isBaseApplied('partially_applied')).toBe(true)
  expect(isBaseApplied('pending')).toBe(false)
})
