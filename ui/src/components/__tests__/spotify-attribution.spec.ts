import { mount } from '@vue/test-utils'
import { beforeEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { openSpotify } from '../../shell'
import SpotifyAttributionLink from '../SpotifyAttributionLink.vue'

vi.mock('../../shell', () => ({ openSpotify: vi.fn() }))

beforeEach(() => vi.mocked(openSpotify).mockReset().mockResolvedValue(undefined))

function mountLink(kind: 'playlist' | 'track', spotifyId: string) {
  return mount(SpotifyAttributionLink, {
    props: { kind, spotifyId },
    global: { plugins: [i18n] },
  })
}

test('prefers the desktop app URI and falls back to the canonical web URL', async () => {
  const id = '37i9dQZF1DXcBWIGoYBM5M'
  const wrapper = mountLink('track', id)

  expect(wrapper.get('button').attributes('title')).toBe('Ouvrir dans Spotify')
  await wrapper.get('button').trigger('click')

  expect(openSpotify).toHaveBeenCalledWith(
    `spotify:track:${id}`,
    `https://open.spotify.com/track/${id}`,
  )
})

test('shows a local failure state when the opener rejects', async () => {
  vi.mocked(openSpotify).mockRejectedValueOnce(new Error('opener failed'))
  const wrapper = mountLink('playlist', '37i9dQZF1DXcBWIGoYBM5M')

  await wrapper.get('button').trigger('click')

  expect(wrapper.get('button').attributes('data-failed')).toBe('true')
  expect(wrapper.get('button').attributes('title')).toContain("n'a pas pu être ouvert")
})
