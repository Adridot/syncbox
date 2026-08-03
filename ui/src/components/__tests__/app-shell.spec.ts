import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import App from '../../App.vue'
import { i18n } from '../../i18n'
import { onboardingVisible } from '../../lib/onboarding'
import { useStatusStore } from '../../stores/status'

beforeEach(() => {
  localStorage.clear()
  onboardingVisible.value = false
})

afterEach(() => {
  onboardingVisible.value = false
})

test('the empty drag region stays separate from all shell content and controls', async () => {
  const pinia = createPinia()
  setActivePinia(pinia)
  const RoutedContent = {
    template: '<section data-testid="routed-content">Routed content</section>',
  }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'dashboard', component: RoutedContent },
      { path: '/library', name: 'library', component: RoutedContent },
      { path: '/events', name: 'events', component: RoutedContent },
      { path: '/history', name: 'history', component: RoutedContent },
      { path: '/health/:tab?', name: 'health', component: RoutedContent },
      { path: '/missing/:scope?', name: 'missing', component: RoutedContent },
      {
        path: '/settings',
        name: 'settings',
        component: { template: '<section data-testid="settings-content">Settings</section>' },
      },
    ],
  })
  await router.push('/')
  await router.isReady()

  const status = useStatusStore()
  status.rbOpen = true
  status.backendDown = true
  onboardingVisible.value = true

  const wrapper = mount(App, {
    global: {
      plugins: [pinia, i18n, router],
      stubs: {
        BackendDownOverlay: { template: '<div data-testid="backend-down">Backend down</div>' },
        ConsentHost: { template: '<div data-testid="consent-host">Consent</div>' },
        HealthPill: true,
        OnboardingOverlay: { template: '<div data-testid="onboarding">Onboarding</div>' },
        RbGuardBanner: { template: '<div data-testid="rb-banner">Banner</div>' },
      },
    },
  })
  await flushPromises()

  const dragRegion = wrapper.get('[data-tauri-drag-region]')
  expect(dragRegion.element.childElementCount).toBe(0)
  expect(
    dragRegion.findAll('a, button, input, select, textarea, [tabindex], [role="button"]'),
  ).toHaveLength(0)

  for (const selector of [
    '.brand',
    '.nav',
    '[data-testid="rb-banner"]',
    '[data-testid="routed-content"]',
    '[data-testid="backend-down"]',
    '[data-testid="consent-host"]',
    '[data-testid="onboarding"]',
  ]) {
    expect(dragRegion.element.contains(wrapper.get(selector).element), selector).toBe(false)
  }

  window.dispatchEvent(
    new KeyboardEvent('keydown', { key: ',', metaKey: true, cancelable: true }),
  )
  await flushPromises()
  expect(router.currentRoute.value.fullPath).toBe('/settings')

  wrapper.unmount()
})
