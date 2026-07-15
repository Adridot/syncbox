import { mount } from '@vue/test-utils'
import { beforeEach, expect, test, vi } from 'vitest'

import { openExternal } from '../../shell'
import SpotifyAttributionLink from '../SpotifyAttributionLink.vue'

vi.mock('../../shell', () => ({ openExternal: vi.fn() }))

beforeEach(() => vi.mocked(openExternal).mockReset().mockResolvedValue(undefined))

test('opens the canonical Spotify URL in the external browser', async () => {
  const id = '37i9dQZF1DXcBWIGoYBM5M'
  const wrapper = mount(SpotifyAttributionLink, {
    props: { kind: 'track', spotifyId: id },
  })

  expect(wrapper.text()).toBe('OPEN SPOTIFY ↗')
  await wrapper.get('button').trigger('click')

  expect(openExternal).toHaveBeenCalledWith(`https://open.spotify.com/track/${id}`)
})

test('shows a local failure state when the external opener rejects', async () => {
  vi.mocked(openExternal).mockRejectedValueOnce(new Error('opener failed'))
  const wrapper = mount(SpotifyAttributionLink, {
    props: { kind: 'playlist', spotifyId: '37i9dQZF1DXcBWIGoYBM5M' },
  })

  await wrapper.get('button').trigger('click')

  expect(wrapper.get('button').attributes('data-failed')).toBe('true')
  expect(wrapper.get('button').attributes('title')).toContain('could not be opened')
})
