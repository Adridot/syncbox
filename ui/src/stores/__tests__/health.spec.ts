import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, expect, test } from 'vitest'

import { useHealthStore } from '../health'
import { useJobsStore } from '../jobs'
import { useStatusStore } from '../status'

beforeEach(() => setActivePinia(createPinia()))

test('pill tones derive from the single status/jobs source', () => {
  const health = useHealthStore()
  const status = useStatusStore()
  const jobs = useJobsStore()

  expect(health.pill).toEqual({ spotify: 'idle', rekordbox: 'ok', jobs: 'idle' })

  status.spotifyConnected = true
  status.rbOpen = true // RB open -> amber, mutations paused
  jobs.active['sources.sync'] = { job: 'j', kind: 'sources.sync', done: 1, total: 2, pct: 50 }
  expect(health.pill).toEqual({ spotify: 'ok', rekordbox: 'warn', jobs: 'ok' })
})

test('jobRunning combines SSE-active jobs and in-flight mutations', () => {
  const jobs = useJobsStore()
  expect(jobs.jobRunning).toBe(false)
  jobs.inFlightMutations = 1
  expect(jobs.jobRunning).toBe(true)
  jobs.inFlightMutations = 0
  jobs.active['x'] = { job: 'j', kind: 'x', done: 0, total: 1, pct: 0 }
  expect(jobs.jobRunning).toBe(true)
})

test('counts are null (never scanned -> "—") until a real result lands', () => {
  const health = useHealthStore()
  expect(health.badges.duplicates).toBeNull()
  expect(health.missingTotal).toBeNull()

  health.setDuplicateGroups(4)
  health.setMissingCounts({ library: 2, event: 1, collection: 3 })
  health.setUntaggedCount(7)
  expect(health.badges.duplicates).toBe(4)
  expect(health.missingTotal).toBe(6)
  expect(health.badges.untagged).toBe(7)
})
