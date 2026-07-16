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

interface AcquisitionJob {
  id: number
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

  async function run(items: AcquisitionItem[], describe: (cause: unknown) => string) {
    let ok = 0
    let failed = 0
    if (items.length > 1) batch.value = { done: 0, total: items.length }
    for (const item of items) states.value[item.key] = { phase: 'queued' }

    const jobs: Array<{ item: AcquisitionItem; job: AcquisitionJob }> = []
    for (const item of items) {
      try {
        const job = await api.post<AcquisitionJob>('/api/acquisition/jobs', {
          ...item.body,
          enqueue: true,
        })
        jobs.push({ item, job })
      } catch (cause) {
        states.value[item.key] = { phase: 'failed', error: describe(cause) }
        failed += 1
        if (batch.value) batch.value = { done: ok + failed, total: batch.value.total }
      }
    }

    await Promise.all(
      jobs.map(async ({ item, job: queued }) => {
        let job = queued
        try {
          while (!TERMINAL_JOB_STATUSES.has(job.status)) {
            states.value[item.key] = {
              phase: job.status === 'running' ? 'running' : 'queued',
            }
            await new Promise((resolve) => window.setTimeout(resolve, 500))
            job = await api.get<AcquisitionJob>(`/api/acquisition/jobs/${job.id}`)
          }
          if (job.status === 'downloaded' || job.status === 'relinked') {
            states.value[item.key] = {
              phase: 'downloaded',
              quality: job.quality ?? undefined,
            }
            ok += 1
          } else {
            states.value[item.key] = {
              phase: 'failed',
              error: job.error ?? undefined,
            }
            failed += 1
          }
        } catch (cause) {
          states.value[item.key] = { phase: 'failed', error: describe(cause) }
          failed += 1
        }
        if (batch.value) batch.value = { done: ok + failed, total: batch.value.total }
      }),
    )
    batch.value = null
    return { ok, failed }
  }

  return { states, batch, running, run, prune }
}
