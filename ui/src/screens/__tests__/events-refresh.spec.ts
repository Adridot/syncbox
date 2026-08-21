/* event-playlist-refresh: the workspace can re-read the event's Spotify
   playlist. Additions feed the existing pending delta; departures are a
   SIGNAL — nothing was written, nothing is owed — so they must read as a
   decision to make, never as work the re-apply will do. */
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
  row({ id: 1, title: 'Still There' }),
  row({ id: 2, title: 'Just Added', added_after_apply: 1 }),
  // left the playlist: keeps its previous state, awaits a decision
  row({ id: 3, title: 'Gone From Spotify', status: 'removed_upstream', prior_status: 'applied' }),
]

const EVENT = {
  id: 1,
  name: 'jo-helo',
  slug: 'jo-helo',
  default_tag: 'Situation:jo-helo',
  spotify_playlist_id: '37i9dQZF1DXcBWIGoYBM5M',
  staging_dir: '/s',
  status: 'partially_applied',
  applied_at: '2026-08-01T10:00:00',
  created_at: '2026-08-01',
  n_tracks: TRACKS.length,
  pending_delta: 1,
  removed_upstream: 1,
}

/** The kept track comes back bare from the POST, restored to `prior_status`. */
const KEPT = row({ id: 3, title: 'Gone From Spotify', status: 'applied', prior_status: null })

function mountScreen(
  event: Record<string, unknown> = EVENT,
  tracks: unknown[] = TRACKS,
  refresh: Record<string, number> = { added: 2, updated: 5, removed: 1 },
) {
  // stateful like the sidecar: the screen reloads after every mutation, so
  // the reload must see the new state, not the stale one
  let current = tracks
  let summary = event
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    const path = new URL(url).pathname
    if (path === '/api/events/1/tracks/3/keep') {
      current = current.map((t) => ((t as { id: number }).id === 3 ? KEPT : t))
      summary = { ...summary, removed_upstream: 0 }
    }
    const payloads: Record<string, unknown> = {
      '/api/events': { events: [summary] },
      '/api/events/1': { ...summary, tracks: current },
      '/api/events/1/refresh': refresh,
      '/api/events/1/tracks/3/keep': KEPT,
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(payloads[path] ?? {}),
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return mount(EventsScreen, { global: { plugins: [i18n, pinia, router] } })
}

const chip = (wrapper: ReturnType<typeof mountScreen>, label: string) =>
  wrapper.findAll('.chip').find((c) => c.text().startsWith(label))
const tool = (wrapper: ReturnType<typeof mountScreen>, label: string) =>
  wrapper.findAll('.tool').find((b) => b.text().startsWith(label))

test('6.1 the refresh button posts and reports the three counts', async () => {
  const wrapper = await mountScreen()
  await flushPromises()

  await tool(wrapper, 'Rafraîchir')!.trigger('click')
  await flushPromises()

  expect(vi.mocked(fetch)).toHaveBeenCalledWith(
    'http://127.0.0.1:8766/api/events/1/refresh',
    expect.objectContaining({ method: 'POST' }),
  )
  const banner = wrapper.get('.banner[data-tone="success"]').text()
  expect(banner).toContain('2')
  expect(banner).toContain('5')
  expect(banner).toContain('1')
})

test('6.1 an unchanged playlist says so instead of showing three zeroes', async () => {
  const wrapper = await mountScreen(EVENT, TRACKS, { added: 0, updated: 0, removed: 0 })
  await flushPromises()

  await tool(wrapper, 'Rafraîchir')!.trigger('click')
  await flushPromises()

  expect(wrapper.get('.banner[data-tone="success"]').text()).toContain('n’a pas bougé')
})

test('6.1 a manual event has no playlist to refresh, so no button', async () => {
  const wrapper = await mountScreen({ ...EVENT, spotify_playlist_id: 'manual:1' })
  await flushPromises()

  expect(tool(wrapper, 'Rafraîchir')).toBeUndefined()
})

test('6.2 a departure is counted apart from the pending delta, and reads apart', async () => {
  const wrapper = await mountScreen()
  await flushPromises()

  // the +n badge keeps its own count; the departure gets its own, sign-less
  expect(wrapper.get('.pend-badge').text()).toContain('+1')
  const dep = wrapper.get('.dep-badge')
  expect(dep.text()).toBe('1 partis')
  expect(dep.text()).not.toContain('+')
  expect(dep.attributes('title')).toContain('Rekordbox')

  // and it is nowhere in the counts: 2 titles, not 3
  expect(wrapper.get('.legend').text()).toContain('2')
  expect(wrapper.findAll('.v-rows .row')).toHaveLength(2)
  expect(wrapper.text()).not.toContain('Gone From Spotify')
})

test('6.2 the removed chip appears only when something left, and lists it', async () => {
  const clean = await mountScreen({ ...EVENT, removed_upstream: 0 }, TRACKS.slice(0, 2))
  await flushPromises()
  expect(chip(clean, 'Partis')).toBeUndefined()
  expect(clean.find('.dep-badge').exists()).toBe(false)

  const wrapper = await mountScreen()
  await flushPromises()
  expect(chip(wrapper, 'Partis')!.text()).toContain('1')

  await chip(wrapper, 'Partis')!.trigger('click')
  const rows = wrapper.findAll('.v-rows .row')
  expect(rows).toHaveLength(1)
  expect(rows[0].get('.row-title').text()).toBe('Gone From Spotify')
})

test('6.3 keeping a departed track clears the signal', async () => {
  const wrapper = await mountScreen()
  await flushPromises()
  await chip(wrapper, 'Partis')!.trigger('click')

  const departed = wrapper.get('.v-rows .row')
  // both halves of the decision are offered: keep it, or remove it
  expect(departed.find('.row-keep').exists()).toBe(true)
  expect(departed.findAll('.row-remove:not(.row-keep)')).toHaveLength(1)

  await departed.get('.row-keep').trigger('click')
  await flushPromises()

  expect(vi.mocked(fetch)).toHaveBeenCalledWith(
    'http://127.0.0.1:8766/api/events/1/tracks/3/keep',
    expect.objectContaining({ method: 'POST' }),
  )
  // the signal is gone: chip empty, badge gone, the row back among the rest
  expect(chip(wrapper, 'Partis')!.text()).toContain('0')
  expect(wrapper.find('.dep-badge').exists()).toBe(false)
  await chip(wrapper, 'Tous')!.trigger('click')
  expect(wrapper.findAll('.v-rows .row')).toHaveLength(3)
  expect(wrapper.get('.banner[data-tone="success"]').text()).toContain('Gone From Spotify')
})
