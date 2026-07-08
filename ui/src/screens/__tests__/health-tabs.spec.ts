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
      protected: false,
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
      protected: false,
      playlist_count: 0,
      cue_count: 0,
      resolved_path: '/music/b.mp3',
      quality_verdict: 'lossy_source_probable' as const,
      quality_reason: 'cutoff_indicates_le192_source',
    },
  ],
  keeper: { content_id: 'c1', reason: 'quality' },
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
  // Honesty invariant (§5.11): the ✓ catalog must match smartfixes.py CATALOG
  // (strip junk/URL + mojibake). 'extract' and 'case' are deferred, not shipped
  // — a ✓ next to a fix that never fires misleads the DJ.
  const wrapper = mount(SmartFixesTab, { global: { plugins: [i18n, pinia, router] } })
  const families = wrapper.findAll('.family').map((f) => f.text())
  expect(families).toHaveLength(2)
  expect(families.join(' | ')).toContain('URL')
  expect(families.join(' | ')).toContain('mojibake')
  expect(wrapper.text()).not.toContain('casse')
  expect(wrapper.text()).not.toContain('remixer')
})

test('untagged selection binds to the visible filter (§9 regression)', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      const path = new URL(url).pathname
      const payloads: Record<string, unknown> = {
        '/api/untagged': {
          tracks: [
            { content_id: 'u1', title: 'spotify:track:x', artist: '', protected: false, category: 'junk' },
            { content_id: 'u2', title: 'Track A', artist: 'B', protected: false, category: 'review' },
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

  // select everything visible under "junk"
  const chips = wrapper.findAll('.chip')
  await chips[1].trigger('click') // junk
  await wrapper.get('.table-head input[type="checkbox"]').setValue(true)
  expect(wrapper.text()).toContain('1 sélectionné(s)')

  // switching filters clears the selection — hidden rows are never acted on
  await chips[4].trigger('click') // review
  expect(wrapper.text()).not.toContain('sélectionné(s)')
})
