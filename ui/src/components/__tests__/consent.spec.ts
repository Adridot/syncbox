import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { type ApiError, api, setConsentBroker } from '../../api/client'
import { i18n } from '../../i18n'
import { useConsentStore } from '../../stores/consent'
import ConsentModal from '../ConsentModal.vue'

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  const consent = useConsentStore()
  setConsentBroker((body) => consent.request(body))
})
afterEach(() => {
  vi.unstubAllGlobals()
  setConsentBroker(null)
})

function mountModal() {
  return mount(ConsentModal, { global: { plugins: [i18n, pinia] }, attachTo: document.body })
}

test('428 anlz: modal appears, requires the named checkbox, re-calls with the consent flag', async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({
      ok: false,
      status: 428,
      json: () => Promise.resolve({ error: 'consent_required', consent: 'anlz', message: 'cues' }),
    })
    .mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve({ stored_path: '/x' }) })
  vi.stubGlobal('fetch', fetchMock)

  const wrapper = mountModal()
  const pending = api.post('/api/missing/collection/1/relink', { path: '/f.aiff' })
  await flushPromises()

  // modal shown; proceed disabled until the checkbox is ticked
  expect(document.body.textContent).toContain('Remplacer cette association')
  const proceed = document.body.querySelector('.btn-danger') as HTMLButtonElement
  expect(proceed.disabled).toBe(true)

  const checkbox = document.body.querySelector('.consent-check input') as HTMLInputElement
  checkbox.checked = true
  checkbox.dispatchEvent(new Event('change'))
  await flushPromises()
  proceed.click()

  const result = await pending
  expect(result).toEqual({ stored_path: '/x' })
  // the re-call carried the anlz_consent flag; consent is not remembered
  expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ path: '/f.aiff', anlz_consent: true })
  wrapper.unmount()
})

test('concurrent 428s are queued, not overwritten — each promise resolves', async () => {
  // both mutations return 428, then 200 on the consented re-call
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({ ok: false, status: 428, json: () => Promise.resolve({ error: 'consent_required', consent: 'anlz', message: 'a' }) })
    .mockResolvedValueOnce({ ok: false, status: 428, json: () => Promise.resolve({ error: 'consent_required', consent: 'anlz', message: 'b' }) })
    .mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({ done: true }) })
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mountModal()

  const a = api.post('/api/missing/collection/1/relink', { path: '/a' })
  const b = api.post('/api/missing/collection/2/relink', { path: '/b' })
  await flushPromises()

  const consent = useConsentStore()
  // both are queued — the first blocker's overwrite bug would drop one
  expect(consent.queue.length).toBe(2)

  // grant the head twice (checkbox each time)
  const grantHead = async () => {
    const cb = document.body.querySelector('.consent-check input') as HTMLInputElement
    cb.checked = true
    cb.dispatchEvent(new Event('change'))
    await flushPromises()
    ;(document.body.querySelector('.btn-danger') as HTMLButtonElement).click()
    await flushPromises()
  }
  await grantHead()
  await grantHead()

  // both original mutations complete — neither promise is stranded
  expect(await a).toEqual({ done: true })
  expect(await b).toEqual({ done: true })
  wrapper.unmount()
})

test('denying the consent rejects the mutation and does not re-call', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: false,
    status: 428,
    json: () => Promise.resolve({ error: 'consent_required', consent: 'permanent_delete', message: 'perm', path: '/f' }),
  })
  vi.stubGlobal('fetch', fetchMock)

  const wrapper = mountModal()
  const pending = api.post('/api/duplicates/resolve', {}).catch((e) => e)
  await flushPromises()

  const cancel = document.body.querySelector('.btn-ghost') as HTMLButtonElement
  cancel.click()
  const error = (await pending) as ApiError
  expect(error.code).toBe('consent_required')
  expect(fetchMock).toHaveBeenCalledTimes(1)
  wrapper.unmount()
})
