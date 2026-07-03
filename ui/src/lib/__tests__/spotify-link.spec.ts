import { expect, test } from 'vitest'

import { extractPlaylistId, extractTrackId } from '../spotify-link'

const ID = '37i9dQZF1DXcBWIGoYBM5M'

test('extracts a playlist id from URL, uri and bare id; ignores junk', () => {
  expect(extractPlaylistId(`https://open.spotify.com/playlist/${ID}`)).toBe(ID)
  expect(extractPlaylistId(`https://open.spotify.com/playlist/${ID}?si=abc`)).toBe(ID)
  expect(extractPlaylistId(`spotify:playlist:${ID}`)).toBe(ID)
  expect(extractPlaylistId(`  ${ID}  `)).toBe(ID)
  expect(extractPlaylistId('https://open.spotify.com/album/xyz')).toBeNull()
  expect(extractPlaylistId('not a link')).toBeNull()
})

test('extracts a track id, distinct from playlist', () => {
  expect(extractTrackId(`https://open.spotify.com/track/${ID}`)).toBe(ID)
  expect(extractTrackId(`spotify:track:${ID}`)).toBe(ID)
  // a playlist link is not a track link
  expect(extractTrackId(`https://open.spotify.com/playlist/${ID}`)).toBeNull()
})
