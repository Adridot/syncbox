/* add-event-track-removal (tasks 5.2 / 5.3): the removal modal is the last
   thing between a click and a trashed file, so what it must prove is that the
   four outcomes read differently, that the CTA carries the real counts, and
   that an unresolved case blocks the batch. */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type { EventSummary, EventTrackRemovalPlan } from '../../api/types'
import { i18n } from '../../i18n'
import { useStatusStore } from '../../stores/status'
import RemoveTracksModal from '../RemoveTracksModal.vue'

const EVENT: EventSummary = {
  id: 7,
  name: 'Summer Set',
  slug: 'summer-set',
  default_tag: 'Summer Set',
  spotify_playlist_id: '37i9dQZF1DXcBWIGoYBM5M',
  staging_dir: '/Music/_syncbox/events/summer-set',
  status: 'applied',
  applied_at: '2026-08-10T12:00:00Z',
  created_at: '2026-08-09T12:00:00Z',
  n_tracks: 4,
  pending_delta: 0,
  removed_upstream: 4,
}

const PLAN = {
  plan_version: 1,
  event_id: 7,
  needs_rekordbox: true,
  tracks: [
    {
      track_id: 1,
      content_id: 'content-1',
      title: 'Brought In',
      artist: 'Example Artist',
      action: 'delete_with_event',
      source_path: '/Music/_syncbox/events/summer-set/brought-in.flac',
      file_deleted: true,
    },
    {
      track_id: 2,
      content_id: 'content-2',
      title: 'Already Owned',
      artist: 'Example Artist',
      action: 'already_permanent',
      source_path: '/Music/rekordbox/Collection/already-owned.aiff',
      file_deleted: false,
    },
    {
      track_id: 3,
      content_id: 'content-3',
      title: 'Outside Storage',
      artist: 'Example Artist',
      action: 'keep_in_place',
      source_path: '/Volumes/Archive/outside.wav',
      file_deleted: false,
    },
    {
      track_id: 4,
      content_id: null,
      title: 'Never Applied',
      artist: 'Example Artist',
      action: 'never_applied',
      source_path: '/Music/_syncbox/events/summer-set/never-applied.flac',
      file_deleted: true,
    },
  ],
  expected_file_deletions: [
    '/Music/_syncbox/events/summer-set/brought-in.flac',
    '/Music/_syncbox/events/summer-set/never-applied.flac',
  ],
  validation: { sources: [{ path: '/Music/_syncbox/events/summer-set/brought-in.flac' }] },
  fingerprint: [['master.db', 42, 2048]],
} satisfies EventTrackRemovalPlan

