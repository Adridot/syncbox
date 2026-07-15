import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, expect, test } from 'vitest'

import type { SmartFixesDryRun } from '../../api/types'
import { i18n } from '../../i18n'
import DryRunModal from '../DryRunModal.vue'

beforeEach(() => {
  setActivePinia(createPinia())
  i18n.global.locale.value = 'fr'
})

const DRY: SmartFixesDryRun = {
  payload: [
    // invisible-only change: trailing space stripped — looks identical
    { content_id: 'c1', field: 'artist', before: 'Carole Fredericks ', after: 'Carole Fredericks' },
    { content_id: 'c2', field: 'remixer', before: null, after: 'Bicep' },
  ],
  fingerprint: [['db', 1]],
}

function mountModal(overrides: Record<string, unknown> = {}) {
  return mount(DryRunModal, {
    props: {
      dry: DRY,
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

test('renders nullable values, localized fields, exact track IDs and an accessible name', () => {
  const wrapper = mountModal()
  const dialog = wrapper.get('[role="dialog"]')
  expect(dialog.attributes('aria-labelledby')).toBe('smartfixes-dryrun-title')
  expect(wrapper.get('#smartfixes-dryrun-title').text()).toBe('Aperçu des corrections')

  const rows = wrapper.findAll('.change')
  expect(rows[0].text()).toContain('Artiste')
  expect(rows[0].text()).toContain('ID du track c1')
  expect(rows[1].text()).toContain('Remixeur')
  expect(rows[1].text()).toContain('ID du track c2')
  expect(rows[1].get('.before').text()).toBe('Non renseigné')
})

test('renders an empty string distinctly and disables execution for a no-op preview', () => {
  const emptyValue = mountModal({
    dry: {
      payload: [{ content_id: 'c3', field: 'artist', before: '', after: 'Artist' }],
      fingerprint: [['db', 1]],
    },
  })
  expect(emptyValue.get('.before').text()).toBe('Valeur vide')

  const noOp = mountModal({ dry: { payload: [], fingerprint: [['db', 1]] } })
  expect(noOp.text()).toContain('Rien à corriger')
  expect(noOp.text()).toContain('aucun changement de champ')
  expect(noOp.get('.confirm').attributes('disabled')).toBeDefined()
})

test('stale shows the banner + rerun CTA and disables the write CTA', () => {
  const wrapper = mountModal({ stale: true })
  expect(wrapper.text()).toContain('relance le dry-run')
  expect(wrapper.get('.stale').attributes('role')).toBe('alert')
  expect(wrapper.get('.confirm').attributes('disabled')).toBeDefined()
})

test('announces execution errors and disables rerun while busy', () => {
  const failed = mountModal({ error: 'Write failed' })
  expect(failed.get('.error-row').attributes('role')).toBe('alert')

  const rerunning = mountModal({ stale: true, busy: true })
  expect(rerunning.get('.stale button').attributes('disabled')).toBeDefined()
  expect(rerunning.get('.confirm').text()).toBe('Chargement…')
})
