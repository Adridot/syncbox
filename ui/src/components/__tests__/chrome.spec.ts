import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { useJobsStore } from '../../stores/jobs'
import { useStatusStore } from '../../stores/status'
import JobRow from '../JobRow.vue'
import ModalShell from '../ModalShell.vue'
import QualityBadge from '../QualityBadge.vue'
import RbGuardBanner from '../RbGuardBanner.vue'
import StatusBadge from '../StatusBadge.vue'

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => vi.unstubAllGlobals())

const global = () => ({ global: { plugins: [i18n, pinia] } })

test('ModalShell closes on esc and backdrop click, not on inner click', async () => {
  const wrapper = mount(ModalShell, {
    ...global(),
    attrs: { 'aria-labelledby': 'modal-title' },
    slots: { default: '<h2 id="modal-title">Title</h2><p class="inner">content</p>' },
    attachTo: document.body,
  })
  const backdrop = document.body.querySelector('.backdrop') as HTMLElement
  const modal = document.body.querySelector('.modal') as HTMLElement
  const inner = document.body.querySelector('.inner') as HTMLElement

  expect(modal.getAttribute('aria-labelledby')).toBe('modal-title')
  inner.click()
  expect(wrapper.emitted('close')).toBeUndefined()

  backdrop.click()
  expect(wrapper.emitted('close')).toHaveLength(1)

  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
  expect(wrapper.emitted('close')).toHaveLength(2)
  wrapper.unmount()
})

test('JobRow width is the REAL SSE pct (F16), hidden when no active job', async () => {
  const jobs = useJobsStore()
  const wrapper = mount(JobRow, {
    ...global(),
    props: { kind: 'duplicates.scan', label: 'Scan' },
  })
  expect(wrapper.find('.job-row').exists()).toBe(false)

  jobs.active['duplicates.scan'] = {
    job: 'j1',
    kind: 'duplicates.scan',
    done: 37,
    total: 100,
    pct: 37,
  }
  await wrapper.vm.$nextTick()
  expect(wrapper.get('.bar').attributes('style')).toContain('width: 37%')
  expect(wrapper.get('.pct').text()).toBe('37%')
})

test('RB banner re-polls /api/status on "J\'ai fermé Rekordbox"', async () => {
  const status = useStatusStore()
  status.rbOpen = true
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ rb_open: false, spotify_connected: true }),
  })
  vi.stubGlobal('fetch', fetchMock)

  const wrapper = mount(RbGuardBanner, global())
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:8765/api/status',
    expect.anything(),
  )
  expect(status.rbOpen).toBe(false)
})

test('StatusBadge maps the shared vocabulary to coherent tones', () => {
  const tones: Record<string, string> = {
    matched: 'accent',
    ready: 'teal',
    imported: 'success',
    conflict: 'warning',
    missing: 'danger',
    ignored: 'muted',
  }
  for (const [status, tone] of Object.entries(tones)) {
    const wrapper = mount(StatusBadge, { ...global(), props: { status } })
    expect(wrapper.get('.badge').attributes('data-tone'), status).toBe(tone)
  }
})

test('QualityBadge: uncertain is the cautious violet tone, never danger', () => {
  const wrapper = mount(QualityBadge, { ...global(), props: { verdict: 'incertain' } })
  expect(wrapper.get('.badge').attributes('data-tone')).toBe('uncertain')
})
