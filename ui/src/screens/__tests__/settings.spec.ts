import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { router } from '../../router'
import SettingsScreen from '../SettingsScreen.vue'

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  i18n.global.locale.value = 'fr'
})
afterEach(() => vi.unstubAllGlobals())

const STORED = {
  spotify_client_id: '',
  rekordbox_db_path: '~/Library/Pioneer/rekordbox/master.db',
  storage_root: '/gone/away',
  backup_retention: 15,
  language: 'fr',
  match_confidence_threshold: 82,
  match_ambiguity_margin: 6,
  match_weights: { title: 0.52, artist: 0.36, duration: 0.12 },
  isrc_collision_policy: 'guarded',
}

function stubApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const path = new URL(url).pathname
      if (path === '/api/settings' && init?.method === 'PUT') {
        const body = JSON.parse(init.body as string)
        // the SERVER decides validity: storage_root '/gone/away' is not found
        if (body.storage_root === '/gone/away')
          return Promise.resolve({
            ok: false,
            status: 400,
            json: () =>
              Promise.resolve({
                error: 'invalid_request',
                message: 'storage_root: not found',
              }),
          })
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ ...STORED, ...body }),
        })
      }
      if (path === '/api/settings')
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(STORED) })
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
    }),
  )
}

function mountSettings() {
  return mount(SettingsScreen, { global: { plugins: [i18n, pinia, router] } })
}

test('B3: stored paths are re-validated on mount — ✕ + server message, never an optimistic ✓', async () => {
  stubApi()
  const wrapper = mountSettings()
  await flushPromises()

  const ticks = wrapper.findAll('.tick')
  // db path: server accepted the PUT -> real ✓
  expect(ticks[0].attributes('data-state')).toBe('valid')
  // storage root: pre-filled but NOT FOUND server-side -> ✕ + inline message
  expect(ticks[1].attributes('data-state')).toBe('invalid')
  expect(wrapper.text()).toContain('storage_root: not found')
  expect(wrapper.text()).toContain('Bibliothèque permanente (ton audio)')
  expect(wrapper.text()).toContain('/gone/away/rekordbox/')
  expect(wrapper.text()).not.toContain('Zone protégée')
})

test('R1: the connect CTA is gated while spotify_client_id is empty, with an actionable note', async () => {
  stubApi()
  const wrapper = mountSettings()
  await flushPromises()

  const connect = wrapper.get('.spotify-row .btn-primary')
  expect(connect.attributes('disabled')).toBeDefined()
  expect(wrapper.text()).toContain('Renseigne ton Client ID Spotify')
  // the inline help walks through creating the app, redirect URI verbatim
  expect(wrapper.text()).toContain('Créer mon app Spotify, pas à pas')
  expect(wrapper.text()).toContain('http://127.0.0.1:8765/callback')
})

test('G4: the weights sum is validated client-side before any PUT', async () => {
  stubApi()
  const wrapper = mountSettings()
  await flushPromises()

  const weightInputs = wrapper.findAll('.weight input')
  await weightInputs[0].setValue('0.9') // 0.9 + 0.36 + 0.12 = 1.38
  await flushPromises()

  expect(wrapper.text()).toContain('doivent sommer exactement à 1.00')
  const save = wrapper
    .findAll('.advanced-actions .btn-primary')
    .find((button) => button.text() === 'Enregistrer')
  expect(save!.attributes('disabled')).toBeDefined()
})
