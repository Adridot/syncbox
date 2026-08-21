/* add-event-track-removal (task 5.1): the batch is built from the departure
   signal. Selection must be grouped and floating — the table geometry cannot
   move when a selection starts — and it must survive the virtualized rows. */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { i18n } from '../../i18n'
import { router } from '../../router'
import EventsScreen from '../EventsScreen.vue'

let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  i18n.global.locale.value = 'fr'
})
afterEach(() => vi.unstubAllGlobals())

const row = (over: Record<string, unknown>) => ({
  id: 1,
  event_id: 1,
  spotify_track_id: 'sp1',
  title: 'T',
  artist: 'A',
  duration_ms: null,
  isrc: null,
  status: 'ready',
  content_id: null,
  confidence: 100,
  staging_file_path: null,
  added_after_apply: 0,
  prior_status: null,
  origin: 'playlist',
  adopted: false,
  duplicates_collection: false,
  duplicate_title: null,
  duplicate_artist: null,
  ...over,
})

const TRACKS = [
  row({ id: 1, title: 'Still There', status: 'applied' }),
  row({ id: 2, title: 'Gone One', status: 'removed_upstream', prior_status: 'applied' }),
  row({ id: 3, title: 'Gone Two', status: 'removed_upstream', prior_status: 'applied' }),
  // already withdrawn by an earlier removal: outstanding work for nobody
  row({ id: 4, title: 'Withdrawn', status: 'removed', prior_status: 'applied' }),
]

const EVENT = {
  id: 1,
  name: 'jo-helo',
  slug: 'jo-helo',
  default_tag: 'Situation:jo-helo',
  spotify_playlist_id: '37i9dQZF1DXcBWIGoYBM5M',
  staging_dir: '/s',
  status: 'applied',
  applied_at: '2026-08-01T10:00:00',
  created_at: '2026-08-01',
  n_tracks: TRACKS.length,
  pending_delta: 0,
  removed_upstream: 2,
}

const PLAN = {
  plan_version: 1,
  event_id: 1,
  needs_rekordbox: true,
  tracks: [
    {
      track_id: 2,
      content_id: 'c2',
      title: 'Gone One',
      artist: 'A',
      action: 'delete_with_event',
      source_path: '/s/gone-one.flac',
      file_deleted: true,
    },
    {
      track_id: 3,
      content_id: 'c3',
      title: 'Gone Two',
      artist: 'A',
      action: 'keep_in_place',
      source_path: '/lib/gone-two.aiff',
      file_deleted: false,
    },
  ],
  expected_file_deletions: ['/s/gone-one.flac'],
  validation: {},
  fingerprint: [],
}

function mountScreen() {
  let current: unknown[] = TRACKS
  let summary: Record<string, unknown> = EVENT
  const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const path = new URL(url).pathname
    const body = JSON.parse((init?.body as string) || '{}')
    if (path === '/api/events/1/tracks/remove' && body.dry_run === false) {
      // the sidecar withdraws the rows: status 'removed', signal cleared
      current = current.map((track) =>
        [2, 3].includes((track as { id: number }).id)
          ? { ...(track as object), status: 'removed' }
          : track,
      )
      summary = { ...summary, removed_upstream: 0 }
    }
    const payloads: Record<string, unknown> = {
      '/api/events': { events: [summary] },
      '/api/events/1': { ...summary, tracks: current },
      '/api/events/1/tracks/remove':
        body.dry_run === false ? { ...PLAN, dry_run: false } : PLAN,
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(payloads[path] ?? {}),
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(EventsScreen, {
    global: { plugins: [i18n, pinia, router], stubs: { teleport: true } },
  })
  return { wrapper, fetchMock }
}

const chip = (wrapper: ReturnType<typeof mount>, label: string) =>
  wrapper.findAll('.chip').find((c) => c.text().startsWith(label))

test('5.1 a withdrawn track is outstanding work for nobody', async () => {
  const { wrapper } = mountScreen()
  await flushPromises()

  // 'removed' is SIDELINED: out of the counts and out of every chip
  expect(wrapper.get('.legend').text()).toContain('1')
  expect(wrapper.findAll('.v-rows .row')).toHaveLength(1)
  expect(wrapper.text()).not.toContain('Withdrawn')
  expect(chip(wrapper, 'Partis')!.text()).toContain('2')
  wrapper.unmount()
})

test('5.1 the batch is picked in the departures view, through a floating bar', async () => {
  const { wrapper } = mountScreen()
  await flushPromises()

  // no pick column anywhere else: it would always read zero there
  expect(wrapper.find('.cell-pick').exists()).toBe(false)

  await chip(wrapper, 'Partis')!.trigger('click')
  const rows = wrapper.findAll('.v-rows .row')
  expect(rows).toHaveLength(2)
  // the anchor is in the DOM before any pick: the table cannot shift
  expect(wrapper.find('.sel-float-anchor').exists()).toBe(true)
  expect(wrapper.find('.selection-float').exists()).toBe(false)

  await rows[0].get('.cell-pick input').setValue(true)
  expect(wrapper.get('.selection-float').text()).toContain('1')

  // select-all covers the filtered rows only
  await wrapper.get('.table-head .cell-pick input').setValue(true)
  expect(wrapper.get('.sel-remove').text()).toContain('2')
  wrapper.unmount()
})

test('5.1 confirming the removal reloads the event and clears the signal', async () => {
  const { wrapper, fetchMock } = mountScreen()
  await flushPromises()
  await chip(wrapper, 'Partis')!.trigger('click')
  await wrapper.get('.table-head .cell-pick input').setValue(true)
  await wrapper.get('.sel-remove').trigger('click')
  await flushPromises()

  // the preview asks for exactly the picked rows
  expect(JSON.parse(fetchMock.mock.calls.at(-1)![1].body as string)).toEqual({
    track_ids: [2, 3],
    dry_run: true,
  })
  await wrapper.get('.confirm').trigger('click')
  await flushPromises()

  expect(wrapper.get('.banner[data-tone="success"]').text()).toContain('2')
  expect(wrapper.find('.selection-float').exists()).toBe(false)
  expect(wrapper.find('.dep-badge').exists()).toBe(false)
  expect(chip(wrapper, 'Partis')!.text()).toContain('0')
  wrapper.unmount()
})

test('5.1 changing the view drops a selection that no longer means anything', async () => {
  const { wrapper } = mountScreen()
  await flushPromises()
  await chip(wrapper, 'Partis')!.trigger('click')
  await wrapper.get('.table-head .cell-pick input').setValue(true)
  expect(wrapper.find('.selection-float').exists()).toBe(true)

  await chip(wrapper, 'Tous')!.trigger('click')
  expect(wrapper.find('.selection-float').exists()).toBe(false)
  expect(wrapper.find('.cell-pick').exists()).toBe(false)
  wrapper.unmount()
})
