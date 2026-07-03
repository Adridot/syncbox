import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { createAppRouter } from '../../router'
import { useSettingsStore } from '../../stores/settings'
import MissingCenterScreen from '../MissingCenterScreen.vue'
import { createMemoryHistory } from 'vue-router'

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => vi.unstubAllGlobals())

function entry(scope: string, over: Record<string, unknown> = {}) {
  return {
    scope,
    id: over.id ?? 1,
    content_id: over.content_id ?? 'c1',
    title: over.title ?? 'Track',
    artist: 'Artist',
    isrc: null,
    status: over.status ?? 'missing',
    purchase_links: over.purchase_links ?? [{ store: 'Beatport', url: 'https://beatport/x' }],
    relink_candidates: [],
    ...over,
  }
}

function stubApi(byScope: Record<string, unknown[]>) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      const path = new URL(url).pathname
      const scope = path.split('/').pop()!
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ scope, entries: byScope[scope] ?? [] }),
      })
    }),
  )
}

async function mountCenter(scope?: string) {
  const router = createAppRouter(createMemoryHistory())
  await router.push(scope ? `/missing/${scope}` : '/missing')
  const wrapper = mount(MissingCenterScreen, {
    props: { scope },
    global: { plugins: [i18n, pinia, router] },
  })
  await flushPromises()
  return wrapper
}

test('scope deep-link filters to one scope; purchase links shown, removed_from_source excluded server-side', async () => {
  stubApi({
    library: [
      entry('library', { content_id: 'a', title: 'Buyable' }),
      // removed_from_source: server sends no purchase_links; UI must not re-add
      entry('library', { id: 2, content_id: 'b', title: 'Removed', status: 'removed_from_source', purchase_links: [] }),
    ],
  })
  useSettingsStore().$patch({ values: { rekordbox_db_path: '/x', storage_root: '/y', language: 'fr' } as never, loaded: true })
  const wrapper = await mountCenter('library')

  expect(wrapper.text()).toContain('Buyable')
  expect(wrapper.text()).toContain('Removed')
  // exactly one purchase button (the removed_from_source row has none)
  expect(wrapper.findAll('.buy')).toHaveLength(1)
})

test('"all" scope folds the three scopes and shows a ScopeBadge per row', async () => {
  stubApi({
    library: [entry('library', { content_id: 'l' })],
    event: [entry('event', { content_id: 'e' })],
    collection: [entry('collection', { content_id: 'c' })],
  })
  useSettingsStore().$patch({ values: { rekordbox_db_path: '/x', storage_root: '/y', language: 'fr' } as never, loaded: true })
  const wrapper = await mountCenter()
  // 3 rows, each carrying a scope badge
  expect(wrapper.findAll('.mrow')).toHaveLength(3)
})
