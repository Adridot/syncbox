import { computed, ref } from 'vue'

import { api } from '../api/client'

export type AcquisitionPhase = 'queued' | 'running' | 'downloaded' | 'failed'
export interface AcquisitionState {
  phase: AcquisitionPhase
  error?: string
  /** streamrip scale: 0 = MP3 128 (fallback), 1 = MP3 320 */
  quality?: number
}

/** Translate the component's terse failure reasons for the UI; unknown
    reasons pass through untouched (they carry diagnostic detail). */
export function humanizeAcquisitionError(
  t: (key: string) => string,
  error: string | undefined,
): string | undefined {
  if (!error) return undefined
  if (error.startsWith('streamrip_NonStreamableError')) return t('missing.errors.notStreamable')
  if (error.startsWith('downloaded_file_is_not_full_track')) return t('missing.errors.notFullTrack')
  if (error.startsWith('isrc_not_resolved') || error.startsWith('isrc_lookup_failed'))
    return t('missing.errors.isrcNotFound')
  if (error === 'rekordbox_open') return t('missing.errors.rekordboxOpen')
  return error
}

/** i18n key for a state's badge — flags a lower-quality fallback download.
    Tolerates undefined so v-if-guarded templates typecheck. */
export function acquisitionLabelKey(state: AcquisitionState | undefined): string {
  if (!state) return 'missing.acq_queued'
  if (state.phase === 'downloaded' && state.quality === 0) return 'missing.acq_downgraded'
  return `missing.acq_${state.phase}`
}
export interface AcquisitionItem {
  key: string
  body: Record<string, unknown>
}

export interface AcquisitionJob {
  id: number
  scope: string
  ref: string
  status: string
  error?: string | null
  quality?: number | null
}

const TERMINAL_JOB_STATUSES = new Set([
  'downloaded',
  'relinked',
  'relink_blocked',
  'relink_failed',
  'failed',
])

function stateOf(job: AcquisitionJob): AcquisitionState {
  if (!TERMINAL_JOB_STATUSES.has(job.status)) {
    return { phase: job.status === 'running' ? 'running' : 'queued' }
  }
  if (job.status === 'downloaded' || job.status === 'relinked') {
    return { phase: 'downloaded', quality: job.quality ?? undefined }
  }
  return { phase: 'failed', error: job.error ?? undefined }
}

/** Persist the complete batch first, then observe the sidecar's FIFO worker. */
export function useAcquisitionQueue() {
  const states = ref<Record<string, AcquisitionState>>({})
  const batch = ref<{ done: number; total: number } | null>(null)
  const running = computed(
    () =>
      batch.value !== null ||
      Object.values(states.value).some((state) => state.phase === 'running'),
  )

  /** Drop badges for rows that no longer need one (resolved or gone). */
  function prune(liveKeys: Set<string>) {
    for (const key of Object.keys(states.value)) if (!liveKeys.has(key)) delete states.value[key]
  }

  /** Poll one job to a terminal state; true on success. */
  async function poll(
    key: string,
    queued: AcquisitionJob,
    describe: (cause: unknown) => string,
  ): Promise<boolean> {
    let job = queued
    try {
      while (!TERMINAL_JOB_STATUSES.has(job.status)) {
        states.value[key] = stateOf(job)
        await new Promise((resolve) => window.setTimeout(resolve, 500))
        job = await api.get<AcquisitionJob>(`/api/acquisition/jobs/${job.id}`)
      }
      states.value[key] = stateOf(job)
      return job.status === 'downloaded' || job.status === 'relinked'
    } catch (cause) {
      states.value[key] = { phase: 'failed', error: describe(cause) }
      return false
    }
  }

  async function run(items: AcquisitionItem[], describe: (cause: unknown) => string) {
    let ok = 0
    let failed = 0
    if (items.length > 1) batch.value = { done: 0, total: items.length }
    for (const item of items) states.value[item.key] = { phase: 'queued' }

    // ONE transactional POST: the whole batch is durable in the sidecar
    // before its worker may claim any item, so closing the UI mid-batch can
    // no longer truncate the intended queue.
    let jobs: AcquisitionJob[]
    try {
      const payload = await api.post<{ jobs: AcquisitionJob[] }>(
        '/api/acquisition/jobs/batch',
        { items: items.map((item) => item.body) },
      )
      jobs = payload.jobs
    } catch (cause) {
      for (const item of items) {
        states.value[item.key] = { phase: 'failed', error: describe(cause) }
      }
      batch.value = null
      return { ok: 0, failed: items.length }
    }

    await Promise.all(
      jobs.map(async (job, index) => {
        const success = await poll(items[index].key, job, describe)
        if (success) ok += 1
        else failed += 1
        if (batch.value) batch.value = { done: ok + failed, total: batch.value.total }
      }),
    )
    batch.value = null
    return { ok, failed }
  }

  /** Rebuild badges from the sidecar's persistent queue after the UI was
      closed and reopened, and resume polling every non-terminal job. */
  async function hydrate(
    keyOf: (job: AcquisitionJob) => string | null,
    describe: (cause: unknown) => string,
  ) {
    let payload: { active?: AcquisitionJob[]; recent?: AcquisitionJob[] }
    try {
      payload = await api.get<{ active?: AcquisitionJob[]; recent?: AcquisitionJob[] }>(
        '/api/acquisition/jobs',
      )
    } catch {
      return // sidecar unreachable: nothing to rehydrate
    }
    for (const job of [...(payload.recent ?? [])].reverse()) {
      const key = keyOf(job)
      if (key) states.value[key] = stateOf(job)
    }
    await Promise.all(
      (payload.active ?? []).map((job) => {
        const key = keyOf(job)
        return key ? poll(key, job, describe) : Promise.resolve(false)
      }),
    )
  }

  return { states, batch, running, run, prune, hydrate }
}
