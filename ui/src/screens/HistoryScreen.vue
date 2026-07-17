<script setup lang="ts">
// Prestations (owner-approved 17/07/2026): the Rekordbox play history
// re-clustered into gigs (crash cuts re-joined, parallel machines kept
// apart, USB imports flagged) + the crash-proof live tracklist. Everything
// here is read-only over master.db — usable WHILE Rekordbox plays.
import { computed, onActivated, onDeactivated, onUnmounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, NetworkError, api } from '../api/client'
import type {
  PerformanceLive,
  PerformanceSummary,
  PerformanceTrack,
} from '../api/types'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import LoadingState from '../components/LoadingState.vue'
import SpotifyAttributionLink from '../components/SpotifyAttributionLink.vue'
import { useRefreshOnReturn } from '../lib/refresh'
import { useStatusStore } from '../stores/status'

const { t, locale } = useI18n()
const status = useStatusStore()

const performances = ref<PerformanceSummary[] | null>(null)
const tracksById = reactive<Record<number, PerformanceTrack[]>>({})
const selectedId = ref<number | null>(null)
const live = ref<PerformanceLive | null>(null)
const loading = ref(true)
const loadError = ref<string | null>(null)
const banner = ref<{ tone: 'error' | 'success'; text: string } | null>(null)
const filter = ref<'main' | 'all' | 'hidden'>('main')
const renaming = ref(false)
const renameValue = ref('')
const exporting = ref(false)

const MAIN_MIN_TRACKS = 5
const LIVE_POLL_MS = 30_000

function describe(cause: unknown): string {
  if (cause instanceof ApiError) return cause.message
  if (cause instanceof NetworkError) return t('common.networkError')
  return String(cause)
}

async function load() {
  loadError.value = null
  try {
    // hidden=1 -> full list; the chips filter client-side
    const [list, liveNow] = await Promise.all([
      api.get<{ performances: PerformanceSummary[] }>('/api/performances?hidden=1'),
      api.get<PerformanceLive>('/api/performances/live'),
    ])
    performances.value = list.performances
    live.value = liveNow
    if (liveNow.active && liveNow.performance) {
      tracksById[liveNow.performance.id] = liveNow.tracks
    }
    if (!list.performances.some((p) => p.id === selectedId.value)) {
      selectedId.value = visible.value[0]?.id ?? null
    }
    if (selectedId.value != null) void loadTracks(selectedId.value)
  } catch (cause) {
    loadError.value = describe(cause)
  } finally {
    loading.value = false
  }
}
useRefreshOnReturn(load)

async function loadTracks(id: number) {
  if (tracksById[id]) return
  try {
    const detail = await api.get<PerformanceSummary & { tracks: PerformanceTrack[] }>(
      `/api/performances/${id}`,
    )
    tracksById[id] = detail.tracks
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
  }
}

// live poll only while the screen is displayed; the sidecar re-ingests on
// every call, so a Rekordbox crash mid-set never loses the tracklist
let timer: ReturnType<typeof setInterval> | null = null
async function pollLive() {
  try {
    const liveNow = await api.get<PerformanceLive>('/api/performances/live')
    live.value = liveNow
    if (liveNow.active && liveNow.performance) {
      tracksById[liveNow.performance.id] = liveNow.tracks
      const known = performances.value?.some((p) => p.id === liveNow.performance!.id)
      if (!known) await load()
    }
  } catch {
    /* transient poll failure: the next tick retries */
  }
}
function startPolling() {
  if (timer == null) timer = setInterval(() => void pollLive(), LIVE_POLL_MS)
}
function stopPolling() {
  if (timer != null) clearInterval(timer)
  timer = null
}
startPolling()
onActivated(startPolling)
onDeactivated(stopPolling)
onUnmounted(stopPolling)

const visible = computed(() => {
  const list = performances.value ?? []
  if (filter.value === 'hidden') return list.filter((p) => p.hidden === 1)
  const shown = list.filter((p) => p.hidden === 0)
  if (filter.value === 'all') return shown
  return shown.filter((p) => p.track_count >= MAIN_MIN_TRACKS)
})
const counts = computed(() => {
  const list = performances.value ?? []
  return {
    main: list.filter((p) => p.hidden === 0 && p.track_count >= MAIN_MIN_TRACKS).length,
    all: list.filter((p) => p.hidden === 0).length,
    hidden: list.filter((p) => p.hidden === 1).length,
  }
})
const selected = computed(
  () => (performances.value ?? []).find((p) => p.id === selectedId.value) ?? null,
)
const selectedTracks = computed(() =>
  selected.value ? (tracksById[selected.value.id] ?? []) : [],
)
const liveIsSelected = computed(
  () => live.value?.active && live.value.performance?.id === selectedId.value,
)

