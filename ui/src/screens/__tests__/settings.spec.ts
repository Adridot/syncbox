import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { useSettingsStore } from '../../stores/settings'
import SettingsScreen from '../SettingsScreen.vue'

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  i18n.global.locale.value = 'fr'
})
afterEach(() => vi.unstubAllGlobals())

const SETTINGS = {
  spotify_client_id: '',
  rekordbox_db_path: '/rb/master.db',
  storage_root: '/music',
  backup_retention: 15,
  language: 'fr',
  match_confidence_threshold: 82,
  match_ambiguity_margin: 6,
  match_weights: { title: 0.52, artist: 0.36, duration: 0.12 },
  isrc_collision_policy: 'guarded',
}

function stubApi(putHandler?: (body: unknown) => unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.method === 'PUT' && putHandler) {
        const result = putHandler(JSON.parse(init.body as string))
        if (result instanceof Error) {
          return Promise.resolve({
            ok: false,
            status: 400,
            json: () => Promise.resolve({ error: 'invalid_request', message: result.message }),
          })
        }
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(SETTINGS) })
    }),
  )
}

function mountSettings() {
  return mount(SettingsScreen, { global: { plugins: [i18n, pinia] } })
}

test('derived read-only rows are shown for the storage subdirs', async () => {
  stubApi()
  useSettingsStore().$patch({ values: { ...SETTINGS } as never, loaded: true })
  const wrapper = mountSettings()
  await flushPromises()
  expect(wrapper.text()).toContain('/music/_rekordbox_sync/inbox')
  expect(wrapper.text()).toContain('/music/_rekordbox_sync/backups')
})

test('the download module + ARL card is NOT built (deprecated, M4-PLAN §6)', async () => {
  stubApi()
  useSettingsStore().$patch({ values: { ...SETTINGS } as never, loaded: true })
  const wrapper = mountSettings()
  await flushPromises()
  const text = wrapper.text().toLowerCase()
  expect(text).not.toContain('téléchargement')
  expect(text).not.toContain('arl')
  expect(text).not.toContain('deezer')
  expect(text).not.toContain('soundcloud')
})

test('G4 weights that do not sum to 1.00 block the save with a client error', async () => {
  const puts: unknown[] = []
  stubApi((body) => {
    puts.push(body)
    return SETTINGS
  })
  useSettingsStore().$patch({ values: { ...SETTINGS } as never, loaded: true })
  const wrapper = mountSettings()
  await flushPromises()

  // open Advanced
  await wrapper.find('.collapse-head').trigger('click')
  // break the sum: set title weight to 0.9 (sum 1.38)
  const titleInput = wrapper.findAll('.weight input')[0]
  await titleInput.setValue('0.9')
  await titleInput.trigger('change')
  await flushPromises()

  expect(wrapper.text()).toContain('doivent totaliser exactement 1.00')
  // no PUT carrying the invalid weights was sent
  expect(puts.some((p) => (p as { match_weights?: unknown }).match_weights)).toBe(false)
})

test('valid G4 weights are persisted via PUT', async () => {
  const puts: Array<Record<string, unknown>> = []
  stubApi((body) => {
    puts.push(body as Record<string, unknown>)
    return SETTINGS
  })
  useSettingsStore().$patch({ values: { ...SETTINGS } as never, loaded: true })
  const wrapper = mountSettings()
  await flushPromises()
  await wrapper.find('.collapse-head').trigger('click')

  const [titleInput, artistInput] = wrapper.findAll('.weight input')
  await titleInput.setValue('0.4')
  await artistInput.setValue('0.4') // 0.4 + 0.4 + 0.12 = 0.92... need duration 0.2
  const durationInput = wrapper.findAll('.weight input')[2]
  await durationInput.setValue('0.2')
  await durationInput.trigger('change')
  await flushPromises()

  const weightsPut = puts.find((p) => p.match_weights) as { match_weights: unknown } | undefined
  expect(weightsPut?.match_weights).toEqual({ title: 0.4, artist: 0.4, duration: 0.2 })
})
