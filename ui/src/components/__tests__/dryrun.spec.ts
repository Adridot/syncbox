import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, expect, test } from 'vitest'

import { i18n } from '../../i18n'
import DryRunModal from '../DryRunModal.vue'

beforeEach(() => setActivePinia(createPinia()))

const DRY = {
  payload: [
    // invisible-only change: trailing space stripped — looks identical
    { content_id: 'c1', field: 'artist', before: 'Carole Fredericks ', after: 'Carole Fredericks' },
    { content_id: 'c2', field: 'title', after: 'Sandstorm', before: 'SANDSTORM' },
  ],
  skipped_protected: [{ content_id: 'c9', name: 'Energy 52 - Café Del Mar' }],
  fingerprint: [['db', 1]],
}

function mountModal(overrides: Record<string, unknown> = {}) {
  return mount(DryRunModal, {
    props: {
      dry: DRY,
      includedIds: [],
      stale: false,
      busy: false,
      error: null,
      ...overrides,
    },
    global: { plugins: [i18n], stubs: { teleport: true } },
  })
}

test('B4: an identical-looking row shows its invisible whitespace as marked dots + legend', () => {
  const wrapper = mountModal()
  // the trailing space of the before value is rendered as a marked dot
  const marks = wrapper.findAll('.change .ws-mark')
  expect(marks.length).toBeGreaterThan(0)
  expect(marks[0].text()).toBe('·')
  // the legend explains the marks
  expect(wrapper.text()).toContain('espaces invisibles')
  // the CTA carries the EXACT payload count (B10)
  expect(wrapper.text()).toContain('Écrire 2 changements')
})

test('protected opt-in is named and NEVER pre-checked; stale disables the write CTA', async () => {
  const wrapper = mountModal({ stale: true })
  const optIn = wrapper.get('.protected-row input')
  expect((optIn.element as HTMLInputElement).checked).toBe(false)
  expect(wrapper.text()).toContain('Café Del Mar')
  // stale: banner + rerun CTA, write disabled
  expect(wrapper.text()).toContain('relance le dry-run')
  expect(wrapper.get('.confirm').attributes('disabled')).toBeDefined()
})
