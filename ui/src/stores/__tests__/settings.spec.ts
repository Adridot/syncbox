import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { SETTINGS_RETRY_MS, useSettingsStore } from '../settings'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

test('settings load retries a sidecar cold-start refusal', async () => {
  const fetchMock = vi
    .fn()
    .mockRejectedValueOnce(new TypeError('refused'))
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          spotify_client_id: '',
          rekordbox_db_path: '/rb/master.db',
          storage_root: '/music',
          backup_retention: 15,
          language: 'en',
          match_confidence_threshold: 82,
          match_ambiguity_margin: 6,
          match_weights: { title: 0.52, artist: 0.36, duration: 0.12 },
          isrc_collision_policy: 'guarded',
        }),
      ),
    )
  vi.stubGlobal('fetch', fetchMock)

  const settings = useSettingsStore()
  const pending = settings.load()
  await vi.advanceTimersByTimeAsync(SETTINGS_RETRY_MS)
  await pending

  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(settings.loaded).toBe(true)
  expect(settings.configured).toBe(true)
})
