import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { router } from '../../router'
import { useHealthStore } from '../../stores/health'
import { useSettingsStore } from '../../stores/settings'
import LibraryScreen from '../LibraryScreen.vue'

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => vi.unstubAllGlobals())

const SOURCES = [{ id: 1, spotify_playlist_id: 'A'.repeat(22), name: 'Peak Hour', tags: ['Mainroom'], enabled: 1, status: null, snapshot_id: 's1' }]

const TRACKS = [
  { id: 10, spotify_track_id: 't1', title: 'Alpha', artist: 'A', duration_ms: 200000, isrc: null, status: 'matched', content_id: 'c1', match_method: 'isrc', confidence: 100, tags: [] },
  { id: 11, spotify_track_id: 't2', title: 'Beta', artist: 'B', duration_ms: 200000, isrc: null, status: 'conflict', content_id: 'c2', match_method: 'fuzzy', confidence: 70, tags: [] },
  { id: 12, spotify_track_id: 't3', title: 'Gamma', artist: 'C', duration_ms: 200000, isrc: null, status: 'ignored', content_id: null, match_method: null, confidence: null, tags: [] },
  { id: 13, spotify_track_id: 't4', title: 'Delta', artist: 'D', duration_ms: 200000, isrc: null, status: 'missing', content_id: null, match_method: null, confidence: 0, tags: [] },
]

function stubApi(overrides: Record<string, unknown> = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      const path = new URL(url).pathname
      const payloads: Record<string, unknown> = {
        '/api/sources': { sources: SOURCES },
        '/api/sources/1/tracks': { tracks: TRACKS },
        ...overrides,
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payloads[path] ?? {}) })
    }),
  )
}

function mountLibrary() {
  return mount(LibraryScreen, { global: { plugins: [i18n, pinia, router] } })
}

test('review table hides ignored/removed in "Tous"; review badge counts attention rows', async () => {
  stubApi()
  useSettingsStore().$patch({ values: { rekordbox_db_path: '/x', storage_root: '/y', language: 'fr' } as never, loaded: true })
  const wrapper = mountLibrary()
  await flushPromises()

  // "Tous" shows matched/conflict/missing (3), hides the ignored row
  const rows = wrapper.findAll('.trow')
  expect(rows).toHaveLength(3)
  expect(wrapper.text()).not.toContain('Gamma')
  // review count = new/conflict/missing = 2 (conflict + missing)
  expect(useHealthStore().badges.library).toBe(2)
})

test('status filter switches the visible rows; ignored filter reveals ignored', async () => {
  stubApi()
  useSettingsStore().$patch({ values: { rekordbox_db_path: '/x', storage_root: '/y', language: 'fr' } as never, loaded: true })
  const wrapper = mountLibrary()
  await flushPromises()

  const ignoredChip = wrapper.findAll('.chip-btn').find((b) => b.text() === 'Ignoré')!
  await ignoredChip.trigger('click')
  const rows = wrapper.findAll('.trow')
  expect(rows).toHaveLength(1)
  expect(wrapper.text()).toContain('Gamma')
})

test('select-all checks only the FILTERED rows', async () => {
  stubApi()
  useSettingsStore().$patch({ values: { rekordbox_db_path: '/x', storage_root: '/y', language: 'fr' } as never, loaded: true })
  const wrapper = mountLibrary()
  await flushPromises()

  await wrapper.find('.thead .cb input').setValue(true)
  // 3 visible rows selected -> bulk bar shows 3
  expect(wrapper.find('.bulk-count').text()).toContain('3')
})

test('404 on a private playlist shows the actionable error state', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      const path = new URL(url).pathname
      if (path === '/api/sources')
        return Promise.resolve({
          ok: false,
          status: 502,
          json: () => Promise.resolve({ error: 'spotify_api_error', status_code: 404, message: 'private' }),
        })
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
    }),
  )
  useSettingsStore().$patch({ values: { rekordbox_db_path: '/x', storage_root: '/y', language: 'fr' } as never, loaded: true })
  const wrapper = mountLibrary()
  await flushPromises()
  expect(wrapper.text()).toContain('Playlist privée ou inaccessible')
  expect(wrapper.text()).toContain('Connecter mon compte Spotify')
})
