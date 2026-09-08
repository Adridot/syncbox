import { createPinia, setActivePinia } from 'pinia'
import { expect, test, vi } from 'vitest'

import { connectJobStream } from '../../api/sse'
import { useJobsStore } from '../jobs'

vi.mock('../../api/sse', () => ({ connectJobStream: vi.fn() }))

test('failed completion releases the busy state and a later job can run', () => {
  setActivePinia(createPinia())
  const jobs = useJobsStore()
  jobs.start()
  const handlers = vi.mocked(connectJobStream).mock.calls[0]![0]
  const progress = { job: 'first', kind: 'events.reapply', done: 0, total: 1, pct: 0 }
  handlers.onProgress?.(progress)
  expect(jobs.jobRunning).toBe(true)
  handlers.onDone?.({ job: 'first', kind: progress.kind, status: 'failed' })
  expect(jobs.jobRunning).toBe(false)
  handlers.onProgress?.({ ...progress, job: 'retry' })
  expect(jobs.jobRunning).toBe(true)
  handlers.onDone?.({ job: 'retry', kind: progress.kind, applied: 5 })
  expect(jobs.jobRunning).toBe(false)
})