// tracklist rows with the crash markers woven in at their resume points
const displayRows = computed(() => {
  const cutsByResume = new Map(
    (selected.value?.cuts ?? []).map((cut) => [cut.resumed, cut]),
  )
  return selectedTracks.value.map((track) => ({
    track,
    cut: cutsByResume.get(track.played_at) ?? null,
  }))
})

const toDate = (ts: string) => new Date(ts.replace(' ', 'T') + 'Z')
const fmtDate = (ts: string) =>
  toDate(ts).toLocaleDateString(locale.value, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
const fmtTime = (ts: string) =>
  toDate(ts).toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' })
function fmtDuration(p: PerformanceSummary): string {
  const minutes = Math.round((toDate(p.ended_at).getTime() - toDate(p.started_at).getTime()) / 60000)
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')}`
}
const displayName = (p: PerformanceSummary) =>
  p.name ?? t('history.unnamed', { date: fmtDate(p.started_at) })

function selectPerformance(id: number) {
  selectedId.value = id
  renaming.value = false
  void loadTracks(id)
}

function startRename() {
  renameValue.value = selected.value?.name ?? ''
  renaming.value = true
}

async function saveRename() {
  if (!selected.value) return
  banner.value = null
  try {
    const updated = await api.patch<PerformanceSummary>(
      `/api/performances/${selected.value.id}`,
      { name: renameValue.value.trim() || null },
    )
    Object.assign(selected.value, { name: updated.name })
    renaming.value = false
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
  }
}

async function exportPlaylist() {
  if (!selected.value) return
  banner.value = null
  exporting.value = true
  try {
    const result = await api.post<{
      playlist: string
      folder: string
      tracks: number
      spotify_revived: number
      spotify_recovered: number
      skipped_missing: number
    }>(`/api/performances/${selected.value.id}/export-playlist`)
    const revived = result.spotify_revived
      ? ' ' + t('history.exportSpotify', result.spotify_revived)
      : ''
    const recovered = result.spotify_recovered
      ? ' ' + t('history.exportRecovered', result.spotify_recovered)
      : ''
    const skipped = result.skipped_missing
      ? ' ' + t('history.exportSkipped', result.skipped_missing)
      : ''
    banner.value = {
      tone: 'success',
      text:
        t('history.exportDone', {
          name: result.playlist,
          folder: result.folder,
          n: result.tracks,
        }) +
        revived +
        recovered +
        skipped,
    }
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
  } finally {
    exporting.value = false
  }
}

async function toggleHidden() {
  if (!selected.value) return
  banner.value = null
  try {
    const updated = await api.patch<PerformanceSummary>(
      `/api/performances/${selected.value.id}`,
      { hidden: selected.value.hidden === 0 },
    )
    Object.assign(selected.value, { hidden: updated.hidden })
    if (!visible.value.some((p) => p.id === selectedId.value))
      selectedId.value = visible.value[0]?.id ?? null
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
  }
}
</script>

<template>
  <main class="screen">
    <header class="head">
      <div>
        <h1>{{ t('nav.history') }}</h1>
        <p class="tagline">{{ t('history.tagline') }}</p>
      </div>
    </header>

    <LoadingState v-if="loading" :rows="4" />

    <ErrorState v-else-if="loadError" :title="t('history.loadErrorTitle')" :body="loadError">
      <button class="btn-secondary" @click="load()">{{ t('common.retry') }}</button>
    </ErrorState>

    <EmptyState
      v-else-if="!performances?.length"
      icon="◷"
      :title="t('history.emptyTitle')"
      :body="t('history.emptyBody')"
    />

    <template v-else>
      <button
        v-if="live?.active && live.performance"
        class="live-banner"
        @click="selectPerformance(live.performance.id)"
      >
        <span class="live-dot" aria-hidden="true" />
        {{
          t('history.liveBanner', {
            n: live.performance.track_count,
            time: fmtTime(live.performance.ended_at),
          })
        }}
        <span class="live-open">{{ t('history.liveShow') }} →</span>
      </button>

      <div class="toolbar">
        <button
          v-for="chip in ['main', 'all', 'hidden'] as const"
          :key="chip"
          class="chip"
          :data-active="filter === chip"
          @click="filter = chip"
        >
          {{ t(`history.filters.${chip}`) }}
          <span class="chip-n mono">{{ counts[chip] }}</span>
        </button>
      </div>

      <div class="split">
        <div class="list">
          <button
            v-for="p in visible"
            :key="p.id"
            class="item"
            :data-active="p.id === selectedId"
            @click="selectPerformance(p.id)"
          >
            <div class="item-line">
              <span class="item-name">{{ displayName(p) }}</span>
              <span
                v-if="live?.active && live.performance?.id === p.id"
                class="live-dot"
                aria-hidden="true"
              />
            </div>
            <div class="item-meta">
              <span class="mono">{{ fmtDate(p.started_at) }}</span>
              · {{ fmtTime(p.started_at) }}–{{ fmtTime(p.ended_at) }}
              · <span class="mono">{{ p.track_count }}</span> {{ t('history.tracksUnit') }}
            </div>
            <div v-if="p.cuts.length || p.bulk_import || p.overlaps" class="item-badges">
              <span v-if="p.cuts.length" class="badge cut">⚡ {{ t('history.cutBadge') }}</span>
              <span v-if="p.bulk_import" class="badge usb" :title="t('history.usbNote')">
                {{ t('history.usbBadge') }}
              </span>
              <span v-if="p.overlaps" class="badge overlap" :title="t('history.overlapNote')">
                ⧉ {{ t('history.overlapBadge') }}
              </span>
            </div>
          </button>
        </div>

        <section v-if="selected" class="workspace" :data-live="liveIsSelected">
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
                  <button class="ghost" @click="saveRename">
                    {{ t('history.renameSave') }}
                  </button>
                  <button class="ghost" @click="renaming = false">
                    {{ t('common.cancel') }}
                  </button>
                </template>
                <template v-else>
                  <div class="ws-name">{{ displayName(selected) }}</div>
                  <button class="ghost" :title="t('history.rename')" @click="startRename">
                    ✎
                  </button>
                </template>
              </div>
              <div class="ws-meta">
                {{ fmtDate(selected.started_at) }} · {{ fmtTime(selected.started_at) }}–{{
                  fmtTime(selected.ended_at)
                }}
                · {{ fmtDuration(selected) }} ·
                <span class="mono">{{ selected.track_count }}</span>
                {{ t('history.tracksUnit') }} ·
                {{ t('history.sessionsUnit', selected.session_count) }}
              </div>
              <div v-if="selected.bulk_import || selected.overlaps" class="ws-notes">
                <div v-if="selected.bulk_import">{{ t('history.usbNote') }}</div>
                <div v-if="selected.overlaps">{{ t('history.overlapNote') }}</div>
              </div>
            </div>
            <button
              class="export-btn"
              :disabled="status.rbOpen || exporting"
              @click="exportPlaylist"
            >
              {{ status.rbOpen ? t('rbGuard.blocked') : t('history.exportCta') }}
            </button>
            <button class="btn-secondary" @click="toggleHidden">
              {{ selected.hidden ? t('history.unhide') : t('history.hide') }}
            </button>
          </div>

          <div v-if="banner" class="banner" :data-tone="banner.tone" role="status">
            <span class="banner-text">{{ banner.text }}</span>
            <button class="banner-close" @click="banner = null">✕</button>
          </div>

          <div class="table">
            <div class="table-head">
              <span class="cell-time">{{ t('history.columns.time') }}</span>
              <span class="cell-title">{{ t('history.columns.title') }}</span>
            </div>
            <template v-for="(row, index) in displayRows" :key="row.track.uuid">
              <div v-if="row.cut" class="cut-row">
                ⚡
                {{
                  t('history.cutRow', {
                    ended: fmtTime(row.cut.ended),
                    resumed: fmtTime(row.cut.resumed),
                  })
                }}
              </div>
              <div class="row">
                <span class="cell-time mono">
                  <span class="track-no">{{ index + 1 }}</span>
                  {{ selected.bulk_import ? '—' : fmtTime(row.track.played_at) }}
                </span>
                <div class="cell-title">
                  <div class="row-title-line">
                    <span class="row-title" :data-pending="!row.track.title">
                      {{ row.track.title ?? t('history.spotifyPending') }}
                    </span>
                    <SpotifyAttributionLink
                      v-if="row.track.spotify_track_id"
                      kind="track"
                      :spotify-id="row.track.spotify_track_id"
                    />
                  </div>
                  <div class="row-artist">{{ row.track.artist }}</div>
                </div>
              </div>
            </template>
          </div>
        </section>
      </div>
    </template>
  </main>
</template>

<style scoped>
.screen {
  padding: var(--screen-padding);
  max-width: var(--content-max-width);
  margin: 0 auto;
}
.head {
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
.mono {
  font-family: var(--font-mono);
}
.live-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  background: rgba(52, 211, 153, 0.08);
  border: 1px solid rgba(52, 211, 153, 0.3);
  color: var(--text-primary);
  border-radius: 11px;
  padding: 11px 15px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  margin-bottom: 14px;
  text-align: left;
}
.live-open {
  margin-left: auto;
  color: var(--success);
  font-weight: 600;
  font-size: 12.5px;
  white-space: nowrap;
}
.live-dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--success);
  animation: live-pulse 1.6s ease-in-out infinite;
}
@keyframes live-pulse {
  50% {
    opacity: 0.35;
  }
}
.toolbar {
  display: flex;
  gap: 7px;
  margin-bottom: 14px;
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
.split {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.list {
  flex: none;
  width: 300px;
  max-height: 70vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.item {
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 11px;
  padding: 10px 12px;
  cursor: pointer;
  text-align: left;
  color: inherit;
}
.item:hover {
  border-color: #2a3242;
}
.item[data-active='true'] {
  border-color: var(--accent-border);
  background: rgba(77, 163, 255, 0.06);
}
.item-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.item-name {
  font-weight: 600;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.item-meta {
  font-size: 11.5px;
  color: var(--text-muted);
  margin-top: 3px;
}
.item-badges {
  display: flex;
  gap: 5px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.badge {
  font-size: 10px;
  font-weight: 700;
  border-radius: 5px;
  padding: 1px 6px;
  white-space: nowrap;
}
.badge.cut {
  color: var(--warning-text);
  background: var(--warning-tint);
  border: 1px solid rgba(245, 181, 68, 0.28);
}
.badge.usb {
  color: var(--text-muted-bright);
  background: var(--surface);
  border: 1px solid var(--border-2);
}
.badge.overlap {
  color: var(--accent-hover);
  background: var(--accent-tint);
  border: 1px solid var(--accent-border);
}
.workspace {
  flex: 1;
  min-width: 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  overflow: clip;
}
.workspace[data-live='true'] {
  border-color: rgba(52, 211, 153, 0.4);
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
.ws-notes {
  font-size: 11.5px;
  color: var(--text-muted);
  margin-top: 5px;
  line-height: 1.5;
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
.export-btn {
  background: var(--success);
  border: none;
  color: #06131f;
  padding: 8px 14px;
  border-radius: 9px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  flex: none;
}
.export-btn:disabled {
  background: #1a1e26;
  border: 1px solid #2a3140;
  color: var(--text-muted);
  cursor: not-allowed;
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
.table-head {
  display: flex;
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
  padding: 9px 18px;
  border-bottom: 1px solid var(--border-subtle);
}
.cell-time {
  flex: none;
  width: 92px;
  font-size: 12px;
  color: var(--text-muted-bright);
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
}
.track-no {
  color: var(--text-muted);
  font-size: 10.5px;
  min-width: 20px;
  text-align: right;
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
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.row-title[data-pending='true'] {
  color: var(--text-muted);
  font-style: italic;
}
.row-artist {
  font-size: 11.5px;
  color: var(--text-muted-bright);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cut-row {
  padding: 7px 18px;
  font-size: 11.5px;
  color: var(--warning-text);
  background: rgba(245, 181, 68, 0.06);
  border-bottom: 1px solid var(--border-subtle);
}
</style>