function stubFetch(plan: EventTrackRemovalPlan = PLAN) {
  const fetchMock = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
    const body = JSON.parse((init?.body as string) || '{}')
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve(
          body.dry_run === false
            ? { ...plan, dry_run: false, removed_files: [], removed_tracks: [] }
            : plan,
        ),
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function mountModal(trackIds = [1, 2, 3, 4]) {
  return mount(RemoveTracksModal, {
    props: { event: EVENT, trackIds },
    global: { plugins: [i18n], stubs: { teleport: true } },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  i18n.global.locale.value = 'fr'
})
afterEach(() => vi.unstubAllGlobals())

test('5.2 each outcome reads differently and the CTA carries the exact counts', async () => {
  const fetchMock = stubFetch()
  const wrapper = mountModal()
  await flushPromises()

  const text = wrapper.text()
  // the destructive outcome must not read like the two harmless ones
  expect(text).toContain('Supprimé de Rekordbox · fichier à la corbeille')
  expect(text).toContain('l’entrée Rekordbox est supprimée et le fichier part à la corbeille')
  expect(text).toContain('Jamais appliqué · fichier stagé à la corbeille')
  expect(text).toContain('Rekordbox n’est pas touché.')
  expect(text).toContain('Détagué · conservé')
  expect(text).toContain('son fichier n’est pas touché')
  // already_permanent and keep_in_place share a wording but not a group
  expect(wrapper.findAll('.category')).toHaveLength(4)
  expect(wrapper.findAll('.compact-track')).toHaveLength(4)

  // 4 withdrawn, 1 Rekordbox entry deleted, 2 files trashed
  const summary = wrapper.get('.summary').text()
  expect(summary).toContain('4')
  expect(summary).toContain('1')
  expect(summary).toContain('2')
  const cta = wrapper.get('.confirm').text()
  expect(cta).toContain('Retirer 4 titres')
  expect(cta).toContain('2 fichiers à la corbeille')

  await wrapper.get('.confirm').trigger('click')
  await flushPromises()

  // the execute call echoes the preview plan VERBATIM
  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(fetchMock.mock.calls[1][0]).toBe(
    'http://127.0.0.1:8766/api/events/7/tracks/remove',
  )
  expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).toEqual({
    track_ids: [1, 2, 3, 4],
    dry_run: false,
    plan: PLAN,
  })
  expect(wrapper.emitted('removed')).toEqual([[4]])
  wrapper.unmount()
})

test('5.3 an unresolved retained track blocks the batch and says what clears it', async () => {
  stubFetch({
    ...PLAN,
    unresolved: [
      {
        id: 'retained_by_other_mytag-content-1',
        kind: 'retained_by_other_mytag',
        title: 'Brought In',
        artist: 'Example Artist',
        content_id: 'content-1',
        retaining_mytags: ['House', 'Favorites'],
        resolution_options: ['remove_other_mytag', 'delete_event'],
      },
    ],
  })
  const wrapper = mountModal()
  await flushPromises()

  expect(wrapper.text()).toContain('1 cas non résolu')
  expect(wrapper.text()).toContain('Brought In')
  expect(wrapper.text()).toContain('House, Favorites')
  expect(wrapper.findAll('.options li')).toHaveLength(2)
  expect(wrapper.get('.options').text()).toContain('Retirer cet autre MyTag dans Rekordbox')
  expect(wrapper.get('.options').text()).toContain('supprimer l’événement entier')

  const confirm = wrapper.get('.confirm')
  expect(confirm.attributes('disabled')).toBeDefined()
  expect(confirm.text()).toBe('Résoudre les cas restants')
  wrapper.unmount()
})

test('5.2 the Rekordbox guard follows needs_rekordbox, not the screen', async () => {
  stubFetch()
  const blocked = mountModal()
  useStatusStore().rbOpen = true
  await flushPromises()
  expect(blocked.get('.confirm').attributes('disabled')).toBeDefined()
  expect(blocked.get('.confirm').text()).toContain('Rekordbox')
  blocked.unmount()

  // a batch that writes nothing to Rekordbox stays actionable while it runs
  stubFetch({
    ...PLAN,
    needs_rekordbox: false,
    tracks: [PLAN.tracks[3]],
    expected_file_deletions: [PLAN.expected_file_deletions[1]],
  })
  const open = mountModal([4])
  useStatusStore().rbOpen = true
  await flushPromises()
  expect(open.get('.confirm').attributes('disabled')).toBeUndefined()
  expect(open.get('.confirm').text()).toContain('Retirer 1 titre')
  expect(open.text()).toContain('il peut rester ouvert')
  open.unmount()
})

test('a row whose group refused the removal is not announced as untagged', async () => {
  // same-ISRC case: only one of the two tracks sharing an entry is in the
  // batch, so the sidecar degrades it — action reads keep_in_place, but
  // nothing is untagged. The dialog must not promise an act it will not do.
  stubFetch({
    ...PLAN,
    needs_rekordbox: false,
    tracks: [
      {
        ...PLAN.tracks[2],
        track_id: 9,
        title: 'Shared Single Edit',
        action: 'keep_in_place',
        shared_with_kept_track: true,
      },
    ],
    expected_file_deletions: [],
  } as EventTrackRemovalPlan)
  const wrapper = mountModal([9])
  await flushPromises()

  const text = wrapper.text()
  expect(text).toContain('Retiré de l’événement seulement')
  expect(text).toContain('Rien n’est détagué, rien n’est supprimé')
  // the untag promise belongs to the undegraded rows only
  expect(text).not.toContain('Détagué · conservé')
})
