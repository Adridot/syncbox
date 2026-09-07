// PR #31 review regressions: the acquisition queue is PERSISTENT in the
// sidecar — reopening the UI mid-batch must rehydrate badges/errors and
// resume polling, and a batch must be persisted through ONE transactional
// POST before any execution.
import { afterEach, expect, test, vi } from 'vitest'

import { acquisitionDetails, useAcquisitionQueue } from '../acquisition'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
  vi.useRealTimers()
})

function jsonResponse(payload: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(payload),
  })
}

test('reopening the UI rehydrates badges and resumes polling active jobs', async () => {
  vi.useFakeTimers()
  let polls = 0
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      const path = new URL(String(url)).pathname
      if (path === '/api/acquisition/jobs')
        return jsonResponse({
          active: [{ id: 7, scope: 'event', ref: '3', status: 'running' }],
          recent: [
            { id: 6, scope: 'event', ref: '2', status: 'failed', error: 'boom' },
            { id: 5, scope: 'library', ref: '9', status: 'failed', error: 'other scope' },
          ],
        })
      if (path === '/api/acquisition/jobs/7') {
        polls += 1
        return jsonResponse(
          polls < 2
            ? { id: 7, scope: 'event', ref: '3', status: 'running' }
            : { id: 7, scope: 'event', ref: '3', status: 'downloaded', quality: 1 },
        )
      }
      return jsonResponse({})
    }),
  )

  const queue = useAcquisitionQueue()
  const hydration = queue.hydrate(
    (job) => (job.scope === 'event' ? String(job.ref) : null),
    () => 'network error',
  )
  await vi.advanceTimersByTimeAsync(0)

  // Terminal errors and live progress are restored from the sidecar queue.
  expect(queue.states.value['2']).toEqual({ phase: 'failed', error: 'boom' })
  expect(queue.states.value['3']).toEqual({ phase: 'running' })
  expect(queue.states.value['9']).toBeUndefined() // keyOf filtered the scope

  await vi.advanceTimersByTimeAsync(500)
  await vi.advanceTimersByTimeAsync(500)
  await hydration

  expect(queue.states.value['3']).toEqual({ phase: 'downloaded', quality: 1 })
})

test('run() persists the whole batch through one transactional POST', async () => {
  const posts: Array<{ path: string; body: unknown }> = []
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const path = new URL(String(url)).pathname
      if (init?.method === 'POST') {
        posts.push({ path, body: JSON.parse(String(init.body)) })
        return jsonResponse({
          jobs: [
            { id: 1, scope: 'library', ref: '1', status: 'downloaded', quality: 1 },
            { id: 2, scope: 'library', ref: '2', status: 'failed', error: 'no isrc' },
          ],
        })
      }
      return jsonResponse({})
    }),
  )

  const queue = useAcquisitionQueue()
  const result = await queue.run(
    [
      { key: 'library:1', body: { scope: 'library', row_id: 1 } },
      { key: 'library:2', body: { scope: 'library', row_id: 2 } },
    ],
    () => 'network error',
  )

  expect(posts).toEqual([
    {
      path: '/api/acquisition/jobs/batch',
      body: {
        items: [
          { scope: 'library', row_id: 1 },
          { scope: 'library', row_id: 2 },
        ],
      },
    },
  ])
  expect(result).toEqual({ ok: 1, failed: 1 })
  expect(queue.states.value['library:1']).toEqual({ phase: 'downloaded', quality: 1 })
  expect(queue.states.value['library:2']).toEqual({ phase: 'failed', error: 'no isrc' })
})

test('maps reversed mixed-provider results by explicit owner, never array position', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => jsonResponse({ jobs: [
    { id: 8, scope: 'event', ref: '2', event_track_id: 2, provider: 'soundcloud', status: 'failed', error: 'provider_item_unavailable' },
    { id: 7, scope: 'event', ref: '1', event_track_id: 1, provider: 'youtube', status: 'downloaded', processing: 'transcode', source_properties: JSON.stringify({ codec: 'opus', bitrate_kbps: null }), output_properties: JSON.stringify({ codec: 'mp3', sample_rate: 48000 }) },
  ] })))
  const queue = useAcquisitionQueue()
  expect(await queue.run([{ key: 'first', body: { scope: 'event', row_id: 1 } }, { key: 'second', body: { scope: 'event', row_id: 2 } }], String)).toEqual({ ok: 1, failed: 1 })
  expect(queue.states.value.first).toMatchObject({ phase: 'downloaded', processing: 'transcode' })
  expect(queue.states.value.second).toEqual({ phase: 'failed', error: 'provider_item_unavailable' })
})

test('refuses duplicate owner responses instead of counting a job twice', async () => {
  const job = { id: 7, scope: 'event', ref: '1', event_track_id: 1, status: 'downloaded' }
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => jsonResponse({ jobs: [job, job] })))
  const queue = useAcquisitionQueue()
  expect(await queue.run([{ key: 'first', body: { scope: 'event', row_id: 1 } }], String)).toEqual({ ok: 0, failed: 1 })
  expect(queue.states.value.first?.phase).toBe('failed')
})


test('reports unknown source bitrate separately from converted output quality', () => {
  const translate = (key: string, values?: Record<string, string>) => `${key}: ${JSON.stringify(values)}`
  const details = acquisitionDetails(translate, { phase: 'downloaded', processing: 'transcode', sourceProperties: JSON.stringify({ codec: 'opus', bitrate_kbps: null }), outputProperties: JSON.stringify({ codec: 'mp3', sample_rate: 48000, bitrate: 320000 }) })
  expect(details).toContain('"codec":"opus","bitrate":"—"')
  expect(details).toContain('"codec":"mp3","rate":"48000 Hz"')
  expect(details).toContain('linkImport.transcoded')
  expect(details).not.toContain('320')
})
