/* ui-performance: the big track tables are windowed — only ~viewport rows in
   the DOM at any dataset size, while selection/bulk actions keep operating on
   the full filtered data arrays and silent refreshes stay invisible. */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { KeepAlive, defineComponent, h, nextTick, ref } from 'vue'

import { i18n } from '../../i18n'
import { router } from '../../router'
import EventsScreen from '../EventsScreen.vue'
import LibraryScreen from '../LibraryScreen.vue'

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => vi.unstubAllGlobals())

const N = 3000

function makeTracks(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    id: i + 1,
    source_id: 1,
    title: `Track ${i + 1}`,
    artist: `Artist ${i + 1}`,
    status: 'matched',
    tags: [],
    confidence: 90,
  }))
}

function stubLibraryApi(fetchMock = vi.fn()) {
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    const path = new URL(url).pathname
    if (init?.method === 'POST')
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
    const payloads: Record<string, unknown> = {
      '/api/sources': {
        sources: [
          { id: 1, name: 'Big', tags: [], enabled: 1, status: 'synced', spotify_playlist_id: 'x' },
        ],
      },
      '/api/sources/1/tracks': { tracks: makeTracks(N) },
      '/api/settings': {},
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(payloads[path] ?? {}),
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const plugins = () => ({ global: { plugins: [i18n, pinia, router] } })

test('4.1 Library windows the table: DOM rows ≪ dataset size', async () => {
  stubLibraryApi()
  const wrapper = mount(LibraryScreen, plugins())
  await flushPromises()

  const rows = wrapper.findAll('.table-body .row')
  expect(rows.length).toBeGreaterThan(0)
  expect(rows.length).toBeLessThan(100) // ~viewport + overscan, not 3000
  expect(wrapper.text()).toContain('Track 1')
})

test('4.2 select-all covers every filtered track incl. off-DOM; bulk apply posts them all', async () => {
  const fetchMock = stubLibraryApi()
  const wrapper = mount(LibraryScreen, plugins())
  await flushPromises()

  await wrapper.get('.table-head input[type="checkbox"]').setValue(true)
  expect(wrapper.text()).toContain(`${N} sélectionné(s)`)

  await wrapper.get('.sel-action.apply').trigger('click')
  await flushPromises()

  const applyCall = fetchMock.mock.calls.find(([url]) =>
    String(url).includes('/api/sources/1/apply'),
  )
  expect(applyCall).toBeDefined()
  const body = JSON.parse(String(applyCall![1]!.body)) as { track_ids: number[] }
  expect(body.track_ids).toHaveLength(N)
  expect(body.track_ids).toContain(N) // far off-screen row is covered
})

test('4.3 silent refresh with identical data: no skeleton, selection/scroll intact, table untouched', async () => {
  stubLibraryApi()
  const show = ref(true)
  const Host = defineComponent({
    setup: () => () => h(KeepAlive, null, [show.value ? h(LibraryScreen) : null]),
  })
  const wrapper = mount(Host, plugins())
  await flushPromises()

  // select one row, scroll the windowed body
  await wrapper.get('.table-body .row input[type="checkbox"]').setValue(true)
  expect(wrapper.text()).toContain('1 sélectionné(s)')
  const body = wrapper.get('.table-body').element
  body.scrollTop = 500
  const before = wrapper.get('.table-body').html()

  // leave and re-enter: keep-alive re-entry triggers the silent refresh
  show.value = false
  await nextTick()
  show.value = true
  await nextTick()
  expect(wrapper.find('.loading[role="status"]').exists()).toBe(false) // no skeleton mid-refresh
  await flushPromises()

  expect(wrapper.find('.loading[role="status"]').exists()).toBe(false)
  expect(wrapper.text()).toContain('1 sélectionné(s)')
  expect(wrapper.get('.table-body').element.scrollTop).toBe(500)
  expect(wrapper.get('.table-body').html()).toBe(before) // zero DOM change
})

test('4.4 Events renders windowed rows outside the App shell (scroll fallback)', async () => {
  const tracks = Array.from({ length: 500 }, (_, i) => ({
    id: i + 1,
    event_id: 1,
    spotify_track_id: null,
    title: `Set ${i + 1}`,
    artist: `DJ ${i + 1}`,
    duration_ms: null,
    isrc: null,
    status: 'ready',
    content_id: null,
    confidence: 96,
    staging_file_path: null,
    added_after_apply: 0,
    prior_status: null,
  }))
  const event = {
    id: 1,
    name: 'Mariage',
    slug: 'mariage',
    default_tag: 'Situation:Mariage',
    spotify_playlist_id: 'manual:1',
    staging_dir: null,
    status: 'pending',
    applied_at: null,
    created_at: '2026-08-01',
    n_tracks: tracks.length,
    pending_delta: 0,
  }
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      const path = new URL(url).pathname
      const payloads: Record<string, unknown> = {
        '/api/events': { events: [event] },
        '/api/events/1': { ...event, tracks },
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(payloads[path] ?? {}),
      })
    }),
  )
  const wrapper = mount(EventsScreen, plugins())
  await flushPromises()

  const rows = wrapper.findAll('.v-rows .row')
  expect(rows.length).toBeGreaterThan(0)
  expect(rows.length).toBeLessThan(100) // windowed, not 500
  expect(wrapper.text()).toContain('Set 1')
})
