import { afterEach, expect, test, vi } from 'vitest'

import {
  ApiError,
  NetworkError,
  api,
  onInFlightMutations,
  setConsentBroker,
  setMutationBlockedHook,
} from '../client'

afterEach(() => {
  vi.unstubAllGlobals()
  setConsentBroker(null)
  setMutationBlockedHook(null)
})

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  }
}

test('423 mutation_blocked: typed error + status hook fires', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      jsonResponse(423, {
        error: 'mutation_blocked',
        message_key: 'safety.mutation_blocked',
        message: 'quit Rekordbox',
      }),
    ),
  )
  const blocked = vi.fn()
  setMutationBlockedHook(blocked)
  const error = (await api
    .post('/api/untagged/delete', { content_ids: ['1'] })
    .catch((e) => e)) as ApiError
  expect(error).toBeInstanceOf(ApiError)
  expect(error.status).toBe(423)
  expect(error.code).toBe('mutation_blocked')
  expect(error.body.message_key).toBe('safety.mutation_blocked')
  expect(blocked).toHaveBeenCalledOnce()
})

test('409 stale_snapshot: typed with the rerun action', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      jsonResponse(409, {
        error: 'stale_snapshot',
        action: 'rerun_dry_run',
        message: 'stale',
      }),
    ),
  )
  const error = (await api.post('/api/smartfixes/execute', {}).catch((e) => e)) as ApiError
  expect(error.code).toBe('stale_snapshot')
  expect(error.body.action).toBe('rerun_dry_run')
})

test('428 consent loop: broker asked, ONE re-call carries the consent flag', async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      jsonResponse(428, {
        error: 'consent_required',
        consent: 'anlz',
        message: 'anlz consent needed',
      }),
    )
    .mockResolvedValueOnce(jsonResponse(200, { stored_path: '/x' }))
  vi.stubGlobal('fetch', fetchMock)
  const broker = vi.fn().mockResolvedValue(true)
  setConsentBroker(broker)

  const result = await api.post('/api/missing/collection/1/relink', { path: '/f.mp3' })
  expect(result).toEqual({ stored_path: '/x' })
  expect(broker).toHaveBeenCalledOnce()
  expect(broker.mock.calls[0][0].consent).toBe('anlz')
  const recall = JSON.parse(fetchMock.mock.calls[1][1].body)
  expect(recall).toEqual({ path: '/f.mp3', anlz_consent: true })
})

test('428 refused by the user: the error propagates, no re-call', async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    jsonResponse(428, {
      error: 'consent_required',
      consent: 'permanent_delete',
      message: 'permanent',
      path: '/f.mp3',
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
  setConsentBroker(vi.fn().mockResolvedValue(false))
  const error = (await api.post('/api/duplicates/resolve', {}).catch((e) => e)) as ApiError
  expect(error.code).toBe('consent_required')
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

test('unreachable sidecar throws NetworkError, not ApiError', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('refused')))
  const error = await api.get('/api/status').catch((e) => e)
  expect(error).toBeInstanceOf(NetworkError)
})

test('loopback requests bypass the persistent WebKit HTTP cache', async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }))
  vi.stubGlobal('fetch', fetchMock)
  await api.get('/health')
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'GET', cache: 'no-store' })
})

test('in-flight mutation count feeds jobRunning; GETs are ignored', async () => {
  let resolveFetch!: (v: unknown) => void
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() => new Promise((resolve) => (resolveFetch = resolve))),
  )
  const counts: number[] = []
  const unsubscribe = onInFlightMutations((n) => counts.push(n))

  const pending = api.post('/api/sources/sync')
  expect(counts).toEqual([1])
  resolveFetch(jsonResponse(200, { results: [] }))
  await pending
  expect(counts).toEqual([1, 0])
  unsubscribe()
})
