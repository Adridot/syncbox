<script setup lang="ts">
// Events (M4.8 — SPEC-DESIGN §2, SPEC-UNIFIED §5.7/§11.2): cards with
// lifecycle badges + pending-delta, workspace with a REAL-counts segmented
// bar, add-by-link (Spotify-only §11.1) or manual entry, match/claim, and
// the apply / re-apply / delete modals (all RB-guarded). Every click
// surfaces its backend outcome (B1).
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, NetworkError, api } from '../api/client'
import type { DeezerSearchResult, EventSummary, EventTrack } from '../api/types'
import ApplyEventModal from '../components/ApplyEventModal.vue'
import DeezerSearchPanel from '../components/DeezerSearchPanel.vue'
import DeleteEventModal from '../components/DeleteEventModal.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import LoadingState from '../components/LoadingState.vue'
import NewEventModal from '../components/NewEventModal.vue'
import ReapplyEventModal from '../components/ReapplyEventModal.vue'
import SpotifyAttributionLink from '../components/SpotifyAttributionLink.vue'
import StatusBadge from '../components/StatusBadge.vue'
import {
  EVENT_FILTERS,
  type EventFilter,
  eventCounts,
  filterEventTracks,
  isBaseApplied,
} from '../lib/events'
import {
  acquisitionLabelKey,
  humanizeAcquisitionError,
  useAcquisitionQueue,
} from '../lib/acquisition'
import { useRefreshOnReturn } from '../lib/refresh'
import { extractTrackId } from '../lib/spotify'
import { revealInFolder } from '../shell'
import { useHealthStore } from '../stores/health'
import { useJobsStore } from '../stores/jobs'
import { useStatusStore } from '../stores/status'

const { t } = useI18n()
const status = useStatusStore()
const jobs = useJobsStore()
const health = useHealthStore()

const events = ref<EventSummary[] | null>(null)
const tracksByEvent = reactive<Record<number, EventTrack[]>>({})
const selectedId = ref<number | null>(null)
const filter = ref<EventFilter>('all')
const loading = ref(true)
const loadError = ref<string | null>(null)
const banner = ref<{ tone: 'error' | 'success'; text: string } | null>(null)
const modal = ref<null | 'new' | 'apply' | 'reapply' | 'delete'>(null)

const link = ref('')
const adding = ref(false)
const addError = ref<string | null>(null)

const renaming = ref(false)
const renameValue = ref('')

function describe(cause: unknown): string {
  if (cause instanceof ApiError) return cause.message
  if (cause instanceof NetworkError) return t('common.networkError')
  return String(cause)
}

async function load(keepSelection = true) {
  loadError.value = null
  try {
    const list = (await api.get<{ events: EventSummary[] }>('/api/events')).events
    const details = await Promise.all(
      list.map((event) =>
        api.get<EventSummary & { tracks: EventTrack[] }>(`/api/events/${event.id}`),
      ),
    )
    events.value = list
    list.forEach((event, index) => {
      tracksByEvent[event.id] = details[index].tracks
    })
    if (!keepSelection || !list.some((event) => event.id === selectedId.value))
      selectedId.value = list[0]?.id ?? null
    health.setEventsAttentionCount(
      list.filter((event) => event.pending_delta > 0 || event.status === 'pending').length,
    )
  } catch (cause) {
    loadError.value = describe(cause)
  } finally {
    loading.value = false
  }
}
// skeleton on first load only: keep-alive re-entries refresh silently and
// re-run the silent auto-match (on first mount the selectedId watch does it)
useRefreshOnReturn(async () => {
  void refreshAcqReady()
  const hadSelection = selectedId.value != null
  await load()
  if (hadSelection && selectedId.value != null) void autoMatch(selectedId.value)
})

const selected = computed(
  () => (events.value ?? []).find((event) => event.id === selectedId.value) ?? null,
)
const selectedTracks = computed(() =>
  selected.value ? (tracksByEvent[selected.value.id] ?? []) : [],
)
const baseApplied = computed(() => (selected.value ? isBaseApplied(selected.value.status) : false))
const counts = computed(() => eventCounts(selectedTracks.value, baseApplied.value))
const visibleTracks = computed(() => filterEventTracks(selectedTracks.value, filter.value))
const showApply = computed(() => selected.value && (!baseApplied.value || counts.value.pending > 0))

