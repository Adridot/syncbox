import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type { EventDeletePreview, EventSummary } from '../../api/types'
import { i18n } from '../../i18n'
import DeleteEventModal from '../DeleteEventModal.vue'

const EVENT: EventSummary = {
  id: 7,
  name: 'Summer Set',
  slug: 'summer-set',
  default_tag: 'Summer Set',
  spotify_playlist_id: 'manual:summer-set',
  staging_dir: '/Music/_syncbox/events/summer-set',
  status: 'applied',
  applied_at: '2026-07-10T12:00:00Z',
  created_at: '2026-07-09T12:00:00Z',
  n_tracks: 2,
  pending_delta: 0,
}

const PREVIEW = {
  dry_run: true,
  plan_version: 1,
  event_id: 7,
  event_name: 'Summer Set',
  fingerprint: [['master.db', 42, 2048]],
  tag_id: 'tag-7',
  tracks: [
    {
      content_id: 'content-1',
      title: 'Keep Dancing',
      artist: 'Example Artist',
      source_path: '/Music/_syncbox/events/summer-set/keep.flac',
      ownership: 'app_managed',
      retaining_mytags: ['House', 'Favorites'],
      action: 'migrate_to_collection',
      destination_path: '/Music/rekordbox/Collection/keep.flac',
      anlz_update_required: true,
    },
    {
      content_id: 'content-2',
      title: 'Already Safe',
      artist: 'Example Artist',
      source_path: '/Volumes/Archive/already-safe.aiff',
      ownership: 'external',
      retaining_mytags: ['Favorites'],
      action: 'already_permanent',
      destination_path: null,
      anlz_update_required: false,
    },
  ],
  playlists: [{ playlist_id: 'playlist-7', name: 'Summer Set' }],
  xml_artifacts: ['/Music/_syncbox/events/summer-set/masterPlaylists6.xml.bak'],
  staging_artifacts: ['/Music/_syncbox/events/summer-set/keep.flac'],
  expected_file_deletions: ['/Music/_syncbox/events/summer-set/keep.flac'],
  validation: {
    sources: [{ path: '/Music/_syncbox/events/summer-set/keep.flac', size: 2048 }],
  },
} satisfies EventDeletePreview

beforeEach(() => {
  setActivePinia(createPinia())
  i18n.global.locale.value = 'fr'
})
afterEach(() => vi.unstubAllGlobals())

test('event deletion renders the exact migration plan and executes that same payload', async () => {
  const fetchMock = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
    const body = JSON.parse((init?.body as string) || '{}')
    const payload = body.dry_run === false ? { dry_run: false } : PREVIEW
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(payload),
    })
  })
  vi.stubGlobal('fetch', fetchMock)

  const wrapper = mount(DeleteEventModal, {
    props: { event: EVENT },
    global: { plugins: [i18n], stubs: { teleport: true } },
  })
  await flushPromises()

  expect(wrapper.text()).toContain('Migrer vers Collection')
  expect(wrapper.text()).toContain('Conserver sur place')
  expect(wrapper.text()).toContain('Géré par Syncbox')
  expect(wrapper.text()).toContain('Externe')
  expect(wrapper.text()).toContain('House, Favorites')
  expect(wrapper.text()).toContain('/Music/rekordbox/Collection/keep.flac')
  expect(wrapper.text()).toContain('Mise à jour du chemin requise')
  expect(wrapper.text()).toContain('/Music/_syncbox/events/summer-set/keep.flac')

  await wrapper.get('.confirm').trigger('click')
  await flushPromises()

  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).toEqual({
    dry_run: false,
    plan: PREVIEW,
  })
  expect(wrapper.emitted('deleted')).toHaveLength(1)
  wrapper.unmount()
})
