import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { afterEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { useSpotifyConnect } from '../useSpotifyConnect'

afterEach(() => vi.unstubAllGlobals())

test('Spotify callback-port collision is actionable and localized', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: () =>
        Promise.resolve({
          error: 'oauth_callback_port_in_use',
          message: 'technical fallback',
        }),
    }),
  )
  i18n.global.locale.value = 'fr'
  const Harness = defineComponent({
    setup() {
      const spotify = useSpotifyConnect()
      return () =>
        h('div', [
          h('button', { onClick: spotify.connect }, 'connect'),
          h('p', spotify.error.value ?? ''),
        ])
    },
  })
  const wrapper = mount(Harness, {
    global: { plugins: [i18n, createPinia()] },
  })

  await wrapper.get('button').trigger('click')
  await flushPromises()

  expect(wrapper.text()).toContain('port de callback 8765 est utilisé')
  expect(wrapper.text()).not.toContain('technical fallback')
})
