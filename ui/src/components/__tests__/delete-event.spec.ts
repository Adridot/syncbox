import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { useEventsStore } from '../../stores/events'
import DeleteEventModal from '../DeleteEventModal.vue'

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const PREVIEW = {
  tag_id: 't1',
  contents: [{ content_id: 'c1', title: 'Only', action: 'soft_delete', reason: 'event_only' }],
  playlists: [{ playlist_id: 'p1', name: 'Wedding' }],
  artifacts: ['/s/a.aiff', '/s/b.aiff'],
}

test('delete flow previews with dry_run then commits with dry_run:false (D11/D23, B10)', async () => {
  const bodies: Array<Record<string, unknown> | undefined> = []
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      bodies.push(init?.body ? JSON.parse(init.body as string) : undefined)
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(PREVIEW) })
    }),
  )
  const events = useEventsStore()
  events.current = {
    id: 5,
    name: 'Wedding',
    slug: 'wedding',
    status: 'applied',
    spotify_playlist_id: null,
    default_tag: 'Wedding',
    staging_dir: '/s',
    applied_at: null,
    n_tracks: 3,
    pending_delta: 0,
    tracks: [],
  }

  const wrapper = mount(DeleteEventModal, {
    global: { plugins: [i18n, pinia] },
    attachTo: document.body,
  })
  await flushPromises()

  // the preview call defaults to dry_run:true (empty body = preview)
  const previewBody = bodies[0]
  expect(previewBody === undefined || previewBody.dry_run === undefined || previewBody.dry_run === true).toBe(true)
  // preview counts are shown
  expect(document.body.textContent).toContain('2') // artifacts count

  // commit: the destructive call is explicit dry_run:false
  ;(document.body.querySelector('.guarded') as HTMLButtonElement).click()
  await flushPromises()
  const commitBody = bodies[bodies.length - 1]
  expect(commitBody).toMatchObject({ dry_run: false })
  wrapper.unmount()
})
