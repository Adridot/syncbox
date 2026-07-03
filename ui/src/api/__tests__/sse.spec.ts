import { expect, test, vi } from 'vitest'

import { connectJobStream } from '../sse'

class FakeEventSource {
  listeners: Record<string, Array<(event: unknown) => void>> = {}
  onopen: ((ev: unknown) => void) | null = null
  onerror: ((ev: unknown) => void) | null = null
  closed = false

  constructor(public url: string) {}

  addEventListener(type: string, listener: (event: unknown) => void) {
    ;(this.listeners[type] ??= []).push(listener)
  }

  emit(type: string, data: string) {
    this.listeners[type]?.forEach((listener) => listener({ data }))
  }

  close() {
    this.closed = true
  }
}

function connect(handlers: Parameters<typeof connectJobStream>[0]) {
  let source!: FakeEventSource
  const disconnect = connectJobStream(handlers, (url) => {
    source = new FakeEventSource(url)
    return source
  })
  return { source, disconnect }
}

test('decodes job.progress and job.done payloads', () => {
  const onProgress = vi.fn()
  const onDone = vi.fn()
  const { source } = connect({ onProgress, onDone })

  expect(source.url).toBe('http://127.0.0.1:8765/events')
  source.emit(
    'job.progress',
    JSON.stringify({ job: 'j1', kind: 'duplicates.scan', done: 3, total: 10, pct: 30 }),
  )
  expect(onProgress).toHaveBeenCalledWith({
    job: 'j1',
    kind: 'duplicates.scan',
    done: 3,
    total: 10,
    pct: 30,
  })
  source.emit('job.done', JSON.stringify({ job: 'j1', kind: 'duplicates.scan', groups: 4 }))
  expect(onDone).toHaveBeenCalledWith({ job: 'j1', kind: 'duplicates.scan', groups: 4 })
})

test('malformed frames never kill the stream', () => {
  const onProgress = vi.fn()
  const { source } = connect({ onProgress })
  source.emit('job.progress', 'not json {{')
  source.emit('job.progress', JSON.stringify({ job: 'j', kind: 'k', done: 1, total: 2, pct: 50 }))
  expect(onProgress).toHaveBeenCalledOnce()
})

test('reconnect lifecycle reaches the handlers; disconnect closes', () => {
  const onOpen = vi.fn()
  const onError = vi.fn()
  const { source, disconnect } = connect({ onOpen, onError })
  source.onopen?.({})
  source.onerror?.({}) // mid-stream death: EventSource retries natively
  source.onopen?.({}) // reconnected
  expect(onOpen).toHaveBeenCalledTimes(2)
  expect(onError).toHaveBeenCalledTimes(1)
  disconnect()
  expect(source.closed).toBe(true)
})

test('jobs store clears stale active jobs on SSE (re)connect — no replay', async () => {
  const { createPinia, setActivePinia } = await import('pinia')
  setActivePinia(createPinia())
  const { useJobsStore } = await import('../../stores/jobs')
  const jobs = useJobsStore()

  let source!: FakeEventSource
  jobs.start((url) => {
    source = new FakeEventSource(url)
    return source
  })

  source.emit('job.progress', JSON.stringify({ job: 'j', kind: 'duplicates.scan', done: 3, total: 9, pct: 33 }))
  expect(jobs.jobRunning).toBe(true)

  // (re)connect: the HTTP response is the authority, not stale SSE state
  source.onopen?.({})
  expect(Object.keys(jobs.active)).toHaveLength(0)
  expect(jobs.jobRunning).toBe(false)

  // an error also clears (belt-and-suspenders)
  source.emit('job.progress', JSON.stringify({ job: 'k', kind: 'sources.sync', done: 1, total: 4, pct: 25 }))
  source.onerror?.({})
  expect(Object.keys(jobs.active)).toHaveLength(0)
})
