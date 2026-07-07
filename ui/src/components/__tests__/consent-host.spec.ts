import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { api } from '../../api/client'
import { i18n } from '../../i18n'
import ConsentHost from '../ConsentHost.vue'

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.unstubAllGlobals())

function stub428Api() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const path = new URL(url).pathname
      const body = init?.body ? JSON.parse(init.body as string) : {}
      const ok = (payload: unknown) =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload) })
      const consent = (payload: unknown) =>
        Promise.resolve({ ok: false, status: 428, json: () => Promise.resolve(payload) })
      if (path === '/relink')
        return body.anlz_consent
          ? ok({ relinked: true })
          : consent({ error: 'consent_required', message: 'anlz needed', consent: 'anlz' })
      if (path === '/resolve')
        return body.consent_to_permanent_delete
          ? ok({ resolved: true })
          : consent({
              error: 'consent_required',
              message: 'permanent',
              consent: 'permanent_delete',
              path: '/vol/x.aiff',
            })
      return ok({})
    }),
  )
}

test('concurrent 428 consents queue FIFO through the broker — none is lost', async () => {
  stub428Api()
  const wrapper = mount(ConsentHost, {
    global: { plugins: [i18n], stubs: { teleport: true } },
  })
  await flushPromises()

  // two concurrent consent-guarded calls
  const relink = api.post<{ relinked: boolean }>('/relink', {})
  const resolve = api.post<{ resolved: boolean }>('/resolve', {})
  await flushPromises()

  // the FIRST (anlz) shows; the permanent-delete one waits in the queue
  expect(wrapper.text()).toContain('Remplacer le fichier')
  expect(wrapper.text()).not.toContain('Suppression irréversible')

  // grant: checkbox arms the CTA, confirm re-calls once with the flag
  await wrapper.get('input[type="checkbox"]').setValue(true)
  await wrapper.get('.confirm').trigger('click')
  await expect(relink).resolves.toEqual({ relinked: true })
  await flushPromises()

  // the queued consent now shows, with its path
  expect(wrapper.text()).toContain('Suppression irréversible')
  expect(wrapper.text()).toContain('/vol/x.aiff')

  // refuse -> the original 428 propagates to the caller
  await wrapper.get('.btn-secondary').trigger('click')
  await expect(resolve).rejects.toMatchObject({ status: 428 })

  wrapper.unmount()
})
