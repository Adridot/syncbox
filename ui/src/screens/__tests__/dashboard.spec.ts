import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { router } from '../../router'
import { useHealthStore } from '../../stores/health'
import { useJobsStore } from '../../stores/jobs'
import { useSettingsStore } from '../../stores/settings'
import { useStatusStore } from '../../stores/status'
import DashboardScreen from '../DashboardScreen.vue'

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => vi.unstubAllGlobals())

const CONFIGURED = {
  spotify_client_id: '',
  rekordbox_db_path: '/rb/master.db',
  storage_root: '/music',
  backup_retention: 15,
  language: 'fr',
  match_confidence_threshold: 82,
  match_ambiguity_margin: 6,
  match_weights: { title: 0.52, artist: 0.36, duration: 0.12 },
  isrc_collision_policy: 'guarded' as const,
}

const READOUTS = {
  total_tracks: 1240,
  keys_analyzed: { total: 1240, analyzed: 992, pct: 80 },
  never_played: 61,
  added_this_month: 14,
  last_import: '2026-07-01T10:00:00',
  genres: [{ genre: 'Melodic Techno', count: 300 }],
  quality: { ok: 1200, lossy_source_probable: 30, incertain: 10 },
}

function stubApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      const payloads: Record<string, unknown> = {
        '/api/readouts': READOUTS,
        '/api/doctor/backups': { backups: [{ name: 'rekordbox-db-20260703-101530' }] },
        '/api/sources': { sources: [{}, {}, {}] },
        '/api/missing/library': { entries: [{}] },
        '/api/missing/event': { entries: [] },
        '/api/missing/collection': { entries: [{}, {}] },
        '/api/untagged': { tracks: [{}, {}, {}, {}] },
      }
      const path = new URL(url).pathname
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(payloads[path] ?? {}),
      })
    }),
  )
}

function mountDashboard() {
  return mount(DashboardScreen, { global: { plugins: [i18n, pinia, router] } })
}

test('configured dashboard: readouts, tiles and last backup from the API', async () => {
  stubApi()
  useSettingsStore().$patch({ values: CONFIGURED, loaded: true })
  const wrapper = mountDashboard()
  await flushPromises()

  // §11.3 readouts wired (never a red binary counter)
  expect(wrapper.text()).toContain('80%')
  expect(wrapper.text()).toContain('Lossy probable')
  expect(wrapper.text()).toContain('Incertain')
  expect(wrapper.text()).toContain('Melodic Techno')
  // last backup parsed from the timestamped name
  expect(wrapper.text()).toContain('03/07/2026 10:15')
  // duplicates tile: never scanned -> em dash, scan affordance
  expect(wrapper.text()).toContain('—')
  expect(wrapper.text()).toContain('lancer un scan')
  // missing counts loaded through the canonical selector
  expect(useHealthStore().missingTotal).toBe(3)
})

test('hero switches to the RB-open variant from the status store', async () => {
  stubApi()
  useSettingsStore().$patch({ values: CONFIGURED, loaded: true })
  useStatusStore().rbOpen = true
  const wrapper = mountDashboard()
  await flushPromises()
  expect(wrapper.get('.hero').attributes('data-open')).toBe('true')
  expect(wrapper.text()).toContain('écritures en pause')
})

test('SSE job completion renders a translated activity label', async () => {
  stubApi()
  useSettingsStore().$patch({ values: CONFIGURED, loaded: true })
  useJobsStore().doneLog.push({
    job: 'phase6',
    kind: 'sources.sync_all',
    synced: 0,
    at: Date.now(),
  })
  const wrapper = mountDashboard()
  await flushPromises()
  expect(wrapper.text()).toContain('Sources synchronisées')
  expect(wrapper.text()).not.toContain('activity.sources_sync_all')
})

test('unconfigured paths gate the dashboard toward Settings', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ ...CONFIGURED, rekordbox_db_path: '', storage_root: '' }),
    }),
  )
  const wrapper = mountDashboard()
  await flushPromises()
  expect(wrapper.text()).toContain('Presque prêt')
  expect(wrapper.find('.hero').exists()).toBe(false)
})
