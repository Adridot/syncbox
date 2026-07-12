import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { router } from '../../router'
import { useHealthStore } from '../../stores/health'
import { useStatusStore } from '../../stores/status'
import DuplicatesTab from '../health/DuplicatesTab.vue'
import SmartFixesTab from '../health/SmartFixesTab.vue'
import UntaggedTab from '../health/UntaggedTab.vue'

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  i18n.global.locale.value = 'fr'
})
afterEach(() => vi.unstubAllGlobals())

const GROUP = {
  key: 'g1',
  method: 'isrc',
  confidence: 99,
  warning: false,
  members: [
    {
      content_id: 'c1',
      title: 'Voodoo Ray',
      artist: 'A Guy Called Gerald',
      bit_rate: 1411,
      file_missing: false,
      ownership: 'permanent_library' as const,
      playlist_count: 3,
      cue_count: 5,
      resolved_path: '/music/a.flac',
      quality_verdict: 'ok' as const,
      quality_reason: 'lossless_container_full_spectrum',
    },
    {
      content_id: 'c2',
      title: 'Voodoo Ray',
      artist: 'A Guy Called Gerald',
      bit_rate: 320,
      file_missing: false,
      ownership: 'external' as const,
      playlist_count: 0,
      cue_count: 0,
      resolved_path: '/music/b.mp3',
      quality_verdict: 'lossy_source_probable' as const,
      quality_reason: 'cutoff_indicates_le192_source',
    },
  ],
  keeper: { content_id: 'c1', reason: 'quality' },
}

const SMART_DRY = {
  payload: [
    { content_id: 'c1', field: 'title', before: 'CafÃ©  del Mar', after: 'Café del Mar' },
    { content_id: 'c2', field: 'remixer', before: null, after: 'Bicep' },
  ],
  fingerprint: [
    ['db', 10],
    ['wal', 5],
  ],
}

function stubScan({ fail = false, staleOnResolve = false } = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      const path = new URL(url).pathname
      if (path === '/api/duplicates/scan') {
        if (fail)
          return Promise.resolve({
            ok: false,
            status: 423,
            json: () =>
              Promise.resolve({
                error: 'mutation_blocked',
                message: 'Rekordbox est ouvert',
                message_key: 'rb_open',
              }),
          })
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({ groups: [GROUP], scanned: 1200, fingerprint: [['db', 1]] }),
        })
      }
      if (path === '/api/duplicates/resolve' && staleOnResolve)
        return Promise.resolve({
          ok: false,
          status: 409,
          json: () =>
            Promise.resolve({
              error: 'stale_snapshot',
              action: 'rerun_dry_run',
              message: 'stale',
            }),
        })
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ files: [] }) })
    }),
  )
}

function mountTab(component: typeof DuplicatesTab | typeof UntaggedTab) {
  return mount(component, { global: { plugins: [i18n, pinia, router] } })
}

function mountSmartFixes() {
  return mount(SmartFixesTab, {
    global: { plugins: [i18n, pinia, router], stubs: { teleport: true } },
  })
}

test('B1: a failed scan click surfaces the backend message — never a silent no-op', async () => {
  stubScan({ fail: true })
  const wrapper = mountTab(DuplicatesTab)
  await wrapper.get('.scan').trigger('click')
  await flushPromises()
  expect(wrapper.get('.banner[data-tone="error"]').text()).toContain('Rekordbox')
})

test('scan fills the store; resolve echoes the fingerprint and 409 invites a re-scan', async () => {
  stubScan({ staleOnResolve: true })
  const wrapper = mountTab(DuplicatesTab)
  await wrapper.get('.scan').trigger('click')
  await flushPromises()

  expect(useHealthStore().duplicateGroups).toBe(1)
  expect(wrapper.text()).toContain('Voodoo Ray')
  expect(wrapper.text()).toContain('conservé : meilleure qualité')
  expect(wrapper.text()).toContain('Bibliothèque permanente')
  expect(wrapper.text()).toContain('Externe')
  expect(wrapper.text()).not.toContain('protégé')

  await wrapper.get('.resolve').trigger('click')
  await flushPromises()
  const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>
  const resolveCall = fetchMock.mock.calls.find(([url]) =>
    String(url).includes('/api/duplicates/resolve'),
  )
  expect(JSON.parse(resolveCall![1].body as string).fingerprint).toEqual([['db', 1]])
  expect(wrapper.get('.banner[data-tone="error"]').text()).toContain('relance')
})

test('resolve CTA reflects the RB guard', async () => {
  stubScan()
  useStatusStore().rbOpen = true
  const wrapper = mountTab(DuplicatesTab)
  await wrapper.get('.scan').trigger('click')
  await flushPromises()
  const resolve = wrapper.get('.resolve')
  expect(resolve.attributes('disabled')).toBeDefined()
  expect(resolve.text()).toContain('Rekordbox ouvert — bloqué')
})

