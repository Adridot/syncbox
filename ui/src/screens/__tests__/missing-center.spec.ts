import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { router } from '../../router'
import MissingCenterScreen from '../MissingCenterScreen.vue'

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => vi.unstubAllGlobals())

const LIB_ENTRY = {
  scope: 'library',
  id: 1,
  content_id: null,
  title: 'Greece 2000',
  artist: 'Three Drives',
  status: 'missing',
  purchase_links: [
    { store: 'Beatport', url: 'https://www.beatport.com/search?q=x' },
    { store: 'Bandcamp', url: 'https://bandcamp.com/search?q=x' },
  ],
  relink_candidates: [],
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

function stubApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const path = new URL(url).pathname
      if (init?.method === 'POST')
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
      const payloads: Record<string, unknown> = {
        '/api/missing/library': { entries: [LIB_ENTRY] },
        '/api/missing/event': { entries: [NO_LINK_ENTRY] },
        '/api/missing/collection': { entries: [] },
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
  // 2 buy buttons on the linked row, ZERO on the purchase_link_unavailable row
  const rows = wrapper.findAll('.row')
  expect(rows[0].findAll('.buy').map((b) => b.text())).toEqual(['Beatport ↗', 'Bandcamp ↗'])
  expect(rows[1].findAll('.buy')).toHaveLength(0)
})

test('deep-linked scope filters the list', async () => {
  stubApi()
  const wrapper = await mountCenter('event')
  await flushPromises()
  expect(wrapper.text()).toContain('Obscure Bootleg')
  expect(wrapper.text()).not.toContain('Greece 2000')
})

test('D22: ignoring a row offers an inline undo that calls restore', async () => {
  stubApi()
  const wrapper = await mountCenter('library')
  await flushPromises()

  const ignoreButton = wrapper
    .findAll('.secondary')
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