const cardMeta = computed(() => {
  const byId: Record<number, { ready: number; missing: number; total: number }> = {}
  for (const event of events.value ?? []) {
    const c = eventCounts(tracksByEvent[event.id] ?? [])
    byId[event.id] = { ready: c.ready, missing: c.missing, total: c.total }
  }
  return byId
})

function srcLine(event: EventSummary): string {
  const source = event.spotify_playlist_id.startsWith('manual:')
    ? t('events.manualSource')
    : 'Spotify'
  const applied = event.applied_at
    ? ` · ${t('events.appliedShort', { date: event.applied_at.slice(0, 10) })}`
    : ''
  return source + applied
}

// --- workspace actions (B1 on every one) -----------------------------------

/** Matching is automatic (owner request 07/07 — no button): the sidecar
    matches on add, and this re-matches unresolved rows when the event opens
    or when Rekordbox closes (matching needs it closed) — best-effort, silent,
    updating the tracks in place so it never loops through load(). */
async function autoMatch(eventId: number) {
  const tracks = tracksByEvent[eventId] ?? []
  if (
    !tracks.some((t) =>
      ['missing', 'ambiguous', 'acquisition_failed'].includes(t.status),
    )
  )
    return
  if (status.rbOpen) return // matcher needs Rekordbox closed; retried on close
  try {
    const { tracks: matched } = await api.post<{ tracks: EventTrack[] }>(
      `/api/events/${eventId}/match`,
    )
    tracksByEvent[eventId] = matched
  } catch {
    /* B1 does not apply to a silent background match: statuses stay put */
  }
}
watch(selectedId, (id) => {
  if (id != null) void autoMatch(id)
})
watch(
  () => status.rbOpen,
  (open) => {
    if (!open && selectedId.value != null) void autoMatch(selectedId.value)
  },
)

// --- Deezer acquisition (owner decision 16/07): the whole flow lives HERE —
// batch button + live per-track badge + x/N counter; the Missing center
// keeps the cross-scope view ---------------------------------------------
const {
  states: acqStates,
  batch: acqBatch,
  running: acqRunning,
  run: runAcq,
  prune: pruneAcq,
} = useAcquisitionQueue()

const acqReady = ref(false)
async function refreshAcqReady() {
  try {
    const s = await api.get<{
      enabled: boolean
      has_arl: boolean
      component: { installed?: boolean }
    }>('/api/acquisition/deezer')
    acqReady.value = s.enabled && s.has_arl && Boolean(s.component?.installed)
  } catch {
    acqReady.value = false
  }
}

const MISSING_TRACK_STATUSES = ['missing', 'acquisition_failed']
// auto path needs the row's ISRC; ISRC-less rows go through manual search
const downloadable = computed(() =>
  selectedTracks.value.filter(
    (track) => MISSING_TRACK_STATUSES.includes(track.status) && track.isrc,
  ),
)

function pruneAcqBadges() {
  // downloaded rows now show status 'ready' — keep only the failures' badges
  pruneAcq(
    new Set(
      selectedTracks.value
        .filter((track) => MISSING_TRACK_STATUSES.includes(track.status))
        .map((track) => String(track.id)),
    ),
  )
}

async function downloadMissing() {
  banner.value = null
  const { ok, failed } = await runAcq(
    downloadable.value.map((track) => ({
      key: String(track.id),
      body: { scope: 'event', row_id: track.id },
    })),
    describe,
  )
  await load()
  pruneAcqBadges()
  banner.value = {
    tone: failed ? 'error' : 'success',
    text: t('missing.bulkAcquireDone', { ok, failed }),
  }
}

// manual Deezer search with 30 s preview; a pick downloads the chosen
// recording even when the row has no ISRC
const searchTrack = ref<EventTrack | null>(null)
const searchQuery = computed(() =>
  searchTrack.value
    ? [searchTrack.value.artist, searchTrack.value.title].filter(Boolean).join(' ')
    : '',
)

