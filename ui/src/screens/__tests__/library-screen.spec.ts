import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { router } from '../../router'
import { useStatusStore } from '../../stores/status'
import LibraryScreen from '../LibraryScreen.vue'

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => vi.unstubAllGlobals())

const TRACKS = [
  { id: 1, source_id: 1, title: 'Alpha', artist: 'A', status: 'new', tags: [], confidence: null },
  { id: 2, source_id: 1, title: 'Beta', artist: 'B', status: 'matched', tags: [], confidence: 97 },
  { id: 3, source_id: 1, title: 'Gamma', artist: 'C', status: 'ignored', tags: [], confidence: null },
  {
    id: 4,
    source_id: 1,
    title: 'Delta',
    artist: 'D',
    status: 'removed_from_source',
    tags: [],
    confidence: null,
  },
]

function stubApi(overrides: Record<string, unknown> = {}, options: { failSync?: boolean } = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const path = new URL(url).pathname
      if (path === '/api/sources/sync' && init?.method === 'POST') {
        if (options.failSync)
          return Promise.resolve({
            ok: false,
            status: 409,
            json: () =>
              Promise.resolve({ error: 'spotify_not_connected', message: 'connect first' }),
          })
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ results: [] }) })
      }
      const payloads: Record<string, unknown> = {
        '/api/sources': { sources: [{ id: 1, name: 'Peak Time', tags: [], enabled: 1, status: 'synced', spotify_playlist_id: 'x' }] },
        '/api/sources/1/tracks': { tracks: TRACKS },
        '/api/settings': {},
        ...overrides,
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(payloads[path] ?? {}),
      })
    }),
  )
}

function mountLibrary() {
  return mount(LibraryScreen, { global: { plugins: [i18n, pinia, router] } })
}

test('"Tous" hides ignored/removed rows; select-all covers FILTERED rows only', async () => {
  stubApi()
  const wrapper = mountLibrary()
  await flushPromises()

  // "Tous" -> only new + matched are rendered
  expect(wrapper.text()).toContain('Alpha')
  expect(wrapper.text()).toContain('Beta')
  expect(wrapper.text()).not.toContain('Gamma')

  // select-all binds to the two visible rows only
  await wrapper.get('.table-head input[type="checkbox"]').setValue(true)
  expect(wrapper.text()).toContain('2 sélectionné(s)')

  // the ignored chip shows the hidden row
  const chips = wrapper.findAll('.chip')
  await chips[5].trigger('click') // 'Ignoré'
  expect(wrapper.text()).toContain('Gamma')
  expect(wrapper.text()).not.toContain('Alpha')
})

test('B1: a failed sync click surfaces the backend message actionably', async () => {
  stubApi({}, { failSync: true })
  const wrapper = mountLibrary()
  await flushPromises()

  await wrapper.get('header .btn-secondary').trigger('click')
  await flushPromises()

  const banner = wrapper.get('.banner[data-tone="error"]')
  expect(banner.text()).toContain('Connecte ton compte Spotify')
  expect(banner.text()).toContain('Connecter mon compte Spotify')
})

test('apply CTA reflects the RB guard and the exact applicable count', async () => {
  stubApi()
  useStatusStore().rbOpen = true
  const wrapper = mountLibrary()
  await flushPromises()

  await wrapper.get('.table-head input[type="checkbox"]').setValue(true)
  const apply = wrapper.get('.sel-action.apply')
  expect(apply.attributes('disabled')).toBeDefined()
  expect(apply.text()).toContain('Rekordbox ouvert — bloqué')

  useStatusStore().rbOpen = false
  await flushPromises()
  // 1 applicable (matched) out of the 2 selected
  expect(wrapper.get('.sel-action.apply').text()).toContain('Appliquer à Rekordbox · 1')
})
