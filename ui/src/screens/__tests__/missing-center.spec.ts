import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { router } from '../../router'
import { openExternal } from '../../shell'
import MissingCenterScreen from '../MissingCenterScreen.vue'

vi.mock('../../shell', () => ({ openExternal: vi.fn() }))

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  vi.mocked(openExternal).mockResolvedValue(undefined)
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

const LIB_ENTRY = {
  scope: 'library',
  id: 1,
  content_id: null,
  title: 'Greece 2000',
  artist: 'Three Drives',
  spotify_track_id: '37i9dQZF1DXcBWIGoYBM5M',
  status: 'missing',
  purchase_links: [
    { store: 'Beatport', url: 'https://www.beatport.com/search?q=x' },
    { store: 'Bandcamp', url: 'https://bandcamp.com/search?q=x' },
  ],
  relink_candidates: [],
  acquisition: { provider: 'deezer', available: true },
}
// purchase_link_unavailable: the server sends NO links — the UI must not re-add
const NO_LINK_ENTRY = {
  scope: 'event',
  id: 2,
  content_id: null,
  title: 'Obscure Bootleg',
  artist: 'Unknown',
  status: 'purchase_link_unavailable',
  purchase_links: [],
  relink_candidates: [],
}

function stubApi(acquisitionJob: unknown = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const path = new URL(url).pathname
      if (init?.method === 'POST')
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve(
              path === '/api/acquisition/jobs/batch'
                ? { jobs: [acquisitionJob] }
                : {},
            ),
        })
      const payloads: Record<string, unknown> = {
        '/api/missing/library': { entries: [LIB_ENTRY] },
        '/api/missing/event': { entries: [NO_LINK_ENTRY] },
        '/api/missing/collection': { entries: [] },
        '/api/acquisition/jobs': { active: [], recent: [] },
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(payloads[path] ?? { entries: [] }),
      })
    }),
  )
}

async function mountCenter(scope?: string) {
  await router.push(scope ? `/missing/${scope}` : '/missing')
  return mount(MissingCenterScreen, {
    props: { scope },
    global: { plugins: [i18n, pinia, router] },
  })
}

test('"all" merges the 3 scopes with scope badges; purchase links only when the server sent them', async () => {
  stubApi()
  const wrapper = await mountCenter()
  await flushPromises()

  expect(wrapper.text()).toContain('Greece 2000')
  expect(wrapper.text()).toContain('Obscure Bootleg')
  // scope badges visible in the merged view
  expect(wrapper.findAll('.row').length).toBe(2)
  // ONE buy button on the linked row, ZERO on the purchase_link_unavailable
  // row; multiple providers live behind the unified purchase menu and the
  // remaining actions behind the ⋯ row menu (owner decision 15/07).
  const rows = wrapper.findAll('.row')
  expect(rows[0].findAll('.buy')).toHaveLength(1)
  expect(rows[0].get('.buy').text()).toBe('Acheter (2 boutiques) ↗')
  await rows[0].get('.more').trigger('click')
  expect(rows[0].findAll('.menu-item')[0].text()).toBe('Télécharger via Deezer')
  expect(rows[1].findAll('.buy')).toHaveLength(0)
})

test('deep-linked scope filters the list', async () => {
  stubApi()
  const wrapper = await mountCenter('event')
  await flushPromises()
  expect(wrapper.text()).toContain('Obscure Bootleg')
  expect(wrapper.text()).not.toContain('Greece 2000')
})

test('purchase buttons delegate the URL to the external browser bridge', async () => {
  stubApi()
  const wrapper = await mountCenter('library')
  await flushPromises()

  await wrapper.get('.buy').trigger('click')
  expect(wrapper.findAll('.buy-menu .menu-item').map((button) => button.text())).toEqual([
    'Beatport',
    'Bandcamp',
  ])
  await wrapper.get('.buy-menu .menu-item').trigger('click')

  expect(openExternal).toHaveBeenCalledWith(LIB_ENTRY.purchase_links[0].url)
})

test('a rejected external purchase link is reported as an error', async () => {
  stubApi()
  vi.mocked(openExternal).mockRejectedValueOnce(new Error('opener failed'))
  const wrapper = await mountCenter('library')
  await flushPromises()

  await wrapper.get('.buy').trigger('click')
  await wrapper.get('.buy-menu .menu-item').trigger('click')
  await flushPromises()

  expect(wrapper.get('.banner[data-tone="error"]').text()).toContain(
    'n’a pas pu être ouvert',
  )
})

test('D22: ignoring a row offers an inline undo that calls restore', async () => {
  stubApi()
  const wrapper = await mountCenter('library')
  await flushPromises()

  await wrapper.get('.more').trigger('click')
  const ignoreButton = wrapper
    .findAll('.menu-item')
    .find((button) => button.text() === 'Ignorer')
  await ignoreButton!.trigger('click')
  await flushPromises()

  expect(wrapper.get('.banner[data-tone="success"]').text()).toContain('ignoré')
  await wrapper.get('.undo').trigger('click')
  await flushPromises()

  const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>
  const calls = fetchMock.mock.calls.map(([url]) => new URL(String(url)).pathname)
  expect(calls).toContain('/api/missing/library/1/status')
  expect(calls).toContain('/api/missing/library/1/restore')
})

test('a failed acquisition job is never presented as a successful download', async () => {
  stubApi({ status: 'failed', error: 'RuntimeError' })
  const wrapper = await mountCenter('library')
  await flushPromises()

  await wrapper.get('.more').trigger('click')
  const acquireButton = wrapper
    .findAll('.menu-item')
    .find((button) => button.text() === 'Télécharger via Deezer')
  await acquireButton!.trigger('click')
  await flushPromises()

  expect(wrapper.get('.banner[data-tone="error"]').text()).toContain(
    'n’a pas pu être téléchargé',
  )
  expect(wrapper.findAll('.banner[data-tone="success"]')).toHaveLength(0)
})