async function onDeezerPick(result: DeezerSearchResult) {
  const track = searchTrack.value
  searchTrack.value = null
  if (!track) return
  banner.value = null
  const key = String(track.id)
  const { ok } = await runAcq(
    [{ key, body: { scope: 'event', row_id: track.id, deezer_track_id: result.id } }],
    describe,
  )
  const reason = humanizeAcquisitionError(t, acqStates.value[key]?.error)
  await load()
  pruneAcqBadges()
  banner.value = ok
    ? { tone: 'success', text: t('missing.acquired', { title: track.title ?? '' }) }
    : {
        tone: 'error',
        text:
          t('missing.acquisitionFailed', { title: track.title ?? '' }) +
          (reason ? ` (${reason})` : ''),
      }
}

async function runClaim() {
  if (!selected.value) return
  banner.value = null
  try {
    const { claimed } = await api.post<{ claimed: EventTrack[] }>(
      `/api/events/${selected.value.id}/claim`,
    )
    await load()
    banner.value = { tone: 'success', text: t('events.claimDone', claimed.length) }
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
  }
}

async function addTrack() {
  if (!selected.value) return
  addError.value = null
  const id = extractTrackId(link.value)
  if (!id) {
    addError.value = t('events.addTrack.invalidLink')
    return
  }
  adding.value = true
  try {
    // the sidecar resolves the Spotify metadata AND auto-matches on add
    await api.post(`/api/events/${selected.value.id}/tracks`, { spotify_track_id: id })
    link.value = ''
    await load()
  } catch (cause) {
    addError.value = describe(cause)
  } finally {
    adding.value = false
  }
}

async function removeTrack(track: EventTrack) {
  if (!selected.value) return
  banner.value = null
  try {
    await api.delete(`/api/events/${selected.value.id}/tracks/${track.id}`)
    await load()
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
  }
}

function startRename() {
  renameValue.value = selected.value?.name ?? ''
  renaming.value = true
}

async function saveRename() {
  if (!selected.value || !renameValue.value.trim()) return
  banner.value = null
  try {
    await api.patch(`/api/events/${selected.value.id}`, { name: renameValue.value.trim() })
    renaming.value = false
    await load()
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
  }
}

function onCreated(event: EventSummary) {
  modal.value = null
  selectedId.value = event.id
  void load()
}

async function onWriteDone() {
  modal.value = null
  await load()
}
</script>

