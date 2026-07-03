import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { router } from '../../router'
import { useEventsStore } from '../../stores/events'
import { useSettingsStore } from '../../stores/settings'
import { useStatusStore } from '../../stores/status'
import EventsScreen from '../EventsScreen.vue'

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => vi.unstubAllGlobals())

function track(over: Record<string, unknown> = {}) {
  return {
    id: Math.floor(Math.random() * 1e6),
    event_id: 1,
    spotify_track_id: 't',
    title: 'T',
    artist: 'A',
    duration_ms: 200000,
    isrc: null,
    status: 'ready',
    content_id: 'c',
    confidence: 90,
    staging_file_path: null,
    added_after_apply: 0,
    prior_status: null,
    ...over,
  }
}

const CONFIGURED = { rekordbox_db_path: '/x', storage_root: '/y', language: 'fr' }

function stubApi(events: unknown[], detail: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      const path = new URL(url).pathname
      const payloads: Record<string, unknown> = {
        '/api/events': { events },
        '/api/events/1': detail,
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payloads[path] ?? {}) })
    }),
  )
}

async function mountEvents() {
  const wrapper = mount(EventsScreen, { global: { plugins: [i18n, pinia, router] } })
  await flushPromises()
  return wrapper
}

test('pending-event workspace shows "Apply", counts and progress from real data', async () => {
  const cards = [{ id: 1, name: 'Wedding', slug: 'wedding', status: 'pending', spotify_playlist_id: null, default_tag: 'Wedding', staging_dir: '/s', applied_at: null, n_tracks: 3, pending_delta: 0 }]
  stubApi(cards, { ...cards[0], tracks: [track({ status: 'ready' }), track({ status: 'ready' }), track({ status: 'missing' })] })
  useSettingsStore().$patch({ values: CONFIGURED as never, loaded: true })
  const wrapper = await mountEvents()

  const store = useEventsStore()
  expect(store.counts).toMatchObject({ ready: 2, missing: 1, pending: 0, total: 3 })
  expect(store.isReapply).toBe(false)
  // primary CTA reads "Apply" (not reapply)
  expect(wrapper.text()).toContain('Appliquer → Event Imports')
})

test('applied event with a pending delta flips to Re-apply with the delta count', async () => {
  const cards = [{ id: 1, name: 'Party', slug: 'party', status: 'applied', spotify_playlist_id: null, default_tag: 'Party', staging_dir: '/s', applied_at: '2026-07-01', n_tracks: 4, pending_delta: 2 }]
  stubApi(cards, {
    ...cards[0],
    tracks: [
      track({ status: 'imported', added_after_apply: 0 }),
      track({ status: 'imported', added_after_apply: 0 }),
      track({ status: 'ready', added_after_apply: 1 }),
      track({ status: 'missing', added_after_apply: 1 }),
    ],
  })
  useSettingsStore().$patch({ values: CONFIGURED as never, loaded: true })
  const wrapper = await mountEvents()

  const store = useEventsStore()
  expect(store.isReapply).toBe(true)
  expect(store.counts.pending).toBe(2)
  // Modified banner + reapply CTA present
  expect(wrapper.text()).toContain('Modifié depuis la dernière application')
  expect(wrapper.text()).toContain('Ré-appliquer · +2')
})

test('both apply and delete CTAs reflect the RB-open guard', async () => {
  const cards = [{ id: 1, name: 'W', slug: 'w', status: 'pending', spotify_playlist_id: null, default_tag: 'W', staging_dir: '/s', applied_at: null, n_tracks: 1, pending_delta: 0 }]
  stubApi(cards, { ...cards[0], tracks: [track()] })
  useSettingsStore().$patch({ values: CONFIGURED as never, loaded: true })
  useStatusStore().rbOpen = true
  const wrapper = await mountEvents()

  // both guarded buttons show the blocked label (D11/D23 consistency)
  const guarded = wrapper.findAll('.guarded[data-blocked="true"]')
  expect(guarded.length).toBe(2)
  guarded.forEach((btn) => {
    expect(btn.text()).toBe('Rekordbox ouvert — bloqué')
    expect(btn.attributes('disabled')).toBeDefined()
  })
})
