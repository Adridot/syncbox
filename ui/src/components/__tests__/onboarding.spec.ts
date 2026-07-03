import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { router } from '../../router'
import { ONBOARDING_DONE_KEY, ONBOARDING_STEPS, useOnboardingStore } from '../../stores/onboarding'
import OnboardingOverlay from '../OnboardingOverlay.vue'

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  localStorage.clear()
  i18n.global.locale.value = 'fr'
})
afterEach(() => vi.unstubAllGlobals())

test('the flow is exactly 10 bi-phase steps (4 setup + 6 tour), §11.4', () => {
  expect(ONBOARDING_STEPS).toHaveLength(10)
  expect(ONBOARDING_STEPS.filter((s) => s.phase === 'setup')).toHaveLength(4)
  expect(ONBOARDING_STEPS.filter((s) => s.phase === 'tour')).toHaveLength(6)
  // the deprecated "module" step and "acquisition" naming are gone (M4-PLAN §6)
  const keys = ONBOARDING_STEPS.map((s) => s.key)
  expect(keys).not.toContain('module')
  expect(keys).not.toContain('acquisition')
  expect(keys).toContain('missing')
})

test('maybeStart shows onboarding only when the done-flag is absent', () => {
  const store = useOnboardingStore()
  store.maybeStart()
  expect(store.active).toBe(true)

  store.finish()
  expect(store.active).toBe(false)
  expect(localStorage.getItem(ONBOARDING_DONE_KEY)).toBe('1')

  const store2 = useOnboardingStore()
  store2.maybeStart()
  expect(store2.active).toBe(false) // flag present -> not shown again
})

test('clickable rail jumps to a step; skip sets the done-flag', () => {
  const store = useOnboardingStore()
  store.start()
  const wrapper = mount(OnboardingOverlay, { global: { plugins: [i18n, pinia, router] } })

  // rail shows all 10 steps
  expect(wrapper.findAll('.rail-item')).toHaveLength(10)
  // jump to the "events" step via the rail
  const eventsIndex = ONBOARDING_STEPS.findIndex((s) => s.key === 'events')
  wrapper.findAll('.rail-item')[eventsIndex].trigger('click')
  expect(store.index).toBe(eventsIndex)

  // 10 progress dots
  expect(wrapper.findAll('.dot')).toHaveLength(10)

  // skip finishes + persists
  wrapper.find('.skip').trigger('click')
  expect(store.active).toBe(false)
  expect(localStorage.getItem(ONBOARDING_DONE_KEY)).toBe('1')
})