<template>
  <main class="screen">
    <header class="head">
      <div>
        <h1>{{ t('nav.events') }}</h1>
        <p class="tagline">{{ t('events.tagline') }}</p>
      </div>
      <button class="btn-primary" @click="modal = 'new'">{{ t('events.new.cta') }}</button>
    </header>

    <LoadingState v-if="loading" :rows="4" />

    <ErrorState v-else-if="loadError" :title="t('events.loadErrorTitle')" :body="loadError">
      <button class="btn-secondary" @click="load()">{{ t('common.retry') }}</button>
    </ErrorState>

    <EmptyState
      v-else-if="!events?.length"
      icon="◆"
      :title="t('events.emptyTitle')"
      :body="t('events.emptyBody')"
    >
      <button class="btn-primary" @click="modal = 'new'">{{ t('events.new.cta') }}</button>
    </EmptyState>

    <template v-else>
      <div class="cards">
        <button
          v-for="event in events"
          :key="event.id"
          class="card"
          :data-active="event.id === selectedId"
          @click="selectedId = event.id"
        >
          <div class="card-top">
            <div class="card-names">
              <div class="card-name">{{ event.name }}</div>
              <div class="card-src">{{ srcLine(event) }}</div>
            </div>
            <span v-if="event.pending_delta > 0" class="pend-badge">
              +{{ event.pending_delta }} {{ t('events.pendingShort') }}
            </span>
          </div>
          <div class="card-badge"><StatusBadge :status="event.status" /></div>
          <div class="card-counters">
            <span
              ><span class="mono bright">{{ cardMeta[event.id]?.ready ?? 0 }}</span>
              <span class="muted">
                / {{ cardMeta[event.id]?.total ?? 0 }} {{ t('events.readyUnit') }}</span
              ></span
            >
            <span
              ><span class="mono danger">{{ cardMeta[event.id]?.missing ?? 0 }}</span>
              <span class="muted"> {{ t('events.missingUnit') }}</span></span
            >
          </div>
        </button>
      </div>

      <section v-if="selected" class="workspace">
        <div class="ws-head">
          <div class="ws-title">
            <div class="ws-name-row hover-reveal">
              <template v-if="renaming">
                <input
                  v-model="renameValue"
                  class="rename-input"
                  type="text"
                  @keydown.enter.prevent="saveRename"
                  @keydown.esc="renaming = false"
                />
                <button class="ghost" @click="saveRename">{{ t('events.renameSave') }}</button>
                <button class="ghost" @click="renaming = false">{{ t('common.cancel') }}</button>
              </template>
              <template v-else>
                <div class="ws-name">{{ selected.name }}</div>
                <StatusBadge :status="selected.status" />
                <SpotifyAttributionLink
                  v-if="!selected.spotify_playlist_id.startsWith('manual:')"
                  kind="playlist"
                  :spotify-id="selected.spotify_playlist_id"
                />
                <button
                  v-if="selected.status === 'pending'"
                  class="ghost"
                  :title="t('events.rename')"
                  @click="startRename"
                >
                  ✎
                </button>
              </template>
            </div>
            <i18n-t tag="div" class="ws-meta" keypath="events.meta">
              <template #n>
                <span class="mono">{{ counts.total }}</span>
              </template>
              <template #category>
                <span class="mono">Situation</span>
              </template>
            </i18n-t>
            <div class="ws-applied">
              {{
                selected.applied_at
                  ? t('events.appliedLine', {
                      date: selected.applied_at.slice(0, 16).replace('T', ' '),
                    })
                  : t('events.neverApplied')
              }}
            </div>
          </div>
          <button class="delete-btn" :disabled="status.rbOpen" @click="modal = 'delete'">
            {{ status.rbOpen ? t('rbGuard.blocked') : t('events.delete') }}
          </button>
          <button
            v-if="showApply"
            class="apply-btn"
            :data-reapply="baseApplied"
            :disabled="status.rbOpen || jobs.jobRunning"
            @click="modal = baseApplied ? 'reapply' : 'apply'"
          >
            {{
              status.rbOpen
                ? t('rbGuard.blocked')
                : baseApplied
                  ? t('events.reapplyCta', { n: counts.pendReady })
                  : t('events.applyCta')
            }}
          </button>
          <span v-else class="applied-chip">✓ {{ t('status.applied') }}</span>
        </div>

        <div class="progress">
          <div class="bar">
            <div
              class="seg applied"
              :style="{ width: `${(100 * counts.applied) / Math.max(1, counts.total)}%` }"
            />
            <div
              class="seg ready"
              :style="{ width: `${(100 * counts.ready) / Math.max(1, counts.total)}%` }"
            />
            <div
              class="seg missing"
              :style="{ width: `${(100 * counts.missing) / Math.max(1, counts.total)}%` }"
            />
          </div>
          <div class="legend">
            <span v-if="counts.applied" class="leg"
              ><span class="sw applied" /><span class="mono ok">{{ counts.applied }}</span>
              {{ t('events.appliedUnit') }}</span
            >
            <span class="leg"
              ><span class="sw ready" /><span class="mono bright">{{ counts.ready }}</span>
              {{ t('events.readyUnit') }}</span
            >
            <span class="leg"
              ><span class="sw missing" /><span class="mono danger">{{ counts.missing }}</span>
              {{ t('events.missingUnit') }}</span
            >
            <span v-if="counts.pending" class="leg"
              ><span class="sw pending" /><span class="mono warn">{{ counts.pending }}</span>
              {{ t('events.pendingUnit') }}</span
            >
            <span class="spacer" />
            <span class="muted"
              ><span class="mono">{{ counts.total }}</span> {{ t('events.titlesUnit') }}</span
            >
          </div>
        </div>

        <div v-if="counts.pending" class="modified-banner">
          <span class="warn-glyph">⚠</span>
          <i18n-t tag="div" class="modified-text" keypath="events.modifiedBanner">
            <template #n>
              <b>{{ t('events.changesPending', counts.pending) }}</b>
            </template>
          </i18n-t>
        </div>

        <!-- B1 surface -->
        <div v-if="banner" class="banner" :data-tone="banner.tone" role="status">
          <span class="banner-text">{{ banner.text }}</span>
          <button class="banner-close" @click="banner = null">✕</button>
        </div>

        <div class="add-row">
          <div class="link-box">
            <span class="glyph">🔗</span>
            <input
              v-model="link"
              type="text"
              class="mono"
              :placeholder="t('events.addTrack.placeholder')"
              @keydown.enter.prevent="addTrack"
            />
          </div>
          <button class="btn-primary add-btn" :disabled="adding" @click="addTrack">
            {{ adding ? t('events.addTrack.resolving') : t('events.addTrack.add') }}
          </button>
        </div>
        <div v-if="addError" class="banner" data-tone="error">
          <span class="banner-text">{{ addError }}</span>
          <button class="banner-close" @click="addError = null">✕</button>
        </div>

        <div class="toolbar">
          <button
            v-for="chip in EVENT_FILTERS"
            :key="chip"
            class="chip"
            :data-active="filter === chip"
            @click="filter = chip"
          >
            {{ t(`events.filters.${chip}`) }}
            <span class="chip-n mono">{{
              chip === 'all'
                ? counts.total
                : chip === 'ready'
                  ? counts.ready
                  : chip === 'missing'
                    ? counts.missing
                    : chip === 'ambiguous'
                      ? counts.ambiguous
                      : counts.pending
            }}</span>
          </button>
          <span class="spacer" />
          <button
            v-if="acqReady && downloadable.length"
            class="btn-secondary tool"
            :disabled="jobs.jobRunning || acqRunning"
            @click="downloadMissing"
          >
            {{ t('events.downloadMissing', { n: downloadable.length }) }}
          </button>
          <button
            v-if="selected?.staging_dir"
            class="btn-secondary tool"
            :title="t('events.openStagingHelp')"
            @click="revealInFolder(selected!.staging_dir!)"
          >
            {{ t('events.openStaging') }}
          </button>
          <button class="btn-secondary tool" :disabled="jobs.jobRunning" @click="runClaim">
            {{ t('events.claim') }}
          </button>
        </div>

        <div v-if="acqBatch" class="acq-progress" role="status">
          <span class="acq-spinner" aria-hidden="true" />
          {{ t('missing.acqProgress', { done: acqBatch.done, total: acqBatch.total }) }}
        </div>

        <div class="table">
          <div class="table-head">
            <span class="cell-title">{{ t('events.columns.title') }}</span>
            <span class="cell-status">{{ t('events.columns.status') }}</span>
            <span class="cell-conf">{{ t('events.columns.conf') }}</span>
            <span class="cell-actions">{{ t('events.columns.action') }}</span>
          </div>
          <div
            v-for="track in visibleTracks"
            :key="track.id"
            class="row hover-reveal"
            :data-pending="track.added_after_apply === 1"
          >
            <div class="cell-title">
              <div class="row-title-line">
                <span class="row-title">{{ track.title }}</span>
                <SpotifyAttributionLink
                  v-if="track.spotify_track_id"
                  kind="track"
                  :spotify-id="track.spotify_track_id"
                />
                <span v-if="track.added_after_apply === 1" class="added-chip">{{
                  t('events.addedChip')
                }}</span>
              </div>
              <div class="row-artist">{{ track.artist }}</div>
              <div v-if="acqStates[String(track.id)]?.error" class="row-error">
                {{ humanizeAcquisitionError(t, acqStates[String(track.id)]?.error) }}
              </div>
            </div>
            <span class="cell-status">
              <span
                v-if="acqStates[String(track.id)]"
                class="acq-badge"
                :data-phase="acqStates[String(track.id)]?.phase"
              >
                {{ t(acquisitionLabelKey(acqStates[String(track.id)])) }}
              </span>
              <StatusBadge v-else :status="track.status" />
            </span>
            <span class="cell-conf mono" :data-good="(track.confidence ?? 0) >= 95">{{
              track.confidence ?? '—'
            }}</span>
            <span class="cell-actions">
              <!-- compact icon: the text button overflowed into the conf
                   column (owner feedback 16/07) -->
              <button
                v-if="acqReady && MISSING_TRACK_STATUSES.includes(track.status)"
                class="row-search"
                :disabled="jobs.jobRunning || acqRunning"
                :data-tip="t('missing.searchDeezer')"
                :aria-label="t('missing.searchDeezer')"
                @click="searchTrack = track"
              >
                <svg
                  width="13"
                  height="13"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.4"
                  stroke-linecap="round"
                >
                  <circle cx="11" cy="11" r="7" />
                  <line x1="21" y1="21" x2="16.2" y2="16.2" />
                </svg>
              </button>
              <router-link
                v-if="['missing', 'acquisition_failed'].includes(track.status)"
                class="action-link"
                to="/missing/event"
                >{{ t('events.resolveMissing') }}</router-link
              >
              <button
                v-if="track.status !== 'applied'"
                class="row-remove"
                :data-tip="t('events.removeTrack')"
                :aria-label="t('events.removeTrack')"
                @click="removeTrack(track)"
              >
                ✕
              </button>
            </span>
          </div>
          <div v-if="!visibleTracks.length" class="table-empty">
            {{ t('events.filterEmpty') }}
          </div>
        </div>
      </section>
    </template>

    <NewEventModal v-if="modal === 'new'" @close="modal = null" @created="onCreated" />
    <ApplyEventModal
      v-if="modal === 'apply' && selected"
      :event="selected"
      :counts="counts"
      @close="modal = null"
      @applied="onWriteDone"
    />
    <ReapplyEventModal
      v-if="modal === 'reapply' && selected"
      :event="selected"
      :counts="counts"
      @close="modal = null"
      @applied="onWriteDone"
    />
    <DeleteEventModal
      v-if="modal === 'delete' && selected"
      :event="selected"
      @close="modal = null"
      @deleted="onWriteDone"
    />
    <DeezerSearchPanel
      v-if="searchTrack"
      :initial-query="searchQuery"
      :context-label="searchTrack.title ?? ''"
      @close="searchTrack = null"
      @pick="onDeezerPick"
    />
  </main>