test('smart fixes only advertises fixes the server actually runs', () => {
  const wrapper = mountSmartFixes()
  const families = wrapper.findAll('.family').map((family) => family.findAll('span')[1].text())
  expect(families).toEqual([
    'Nettoyer les URL de site finales, séparateurs orphelins et espaces Unicode ; normaliser Unicode en NFC',
    'Réparer certaines signatures courantes et réversibles de mojibake UTF-8 / latin-1 / Windows-1252 et les entités XML nommées exactes &amp; &quot; &apos; &lt; &gt;',
    'Extraire uniquement les crédits finaux artiste invité et remixeur non ambigus',
  ])
  expect(wrapper.text()).toContain('le titre du remix est conservé')
  expect(wrapper.text()).toContain('noms stylisés en majuscules ou en casse mixte restent inchangés')
  expect(wrapper.text()).toContain('motifs ambigus sont ignorés')
  expect(wrapper.text()).not.toContain('Normaliser la casse')
})

test('smart-fix preview stays available with Rekordbox open and execute echoes the exact payload', async () => {
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    const path = new URL(url).pathname
    const body =
      path === '/api/smartfixes/dry-run'
        ? SMART_DRY
        : { fields_applied: 2, tracks_touched: 2 }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) })
  })
  vi.stubGlobal('fetch', fetchMock)
  const status = useStatusStore()
  status.rbOpen = true

  const wrapper = mountSmartFixes()
  const preview = wrapper.get('.dryrun-cta')
  expect(preview.attributes('disabled')).toBeUndefined()
  await preview.trigger('click')
  await flushPromises()

  const confirm = wrapper.get('.confirm')
  expect(confirm.attributes('disabled')).toBeDefined()
  expect(confirm.text()).toContain('Rekordbox ouvert — bloqué')

  status.rbOpen = false
  await wrapper.vm.$nextTick()
  const enabledConfirm = wrapper.get('.confirm')
  expect((enabledConfirm.element as HTMLButtonElement).disabled).toBe(false)
  await enabledConfirm.trigger('click')
  await flushPromises()

  const executeCall = fetchMock.mock.calls.find(([url]) =>
    String(url).includes('/api/smartfixes/execute'),
  )
  expect(JSON.parse(executeCall![1].body as string)).toEqual({
    payload: SMART_DRY.payload,
    fingerprint: SMART_DRY.fingerprint,
  })
  expect(wrapper.get('.banner').attributes('role')).toBe('status')
  expect(wrapper.text()).toContain('2 champs écrits sur 2 tracks')
})

test('smart-fix stale execution stays in the modal and a rerun refreshes the preview', async () => {
  let previews = 0
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      const path = new URL(url).pathname
      if (path === '/api/smartfixes/dry-run') {
        previews += 1
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(SMART_DRY),
        })
      }
      return Promise.resolve({
        ok: false,
        status: 409,
        json: () =>
          Promise.resolve({
            error: 'stale_snapshot',
            action: 'rerun_dry_run',
            message: 'stale',
          }),
      })
    }),
  )

  const wrapper = mountSmartFixes()
  await wrapper.get('.dryrun-cta').trigger('click')
  await flushPromises()
  await wrapper.get('.confirm').trigger('click')
  await flushPromises()
  expect(wrapper.get('.stale').attributes('role')).toBe('alert')
  expect(wrapper.get('.confirm').attributes('disabled')).toBeDefined()

  await wrapper.get('.stale button').trigger('click')
  await flushPromises()
  expect(previews).toBe(2)
  expect(wrapper.find('.stale').exists()).toBe(false)
})

test('smart-fix preview failures are announced and dismissible by name', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ error: 'invalid_request', message: 'Invalid paths' }),
    }),
  )
  const wrapper = mountSmartFixes()
  await wrapper.get('.dryrun-cta').trigger('click')
  await flushPromises()
  expect(wrapper.get('.banner').attributes('role')).toBe('alert')
  expect(wrapper.get('.banner-close').attributes('aria-label')).toBe('Fermer')
})

test('untagged selection binds to the visible filter (§9 regression)', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      const path = new URL(url).pathname
      const payloads: Record<string, unknown> = {
        '/api/untagged': {
          tracks: [
            {
              content_id: 'u1',
              title: 'spotify:track:x',
              artist: '',
              ownership: 'app_managed',
              category: 'junk',
            },
            {
              content_id: 'u2',
              title: 'Track A',
              artist: 'B',
              ownership: 'external',
              category: 'review',
            },
          ],
        },
        '/api/untagged/patterns': { patterns: [] },
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(payloads[path] ?? {}),
      })
    }),
  )
  const wrapper = mountTab(UntaggedTab)
  await flushPromises()
  expect(wrapper.text()).toContain('Géré par Syncbox')
  expect(wrapper.text()).toContain('Externe')
  expect(wrapper.text()).toContain('l’audio n’est jamais touché')

  // select everything visible under "junk"
  const chips = wrapper.findAll('.chip')
  await chips[1].trigger('click') // junk
  await wrapper.get('.table-head input[type="checkbox"]').setValue(true)
  expect(wrapper.text()).toContain('1 sélectionné(s)')

  // switching filters clears the selection — hidden rows are never acted on
  await chips[4].trigger('click') // review
  expect(wrapper.text()).not.toContain('sélectionné(s)')
})
