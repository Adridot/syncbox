import { expect, test } from 'vitest'

import type { LibraryTrack } from '../../api/types'
import { confTone, filterByChip, formatDuration, isApplicable, isRematchable, isReview } from '../library'
import { extractPlaylistId, extractTrackId, spotifyUrl } from '../spotify'

const track = (status: string): LibraryTrack =>
  ({ id: 1, source_id: 1, status } as unknown as LibraryTrack)

test('"Tous" hides ignored and removed_from_source; a chip shows exactly its status', () => {
  const tracks = [
    'new',
    'matched',
    'ignored',
    'removed_from_source',
    'missing',
    'acquisition_failed',
  ].map(track)
  expect(filterByChip(tracks, 'all').map((t) => t.status)).toEqual([
    'new',
    'matched',
    'missing',
    'acquisition_failed',
  ])
  expect(filterByChip(tracks, 'missing').map((t) => t.status)).toEqual([
    'missing',
    'acquisition_failed',
  ])
  expect(filterByChip(tracks, 'ignored').map((t) => t.status)).toEqual(['ignored'])
  expect(filterByChip(tracks, 'removed_from_source').map((t) => t.status)).toEqual([
    'removed_from_source',
  ])
})

test('review/applicable/rematchable mirror the sidecar rules', () => {
  expect(['new', 'conflict', 'missing', 'acquisition_failed'].map(track).every(isReview)).toBe(true)
  expect(['matched', 'ready', 'ignored', 'imported'].map(track).some(isReview)).toBe(false)
  expect(['matched', 'ready'].map(track).every(isApplicable)).toBe(true)
  expect(track('new')).not.toSatisfy(isApplicable)
  expect(
    ['new', 'matched', 'conflict', 'missing', 'acquisition_failed']
      .map(track)
      .every(isRematchable),
  ).toBe(true)
  expect(['ignored', 'imported', 'ready', 'removed_from_source'].map(track).some(isRematchable)).toBe(
    false,
  )
})

test('confidence tone follows the configured threshold', () => {
  expect(confTone(96, 82)).toBe('success')
  expect(confTone(85, 82)).toBe('accent')
  expect(confTone(85, 90)).toBe('warning')
})

test('duration formats mm:ss', () => {
  expect(formatDuration(272_000)).toBe('4:32')
  expect(formatDuration(null)).toBe('—')
})

test('Spotify id extraction: URL, URI, raw id — Spotify only', () => {
  const id = '37i9dQZF1DXcBWIGoYBM5M'
  expect(extractPlaylistId(`https://open.spotify.com/playlist/${id}?si=abc`)).toBe(id)
  expect(extractPlaylistId(`spotify:playlist:${id}`)).toBe(id)
  expect(extractPlaylistId(id)).toBe(id)
  expect(extractPlaylistId('https://www.deezer.com/playlist/123456')).toBeNull()
  expect(extractPlaylistId('not a link')).toBeNull()
  expect(extractTrackId(`https://open.spotify.com/track/${id}`)).toBe(id)
  expect(extractTrackId(`https://open.spotify.com/intl-fr/track/${id}`)).toBe(id)
})

test('Spotify attribution URLs accept only canonical playlist and track ids', () => {
  const id = '37i9dQZF1DXcBWIGoYBM5M'
  expect(spotifyUrl('playlist', id)).toBe(`https://open.spotify.com/playlist/${id}`)
  expect(spotifyUrl('track', id)).toBe(`https://open.spotify.com/track/${id}`)
  expect(() => spotifyUrl('track', 'not-an-id')).toThrow('invalid Spotify track id')
})
