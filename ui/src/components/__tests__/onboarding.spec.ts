import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { completeOnboarding, onboardingVisible, replayOnboarding } from '../../lib/onboarding'
import OnboardingOverlay from '../OnboardingOverlay.vue'

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  localStorage.clear()
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const path = new URL(url).pathname
      if (path === '/api/readouts')
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ total_tracks: 1240 }),
        })
      if (path === '/api/settings' && init?.method === 'PUT')
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(JSON.parse(init.body as string)),
        })
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
    }),
  )
})
afterEach(() => vi.unstubAllGlobals())

const mountOverlay = () =>
  mount(OnboardingOverlay, { global: { plugins: [i18n, pinia] } })

test('bi-phase rail: exactly 10 clickable steps — 4 Configuration + 6 Prise en main (§11.4)', async () => {
  const wrapper = mountOverlay()
  await flushPromises()

  const rows = wrapper.findAll('.rail-row')
  expect(rows).toHaveLength(10)
  expect(wrapper.text()).toContain('Configuration')
  expect(wrapper.text()).toContain('Prise en main')
  // no deprecated "Module" step, missing tracks replaces acquisition
  expect(wrapper.text()).not.toContain('Module')
  expect(wrapper.text()).toContain('Missing tracks')

  // the rail is clickable: jump straight to the last step
  await rows[9].trigger('click')
  expect(wrapper.text()).toContain('Applique un event en smart playlist')
})

test('the scan step performs a REAL read and reports the collection size', async () => {
  const wrapper = mountOverlay()
  await flushPromises()

  await wrapper.findAll('.rail-row')[3].trigger('click') // Premier scan
  await wrapper.get('.btn-primary').trigger('click')
  await flushPromises()

  expect(wrapper.text()).toContain('1240 tracks trouvés')
})

test('skip and the final CTA set the done flag; replay resets it', async () => {
  replayOnboarding()
  expect(onboardingVisible.value).toBe(true)

  const wrapper = mountOverlay()
  await flushPromises()
  await wrapper.get('.skip').trigger('click')
  expect(onboardingVisible.value).toBe(false)
  expect(localStorage.getItem('syncbox.onboarding-done')).toBe('1')

  replayOnboarding()
  expect(onboardingVisible.value).toBe(true)
  expect(localStorage.getItem('syncbox.onboarding-done')).toBeNull()
  completeOnboarding()
})
