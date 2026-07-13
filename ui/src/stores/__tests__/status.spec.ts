import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { DOWN_AFTER_FAILURES, useStatusStore } from '../status'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.useFakeTimers() // hold the fast-retry timers so refresh() calls are ours
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

test('startup grace: backend-down only after sustained failures, and one success resets', async () => {
  // sidecar not listening yet (app boot): fetch rejects → NetworkError
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('refused')))
  const status = useStatusStore()

  await status.refresh()
  expect(status.backendDown).toBe(false) // never on the FIRST failure

  for (let i = 1; i < DOWN_AFTER_FAILURES; i += 1) await status.refresh()
  expect(status.backendDown).toBe(true) // sustained → overlay
  expect(status.backendDownReason).toBe('unreachable')

  // the sidecar comes up: one success clears everything
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ rb_open: false, spotify_connected: true })),
    ),
  )
  await status.refresh()
  expect(status.backendDown).toBe(false)
  expect(status.backendDownReason).toBeNull()
  expect(status.failures).toBe(0)
  expect(status.spotifyConnected).toBe(true)
})

test('shell lifecycle reason is preserved for the backend-down overlay', () => {
  const status = useStatusStore()
  status.setBackendDown(true, 'port_collision')
  expect(status.backendDown).toBe(true)
  expect(status.backendDownReason).toBe('port_collision')
  status.setBackendDown(false)
  expect(status.backendDownReason).toBeNull()
})
