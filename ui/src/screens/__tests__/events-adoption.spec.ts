/* event-staged-file-adoption §5.7: a file dropped in the event staging
   folder becomes a track. The workspace has to say where the row came from
   (it has no Spotify provenance to show) and, when the drop turned out to
   duplicate the collection, that the file was not needed. */
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
  spotify_track_id: null,
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
  adopted: false,
  duplicates_collection: false,
  duplicate_title: null,
  duplicate_artist: null,
  ...over,
})

const TRACKS = [
  row({ id: 1, title: 'From Spotify', spotify_track_id: '4cOdK2wGLETKBW3PvgPWqT' }),
  row({ id: 2, title: 'Via Con Me.mp3', adopted: true, staging_file_path: '/s/Via Con Me.mp3' }),
  row({
    id: 3,
    title: 'Already Owned.flac',
    status: 'matched',
    adopted: true,
    duplicates_collection: true,
    staging_file_path: '/s/Already Owned.flac',
  }),
  // rejected adoption: kept by the sidecar so the file is not re-adopted
  row({ id: 4, title: 'Refused.wav', status: 'ignored', adopted: true }),
]

const EVENT = {
  id: 1,
  name: 'jo-helo',
  slug: 'jo-helo',
  default_tag: 'Situation:jo-helo',
  spotify_playlist_id: 'manual:1',
  staging_dir: '/s',
  status: 'pending',
  applied_at: null,
  created_at: '2026-08-21',
  n_tracks: TRACKS.length,
  pending_delta: 0,
}

/** The restored row comes back from the POST with its state RE-DERIVED — the
    screen must take the endpoint's word for it, not guess `ready`. */
const RESTORED = row({ id: 4, title: 'Refused.wav', status: 'ready', adopted: true })

function mountScreen(tracks: unknown[] = TRACKS) {
  // stateful like the real backend: the screen reloads the event after a
  // restore, so the reload must see the restored row, not the stale one
  let current = tracks
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      const path = new URL(url).pathname
      if (path === '/api/events/1/tracks/4/restore') {
        current = current.map((t) => ((t as { id: number }).id === 4 ? RESTORED : t))
      }
      const payloads: Record<string, unknown> = {
        '/api/events': { events: [EVENT] },
        '/api/events/1': { ...EVENT, tracks: current },
        '/api/events/1/tracks/4/restore': RESTORED,
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(payloads[path] ?? {}),
      })
    }),
  )
  return mount(EventsScreen, { global: { plugins: [i18n, pinia, router] } })
}

const chip = (wrapper: ReturnType<typeof mountScreen>, label: string) =>
  wrapper.findAll('.chip').find((c) => c.text().startsWith(label))

test('5.1 an adopted row is marked, and only an adopted row', async () => {
  const wrapper = await mountScreen()
  await flushPromises()

  const marked = wrapper.findAll('.row').filter((r) => r.find('.adopted-chip').exists())
  expect(marked.map((r) => r.get('.row-title').text())).toEqual([
    'Via Con Me.mp3',
    'Already Owned.flac',
  ])
  // the Spotify row keeps its app-first attribution, not the marker
  const spotify = wrapper.findAll('.row').find((r) => r.text().includes('From Spotify'))!
  expect(spotify.find('.adopted-chip').exists()).toBe(false)
})

test('5.2 a matched adopted row says the dropped file duplicated the collection', async () => {
  const wrapper = await mountScreen()
  await flushPromises()

  const notes = wrapper.findAll('.row-note')
  expect(notes).toHaveLength(1)
  expect(notes[0].text()).toContain('Déjà dans ta collection')
  const dup = wrapper.findAll('.row').find((r) => r.text().includes('Already Owned.flac'))!
  expect(dup.find('.row-note').exists()).toBe(true)
  // rejecting an adoption is not the same act as removing a Spotify title
  expect(dup.get('.row-remove').attributes('aria-label')).toBe('Ignorer ce fichier déposé')
})

test('5.3 an ignored row is nowhere: not a chip count, not a rendered row', async () => {
  const wrapper = await mountScreen()
  await flushPromises()

  expect(wrapper.text()).not.toContain('Refused.wav')
  expect(wrapper.findAll('.v-rows .row')).toHaveLength(3)
  // 3 titles, not 4 — the segmented bar's total ignores the rejected row
  expect(wrapper.get('.legend').text()).toContain('3')
})

test('7.2 the duplicate notice names the entry when the snapshot gave one', async () => {
  const wrapper = await mountScreen([
    row({ id: 1, title: 'A.mp3', status: 'matched', adopted: true, duplicates_collection: true }),
    row({
      id: 2,
      title: 'B.mp3',
      status: 'matched',
      adopted: true,
      duplicates_collection: true,
      duplicate_title: 'Via Con Me',
      duplicate_artist: 'Paolo Conte',
    }),
    // the collection entry has a title but no artist
    row({
      id: 3,
      title: 'C.mp3',
      status: 'matched',
      adopted: true,
      duplicates_collection: true,
      duplicate_title: 'Untitled Bootleg',
    }),
  ])
  await flushPromises()

  const notes = wrapper.findAll('.row-note').map((n) => n.text())
  // snapshot unavailable (both fields null) is normal — generic wording
  expect(notes[0]).toBe(
    'Déjà dans ta collection — le titre existant sera taggé, le fichier déposé n’était pas nécessaire.',
  )
  expect(notes[1]).toContain('Déjà dans ta collection : Via Con Me — Paolo Conte.')
  // no dangling separator when the artist is missing
  expect(notes[2]).toContain('Déjà dans ta collection : Untitled Bootleg.')
})

test('8.4 the rejected chip stays out of the toolbar until there IS a rejection', async () => {
  const clean = await mountScreen(TRACKS.filter((t) => t.status !== 'ignored'))
  await flushPromises()
  expect(chip(clean, 'Rejetés')).toBeUndefined()

  const wrapper = await mountScreen()
  await flushPromises()
  expect(chip(wrapper, 'Rejetés')!.text()).toContain('1')
})

test('8.4 the chip lists the rejected row, whose only action puts it back', async () => {
  const wrapper = await mountScreen()
  await flushPromises()
  await chip(wrapper, 'Rejetés')!.trigger('click')

  const rows = wrapper.findAll('.v-rows .row')
  expect(rows).toHaveLength(1)
  expect(rows[0].get('.row-title').text()).toBe('Refused.wav')
  // rejecting an already-rejected row is not a thing
  expect(rows[0].find('.row-remove:not(.row-restore)').exists()).toBe(false)

  await rows[0].get('.row-restore').trigger('click')
  await flushPromises()

  expect(vi.mocked(fetch)).toHaveBeenCalledWith(
    'http://127.0.0.1:8766/api/events/1/tracks/4/restore',
    expect.objectContaining({ method: 'POST' }),
  )
  // the row is refreshed FROM the response: it left the rejected chip for
  // the state the sidecar re-derived
  expect(wrapper.findAll('.v-rows .row')).toHaveLength(0)
  expect(chip(wrapper, 'Rejetés')!.text()).toContain('0')
  await chip(wrapper, 'Tous')!.trigger('click')
  expect(wrapper.findAll('.v-rows .row')).toHaveLength(4)
  expect(wrapper.get('.banner[data-tone="success"]').text()).toContain('Refused.wav')
})
