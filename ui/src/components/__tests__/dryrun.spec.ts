import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { useStatusStore } from '../../stores/status'
import DryRunModal from '../DryRunModal.vue'

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const DRY = {
  payload: [{ content_id: '1', field: 'title', before: 'Song  Twice', after: 'Song Twice' }],
  skipped_protected: [{ content_id: 'p1', name: 'Artist - Protected' }],
  fingerprint: [['db', 1]],
}

// ModalShell teleports to <body>, so assert against document.body.
function mountModal() {
  return mount(DryRunModal, { global: { plugins: [i18n, pinia] }, attachTo: document.body })
}

test('dry-run preview: before→after rows, protected opt-in named, CTA carries the exact count', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve(DRY) }),
  )
  const wrapper = mountModal()
  await flushPromises()

  expect(document.body.textContent).toContain('Song Twice')
  expect(document.body.textContent).toContain('Artist - Protected') // protected named
  const cta = document.body.querySelector('.guarded') as HTMLElement
  expect(cta.textContent).toContain('Confirmer & écrire (1)')
  wrapper.unmount()
})

test('stale fingerprint on execute shows the re-run banner, no silent write', async () => {
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    const path = new URL(url).pathname
    if (path === '/api/smartfixes/dry-run')
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(DRY) })
    return Promise.resolve({
      ok: false,
      status: 409,
      json: () => Promise.resolve({ error: 'stale_snapshot', action: 'rerun_dry_run', message: 'stale' }),
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mountModal()
  await flushPromises()

  ;(document.body.querySelector('.guarded') as HTMLButtonElement).click()
  await flushPromises()
  expect(document.body.textContent).toContain('La collection a changé')
  expect((document.body.querySelector('.btn-accent') as HTMLElement).textContent).toContain(
    "Relancer l'aperçu",
  )
  wrapper.unmount()
})

test('CTA reflects the RB-open guard', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve(DRY) }),
  )
  useStatusStore().rbOpen = true
  const wrapper = mountModal()
  await flushPromises()
  expect(document.body.querySelector('.guarded[data-blocked="true"]')).not.toBeNull()
  wrapper.unmount()
})