</template>

<style scoped>
.screen {
  padding: var(--screen-padding);
  max-width: var(--content-max-width);
  margin: 0 auto;
}
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 22px;
}
h1 {
  font: var(--text-h1);
  letter-spacing: -0.02em;
  margin: 0;
}
.tagline {
  color: var(--text-muted-bright);
  font-size: 14px;
  margin: 4px 0 0;
}
.cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 26px;
}
.card {
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 13px;
  padding: 14px;
  cursor: pointer;
  text-align: left;
  color: inherit;
}
.card:hover {
  border-color: #2a3242;
}
.card[data-active='true'] {
  border-color: var(--accent-border);
  background: rgba(77, 163, 255, 0.06);
}
.card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.card-names {
  min-width: 0;
}
.card-name {
  font-weight: 600;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.card-src {
  font-size: var(--size-meta);
  color: var(--text-muted);
  margin-top: 2px;
}
.pend-badge {
  flex: none;
  font-size: 10.5px;
  font-weight: 700;
  color: var(--warning-text);
  background: var(--warning-tint);
  border: 1px solid rgba(245, 181, 68, 0.28);
  border-radius: 6px;
  padding: 2px 7px;
  white-space: nowrap;
}
.card-badge {
  margin-top: 11px;
}
.card-counters {
  display: flex;
  gap: 14px;
  margin-top: 12px;
  font-size: 12px;
}
.mono {
  font-family: var(--font-mono);
}
.bright {
  color: var(--text-secondary-bright);
}
.muted {
  color: var(--text-muted);
}
.danger {
  color: var(--danger-text);
}
.warn {
  color: var(--warning-text);
}
.ok {
  color: var(--success);
}
.workspace {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  overflow: clip;
}
.ws-head {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-subtle-2);
}
.ws-title {
  flex: 1;
  min-width: 0;
}
.ws-name-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.ws-name {
  font-weight: 600;
  font-size: 15px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.rename-input {
  background: var(--surface-raised);
  border: 1px solid var(--accent-border);
  border-radius: 8px;
  padding: 6px 10px;
  color: var(--text-primary);
  font: inherit;
  font-size: 14px;
  outline: none;
}
.ws-meta {
  font-size: 12px;
  color: var(--text-muted-bright);
  margin-top: 3px;
}
.ws-applied {
  font-size: 11.5px;
  color: var(--text-muted);
  margin-top: 5px;
}
.ghost {
  background: transparent;
  border: none;
  color: var(--text-muted-bright);
  font-size: 12.5px;
  cursor: pointer;
  padding: 0;
  white-space: nowrap;
}
.ghost:hover {
  color: var(--accent-hover);
}
.delete-btn {
  background: transparent;
  border: 1px solid #2a3140;
  color: var(--danger-text);
  padding: 8px 13px;
  border-radius: 9px;
  font-size: 12.5px;
  cursor: pointer;
  flex: none;
  white-space: nowrap;
}
.delete-btn:disabled {
  background: #1a1e26;
  color: var(--text-muted);
  cursor: not-allowed;
}
.apply-btn {
  background: var(--success);
  border: none;
  color: #06131f;
  padding: 9px 16px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  flex: none;
}
.apply-btn[data-reapply='true'] {
  background: var(--warning);
  color: #1f1503;
}
.apply-btn:disabled {
  background: #1a1e26;
  border: 1px solid #2a3140;
  color: var(--text-muted);
  cursor: not-allowed;
}
.applied-chip {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(52, 211, 153, 0.1);
  border: 1px solid rgba(52, 211, 153, 0.28);
  color: #5fe0b0;
  padding: 8px 14px;
  border-radius: 9px;
  font-size: 12.5px;
  font-weight: 600;
}
.progress {
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-subtle-2);
}
.bar {
  display: flex;
  height: 7px;
  border-radius: 999px;
  overflow: clip;
  background: #11151d;
}
.seg {
  height: 100%;
}
.seg.applied {
  background: var(--success);
}
.seg.ready {
  background: var(--teal);
}
.seg.missing {
  background: var(--danger);
}
.seg.pending {
  background: var(--warning);
}
.legend {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-top: 11px;
  font-size: 12px;
  color: var(--text-muted);
}
.leg {
  display: flex;
  align-items: center;
  gap: 6px;
}
.sw {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.sw.applied {
  background: var(--success);
}
.sw.ready {
  background: var(--teal);
}
.sw.missing {
  background: var(--danger);
}
.sw.pending {
  background: var(--warning);
}
.spacer {
  flex: 1;
}
.modified-banner {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 12px 18px;
  border-bottom: 1px solid var(--border-subtle-2);
  background: rgba(245, 181, 68, 0.07);
}
.warn-glyph {
  font-size: 14px;
  color: var(--warning);
}
.modified-text {
  flex: 1;
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.45;
}
.modified-text b {
  color: var(--warning-text);
}
.banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 18px;
  font-size: 12.5px;
  border-bottom: 1px solid var(--border-subtle-2);
}
.banner[data-tone='error'] {
  background: var(--danger-tint);
  color: var(--danger-text);
}
.banner[data-tone='success'] {
  background: var(--success-tint);
  color: var(--success);
}
.banner-text {
  flex: 1;
  min-width: 0;
}
.banner-close {
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
  padding: 0 2px;
}
.add-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 18px;
  border-bottom: 1px solid var(--border-subtle-2);
  background: #0a0d14;
}
.link-box {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface-raised);
  border: 1px solid #2a3140;
  border-radius: 8px;
  padding: 8px 12px;
  min-width: 0;
}
.link-box .glyph {
  color: var(--text-muted);
  font-size: 13px;
}
.link-box input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-secondary-bright);
  font-size: 12.5px;
}
.link-box input.mono {
  font-family: var(--font-mono);
}
.add-btn {
  padding: 8px 15px;
  font-size: 12.5px;
  flex: none;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 11px 18px;
  border-bottom: 1px solid var(--border-subtle-2);
  flex-wrap: wrap;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 11px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  color: #8b97a9;
  background: transparent;
  border: 1px solid var(--border-2);
}
.chip[data-active='true'] {
  color: var(--text-primary);
  background: rgba(77, 163, 255, 0.12);
  border-color: rgba(77, 163, 255, 0.28);
}
.chip-n {
  font-size: var(--size-meta);
  color: var(--text-muted);
}
.chip[data-active='true'] .chip-n {
  color: var(--accent-hover);
}
.tool {
  padding: 6px 12px;
  font-size: 12px;
}
.table-head {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 9px 18px;
  border-bottom: 1px solid var(--border-subtle-2);
  font-size: var(--size-meta);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  font-weight: 600;
}
.row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 11px 18px;
  border-bottom: 1px solid var(--border-subtle);
  border-left: 2px solid transparent;
}
.row[data-pending='true'] {
  border-left-color: var(--warning);
  background: rgba(245, 181, 68, 0.045);
}
.cell-title {
  flex: 1;
  min-width: 0;
}
.row-title-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.row-title {
  font-size: 13.5px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.added-chip {
  flex: none;
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--warning-text);
  background: var(--warning-tint);
  border-radius: 4px;
  padding: 1px 5px;
}
.row-artist {
  font-size: 12px;
  color: var(--text-muted-bright);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cell-status {
  width: 140px;
  flex: none;
}
.cell-conf {
  width: 70px;
  text-align: right;
  flex: none;
  font-size: 13px;
  color: var(--text-muted);
}
.cell-conf[data-good='true'] {
  color: var(--success);
}
.cell-actions {
  width: 170px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 7px;
  flex: none;
}
.action-link {
  border: 1px solid #2a3140;
  color: var(--accent-hover);
  padding: 4px 11px;
  border-radius: 7px;
  font-size: 12px;
  text-decoration: none;
  white-space: nowrap;
}
.row-search {
  background: transparent;
  border: 1px solid #2a3140;
  color: var(--accent-hover);
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
  padding: 0;
  cursor: pointer;
  flex: none;
}
.row-search:hover {
  border-color: var(--accent-border);
  background: var(--accent-tint);
}
.row-search:disabled {
  opacity: 0.55;
  cursor: default;
}
.row-error {
  font-size: 11.5px;
  color: var(--danger-text);
  margin-top: 2px;
}
.acq-badge {
  font-size: var(--size-meta);
  border-radius: 6px;
  padding: 2px 7px;
  white-space: nowrap;
  border: 1px solid var(--border-2);
  color: var(--text-secondary);
}
.acq-badge[data-phase='running'] {
  color: var(--accent-hover);
  border-color: var(--accent-border);
  background: var(--accent-tint);
}
.acq-badge[data-phase='downloaded'] {
  color: var(--success);
  border-color: var(--success-border);
  background: var(--success-tint);
}
.acq-badge[data-phase='failed'] {
  color: var(--danger-text);
  border-color: var(--danger-border);
  background: var(--danger-tint);
}
.acq-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}
.acq-spinner {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid var(--accent-border);
  border-top-color: var(--accent);
  animation: acq-spin 0.8s linear infinite;
}
@keyframes acq-spin {
  to {
    transform: rotate(360deg);
  }
}
.row-remove {
  background: transparent;
  border: 1px solid #2a3140;
  color: var(--text-muted);
  width: 28px;
  border-radius: 7px;
  font-size: 13px;
  cursor: pointer;
}
.row-remove:hover {
  color: var(--danger-text);
  border-color: rgba(247, 110, 110, 0.4);
}
.table-empty {
  padding: 34px;
  text-align: center;
  font-size: 12.5px;
  color: var(--text-muted);
}
</style>
