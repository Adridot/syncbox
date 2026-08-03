<script setup lang="ts">
// Bibliothèque (M4.7 — SPEC-DESIGN §2/§6, M4-PLAN §5): master list of the
// followed Spotify sources + the review table, wired to the real REST/SSE.
// Every user-triggered action surfaces its backend error (B1) — no silent
// no-op click anywhere. The apply CTA is owner-arbitrated (2026-07-07):
// selection-scoped, RB-guarded, exact-count label (B10 spirit).
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, NetworkError, api } from '../api/client'
import type { LibraryTrack, Source } from '../api/types'
import AddSourceModal from '../components/AddSourceModal.vue'
import BulkTagModal from '../components/BulkTagModal.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import JobRow from '../components/JobRow.vue'
import LoadingState from '../components/LoadingState.vue'
import ReMatchModal from '../components/ReMatchModal.vue'
import SelectionBar from '../components/SelectionBar.vue'
import SpotifyAttributionLink from '../components/SpotifyAttributionLink.vue'
import StatusBadge from '../components/StatusBadge.vue'
import {
  FILTER_CHIPS,
  type FilterChip,
  confTone,
  filterByChip,
  isApplicable,
  isRematchable,
  isReview,
} from '../lib/library'
import { useRefreshOnReturn } from '../lib/refresh'
import { useVirtualRows } from '../lib/virtualRows'
import { useSpotifyConnect } from '../lib/useSpotifyConnect'
import { useHealthStore } from '../stores/health'
import { useJobsStore } from '../stores/jobs'
import { useSettingsStore } from '../stores/settings'
import { useStatusStore } from '../stores/status'

const { t } = useI18n()
const status = useStatusStore()
const jobs = useJobsStore()
const health = useHealthStore()
const settings = useSettingsStore()
const spotify = useSpotifyConnect()

const sources = ref<Source[] | null>(null)
const tracksBySource = reactive<Record<number, LibraryTrack[]>>({})
const selectedSource = ref<'all' | number>('all')
const filter = ref<FilterChip>('all')
const search = ref('')
const selection = ref<Set<number>>(new Set())
const loading = ref(true)
const loadError = ref<string | null>(null)
const banner = ref<{ tone: 'error' | 'success'; text: string; connect?: boolean } | null>(null)
const restoredFlash = reactive<Record<number, string>>({})
const modal = ref<null | 'add' | 'tags'>(null)
const rematchTrack = ref<LibraryTrack | null>(null)
const unfollowArmed = ref(false)

const threshold = computed(() => settings.values?.match_confidence_threshold ?? 82)

function describe(cause: unknown): { text: string; connect?: boolean } {
  if (cause instanceof ApiError) {
    if (cause.code === 'spotify_not_connected')
      return { text: t('library.add.notConnected'), connect: true }
    if (cause.code === 'spotify_api_error' && cause.body.status_code === 404)
      return { text: t('library.add.privatePlaylist'), connect: true }
    return { text: cause.message }
  }
  if (cause instanceof NetworkError) return { text: t('common.networkError') }
  return { text: String(cause) }
}

async function load() {
  // skeleton on FIRST load only: refreshes (sync, apply, add-source) keep
  // the grid mounted — no full-screen flash (owner feedback 15/07)
  loading.value = sources.value === null
  loadError.value = null
  try {
    const list = (await api.get<{ sources: Source[] }>('/api/sources')).sources
    const results = await Promise.all(
      list.map((source) =>
        api.get<{ tracks: LibraryTrack[] }>(`/api/sources/${source.id}/tracks`),
      ),
    )
    const nextTracks: Record<number, LibraryTrack[]> = {}
    list.forEach((source, index) => {
      nextTracks[source.id] = results[index].tracks
    })
    // windowed table: swapping the refs re-patches only the ~viewport rows,
    // keyed by stable ids — an identical payload causes zero DOM mutation,
    // so no whole-payload compare is needed (design Decision 2)
    sources.value = list
    for (const key of Object.keys(tracksBySource))
      if (!(key in nextTracks)) delete tracksBySource[key as unknown as number]
    Object.assign(tracksBySource, nextTracks)
    health.setLibraryReviewCount(allTracks.value.filter(isReview).length)
    if (firstLoad) {
      firstLoad = false
      defaultFilter()
    }
  } catch (cause) {
    loadError.value = describe(cause).text
  } finally {
    loading.value = false
  }
}
let firstLoad = true
// skeleton on first load only; keep-alive re-entries refresh silently
useRefreshOnReturn(() => {
  if (!settings.loaded) void settings.load().catch(() => {})
  void load()
})

const allTracks = computed(() =>
  (sources.value ?? []).flatMap((source) => tracksBySource[source.id] ?? []),
)
const scopedTracks = computed(() =>
  selectedSource.value === 'all' ? allTracks.value : (tracksBySource[selectedSource.value] ?? []),
)
const visibleTracks = computed(() => filterByChip(scopedTracks.value, filter.value))

// windowed table body: only ~viewport rows are in the DOM (ui-performance)
const tableBodyEl = ref<HTMLElement | null>(null)
const { rowItems, totalSize, measure, rowStyle } = useVirtualRows(
  () => visibleTracks.value,
  tableBodyEl,
)

const reviewCounts = computed(() => {
  const counts: Record<number, number> = {}
  for (const source of sources.value ?? [])
    counts[source.id] = (tracksBySource[source.id] ?? []).filter(isReview).length
  return counts
})
const totalReview = computed(() => allTracks.value.filter(isReview).length)

const visibleSources = computed(() => {
  const q = search.value.trim().toLowerCase()
  const list = [...(sources.value ?? [])].sort((a, b) =>
    (a.name || '').localeCompare(b.name || '', undefined, { sensitivity: 'base' }),
  ) // alphabetical (owner feedback 07/07)
  return q ? list.filter((source) => source.name.toLowerCase().includes(q)) : list
})

const currentSource = computed(() =>
  selectedSource.value === 'all'
    ? null
    : (sources.value ?? []).find((source) => source.id === selectedSource.value) ?? null,
)
const contextSub = computed(() => {
  if (currentSource.value)
    return t('library.tracksFollowed', { n: (tracksBySource[currentSource.value.id] ?? []).length })
  const list = sources.value ?? []
  return t('library.allSub', { playlists: list.length, tracks: allTracks.value.length })
})

watch([selectedSource, filter], () => {
  selection.value = new Set()
  unfollowArmed.value = false
})

/** To-review first (owner feedback 07/07): entering a source — or the app —
    lands on « À traiter » when there is review work, on « Tous » otherwise.
    Manual chip picks are respected until the selection changes again. */
function defaultFilter() {
  filter.value = scopedTracks.value.some(isReview) ? 'review' : 'all'
}
watch(selectedSource, defaultFilter)

// --- selection (select-all over FILTERED rows only, M4-PLAN M4.7) ---------
const allVisibleSelected = computed(
  () =>
    visibleTracks.value.length > 0 &&
    visibleTracks.value.every((track) => selection.value.has(track.id)),
)
function toggleAll() {
  const next = new Set(selection.value)
  if (allVisibleSelected.value) visibleTracks.value.forEach((track) => next.delete(track.id))
  else visibleTracks.value.forEach((track) => next.add(track.id))
  selection.value = next
}
function toggleOne(id: number) {
  const next = new Set(selection.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selection.value = next
}

const selectedTracks = computed(() =>
  scopedTracks.value.filter((track) => selection.value.has(track.id)),
)
const applicableSelected = computed(() => selectedTracks.value.filter(isApplicable))

// --- actions (every one surfaces its error — B1) ---------------------------
async function syncAll() {
  banner.value = null
  try {
    const { results } = await api.post<{
      results: Array<{ source_id: number; error?: string }>
    }>('/api/sources/sync')
    const failed = results.filter((result) => result.error)
    banner.value = failed.length
      ? {
          tone: 'error',
          text: t('library.syncPartial', { n: failed.length }) + ' — ' + failed.map((f) => f.error).join(' · '),
        }
      : { tone: 'success', text: t('library.syncDone', { n: results.length }) }
    await load()
  } catch (cause) {
    banner.value = { tone: 'error', ...describe(cause) }
  }
}

async function syncOne(source: Source) {
  banner.value = null
  try {
    await api.post(`/api/sources/${source.id}/sync`)
    banner.value = { tone: 'success', text: t('library.syncDone', { n: 1 }) }
    await load()
  } catch (cause) {
    banner.value = { tone: 'error', ...describe(cause) }
  }
}

async function unfollow(source: Source) {
  banner.value = null
  try {
    await api.delete(`/api/sources/${source.id}`)
    selectedSource.value = 'all'
    await load()
  } catch (cause) {
    banner.value = { tone: 'error', ...describe(cause) }
  } finally {
    unfollowArmed.value = false
  }
}

function replaceTrack(updated: LibraryTrack) {
  const list = tracksBySource[updated.source_id]
  const index = list?.findIndex((track) => track.id === updated.id) ?? -1
  if (index >= 0) list[index] = updated
  health.setLibraryReviewCount(allTracks.value.filter(isReview).length)
}

async function ignoreTrack(track: LibraryTrack) {
  banner.value = null
  try {
    replaceTrack(await api.post<LibraryTrack>(`/api/library/tracks/${track.id}/ignore`))
  } catch (cause) {
    banner.value = { tone: 'error', ...describe(cause) }
  }
}

async function restoreTrack(track: LibraryTrack) {
  banner.value = null
  try {
    const updated = await api.post<LibraryTrack>(`/api/library/tracks/${track.id}/restore`)
    replaceTrack(updated)
    // D22 inline feedback: show WHERE the row went back to, no modal
    restoredFlash[updated.id] = updated.status
    setTimeout(() => delete restoredFlash[updated.id], 4000)
  } catch (cause) {
    banner.value = { tone: 'error', ...describe(cause) }
  }
}

async function applySelection() {
  banner.value = null
  const bySource = new Map<number, number[]>()
  for (const track of applicableSelected.value) {
    const list = bySource.get(track.source_id) ?? []
    list.push(track.id)
    bySource.set(track.source_id, list)
  }
  const failures: string[] = []
  let applied = 0
  for (const [sourceId, trackIds] of bySource) {
    try {
      await api.post(`/api/sources/${sourceId}/apply`, { track_ids: trackIds })
      applied += trackIds.length
    } catch (cause) {
      failures.push(describe(cause).text)
    }
  }
  banner.value = failures.length
    ? { tone: 'error', text: failures.join(' · ') }
    : { tone: 'success', text: t('library.applyDone', { n: applied }) }
  selection.value = new Set()
  await load()
}

function onRematchUpdated(track: LibraryTrack) {
  replaceTrack(track)
  rematchTrack.value = null
}

function onTagsApplied(tracks: LibraryTrack[]) {
  tracks.forEach(replaceTrack)
  selection.value = new Set()
  modal.value = null
}

async function onSourceAdded(source: Source) {
  // a fresh source starts empty — sync it right away so it never sits at
  // "0 tracks" (owner feedback 07/07); syncOne banners its own failure (B1)
  modal.value = null
  await load()
  void syncOne(source)
}
</script>

<template>
  <main class="screen">
    <header class="head">
      <div>
        <h1>{{ t('nav.library') }}</h1>
        <p class="tagline">{{ t('library.tagline') }}</p>
      </div>
      <button class="btn-secondary" :disabled="jobs.jobRunning" @click="syncAll">
        <span class="btn-icon">↻</span>{{ t('library.syncAll') }}
      </button>
    </header>

    <LoadingState v-if="loading" :rows="5" />

    <ErrorState v-else-if="loadError" :title="t('library.loadErrorTitle')" :body="loadError">
      <button class="btn-secondary" @click="load">{{ t('common.retry') }}</button>
    </ErrorState>

    <EmptyState
      v-else-if="!sources?.length"
      icon="≡"
      :title="t('library.emptyTitle')"
      :body="t('library.emptyBody')"
    >
      <button class="btn-primary" @click="modal = 'add'">{{ t('library.addSource') }}</button>
    </EmptyState>

    <div v-else class="grid">
      <!-- master list -->
      <aside class="master">
        <div class="master-head">
          <div class="master-title-row">
            <div class="master-title">
              <span>{{ t('library.sourcesTitle') }}</span>
              <span class="count mono">{{ sources.length }}</span>
            </div>
            <button class="add-btn" :data-tip="t('library.addSource')" :aria-label="t('library.addSource')" @click="modal = 'add'">+</button>
          </div>
          <div class="search-row">
            <span class="glyph">⌕</span>
            <input v-model="search" type="text" :placeholder="t('library.searchPlaceholder')" />
          </div>
        </div>
        <div class="master-rows">
          <button
            class="source-row"
            :data-active="selectedSource === 'all'"
            @click="selectedSource = 'all'"
          >
            <span class="cover neutral">≡</span>
            <span class="source-text">
              <span class="source-name">{{ t('library.allSources') }}</span>
              <span class="source-meta mono">{{ t('library.toReview', { n: totalReview }) }}</span>
            </span>
          </button>
          <div class="divider" />
          <div
            v-for="source in visibleSources"
            :key="source.id"
            class="source-entry hover-reveal"
            :data-disabled="!source.enabled"
          >
            <button
              class="source-row"
              :data-active="selectedSource === source.id"
              @click="selectedSource = source.id"
            >
              <img
                v-if="source.cover_url"
                class="cover art"
                :src="source.cover_url"
                alt=""
                loading="lazy"
              />
              <span v-else class="cover" :data-pending="source.status === 'pending'">{{
                (source.name || '?').replace(/[^A-Za-z0-9]/g, '').slice(0, 1).toUpperCase() || '?'
              }}</span>
              <span class="source-text">
                <span class="source-name">{{ source.name || source.spotify_playlist_id }}</span>
                <span class="source-meta mono">{{
                  t('library.add.tracksUnit', { n: (tracksBySource[source.id] ?? []).length })
                }}</span>
              </span>
              <span v-if="reviewCounts[source.id]" class="review-badge mono">{{
                reviewCounts[source.id]
              }}</span>
            </button>
            <SpotifyAttributionLink
              kind="playlist"
              :spotify-id="source.spotify_playlist_id"
            />
          </div>
        </div>
      </aside>

      <!-- review surface -->
      <section class="review">
        <div class="context hover-reveal">
          <h2>{{ currentSource ? currentSource.name : t('library.allSources') }}</h2>
          <span class="context-sub">{{ contextSub }}</span>
          <span class="spacer" />
          <template v-if="currentSource">
            <SpotifyAttributionLink
              kind="playlist"
              :spotify-id="currentSource.spotify_playlist_id"
            />
            <button class="ghost" :disabled="jobs.jobRunning" @click="syncOne(currentSource)">
              ↻ {{ t('library.syncOne') }}
            </button>
            <button v-if="!unfollowArmed" class="ghost" @click="unfollowArmed = true">
              {{ t('library.unfollow') }}
            </button>
            <button v-else class="ghost danger" @click="unfollow(currentSource)">
              {{ t('library.unfollowConfirm') }}
            </button>
            <button class="ghost" @click="selectedSource = 'all'">
              ↩ {{ t('library.allSources') }}
            </button>
          </template>
        </div>

        <!-- B1 surface: sync/apply/action outcomes, never silent -->
        <div v-if="banner" class="banner" :data-tone="banner.tone" role="status">
          <span class="banner-text">{{ banner.text }}</span>
          <button v-if="banner.connect" class="btn-secondary small" @click="spotify.connect">
            {{ t('library.add.connectCta') }}
          </button>
          <button class="banner-close" @click="banner = null">✕</button>
        </div>
        <div v-if="spotify.error.value" class="banner" data-tone="error" role="status">
          <span class="banner-text">{{ spotify.error.value }}</span>
        </div>

        <JobRow kind="sources.sync_all" :label="t('activity.job_sources_sync_all')" />
        <JobRow kind="sources.sync" :label="t('activity.job_sources_sync')" />
        <JobRow kind="sources.apply" :label="t('activity.job_sources_apply')" />

        <div class="toolbar">
          <button
            v-for="chip in FILTER_CHIPS"
            :key="chip"
            class="chip"
            :data-active="filter === chip"
            @click="filter = chip"
          >
            {{ t(`library.filters.${chip}`) }}
          </button>
          <span class="spacer" />
          <span class="sel-hint">{{ t('library.selection.hint') }}</span>
        </div>

        <div class="table">
          <div class="table-head">
            <span class="cell-check">
              <input
                type="checkbox"
                :checked="allVisibleSelected"
                :aria-label="t('library.selection.all')"
                @change="toggleAll"
              />
            </span>
            <span class="cell-title">{{ t('library.columns.title') }}</span>
            <span>{{ t('library.columns.status') }}</span>
            <span class="cell-actions" />
          </div>
          <div ref="tableBodyEl" class="table-body">
            <div v-if="visibleTracks.length" class="v-rows" :style="{ height: `${totalSize}px` }">
            <div
              v-for="{ item, row: track } in rowItems"
              :key="track.id"
              :ref="measure"
              :data-index="item.index"
              class="row hover-reveal"
              :data-selected="selection.has(track.id)"
              :style="rowStyle(item)"
            >
              <span class="cell-check">
                <input
                  type="checkbox"
                  :checked="selection.has(track.id)"
                  :aria-label="track.title ?? ''"
                  @change="toggleOne(track.id)"
                />
              </span>
              <div class="cell-title">
                <div class="row-title-line">
                  <div class="row-title">{{ track.title }}</div>
                  <SpotifyAttributionLink
                    v-if="track.spotify_track_id"
                    kind="track"
                    :spotify-id="track.spotify_track_id"
                  />
                </div>
                <div class="row-meta">
                  <span class="artist">{{ track.artist }}</span>
                  <template v-if="track.confidence">
                    <span class="dot">·</span>
                    <span class="mono conf" :data-tone="confTone(track.confidence, threshold)"
                      >{{ track.confidence }}%</span
                    >
                  </template>
                  <template v-if="track.bit_rate">
                    <span class="dot">·</span>
                    <span class="mono br">{{ track.bit_rate }}k</span>
                  </template>
                  <span v-if="restoredFlash[track.id]" class="restored-flash">
                    {{ t('library.restoredTo', { status: t(`status.${restoredFlash[track.id]}`) }) }}
                  </span>
                </div>
              </div>
              <span class="cell-status"><StatusBadge :status="track.status" /></span>
              <span class="cell-actions">
                <router-link
                  v-if="['missing', 'acquisition_failed'].includes(track.status)"
                  class="action"
                  to="/missing/library"
                  :data-tip="t('library.actions.resolve')"
                  :aria-label="t('library.actions.resolve')"
                >
                  <!-- inline SVG (not a glyph): renders pixel-identical to the
                       other action buttons, immune to font fallback -->
                  <svg
                    class="ic"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M12 3v12" />
                    <path d="m7 11 5 5 5-5" />
                    <path d="M5 21h14" />
                  </svg>
                </router-link>
                <button
                  v-if="track.status === 'ignored'"
                  class="action"
                  :data-tip="t('library.actions.restore')"
                  :aria-label="t('library.actions.restore')"
                  @click="restoreTrack(track)"
                >
                  ↺
                </button>
                <button
                  v-if="isRematchable(track)"
                  class="action"
                  :data-tip="t('library.actions.rematch')"
                  :aria-label="t('library.actions.rematch')"
                  @click="rematchTrack = track"
                >
                  ↻
                </button>
                <button
                  v-if="isRematchable(track)"
                  class="action"
                  :data-tip="t('library.actions.ignore')"
                  :aria-label="t('library.actions.ignore')"
                  @click="ignoreTrack(track)"
                >
                  ✕
                </button>
              </span>
            </div>
            </div>
            <div v-else class="table-empty">
              <div class="empty-glyph">✓</div>
              <div class="empty-title">{{ t('library.tableEmptyTitle') }}</div>
              <p class="empty-body">{{ t('library.tableEmptyBody') }}</p>
            </div>
          </div>
        </div>

        <!-- floating pill: the table never shifts when a selection starts -->
        <div class="sel-float-anchor">
          <SelectionBar :count="selection.size" @clear="selection = new Set()">
            <button class="sel-action" @click="modal = 'tags'">
              {{ t('library.selection.editTags') }}
            </button>
            <button
              class="sel-action apply"
              :disabled="status.rbOpen || jobs.jobRunning || !applicableSelected.length"
              @click="applySelection"
            >
              {{
                status.rbOpen
                  ? t('rbGuard.blocked')
                  : t('library.selection.apply', { n: applicableSelected.length })
              }}
            </button>
          </SelectionBar>
        </div>
      </section>
    </div>

    <AddSourceModal
      v-if="modal === 'add'"
      :followed-ids="(sources ?? []).map((s) => s.spotify_playlist_id)"
      @close="modal = null"
      @added="onSourceAdded"
    />
    <BulkTagModal
      v-if="modal === 'tags'"
      :track-ids="[...selection]"
      @close="modal = null"
      @applied="onTagsApplied"
    />
    <ReMatchModal
      v-if="rematchTrack"
      :track="rematchTrack"
      @close="rematchTrack = null"
      @updated="onRematchUpdated"
    />
  </main>
</template>

<style scoped>
.screen {
  padding: var(--screen-padding);
  max-width: var(--content-max-width);
  margin: 0 auto;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  box-sizing: border-box;
}
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 20px;
  flex: none;
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
.grid {
  display: grid;
  grid-template-columns: 288px minmax(0, 1fr);
  gap: 20px;
  align-items: stretch;
  flex: 1;
  min-height: 0;
}
.master {
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  overflow: clip;
}
.master-head {
  padding: 13px 14px 11px;
  border-bottom: 1px solid var(--border-subtle-2);
  flex: none;
}
.master-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}
.master-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
}
.count {
  font-size: var(--size-meta);
  color: var(--text-muted-bright);
  background: #12151d;
  border: 1px solid var(--border-2);
  border-radius: 6px;
  padding: 1px 7px;
}
.add-btn {
  background: var(--accent-tint);
  border: 1px solid var(--accent-border);
  color: var(--accent-hover);
  width: 26px;
  height: 26px;
  border-radius: 7px;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  display: grid;
  place-content: center;
}
.search-row {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 8px;
  padding: 6px 10px;
}
.search-row .glyph {
  color: var(--text-muted);
  font-size: 12px;
}
.search-row input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-secondary-bright);
  font: inherit;
  font-size: 12.5px;
}
.master-rows {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.source-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 9px;
  cursor: pointer;
  background: transparent;
  border: 1px solid transparent;
  color: inherit;
  text-align: left;
  width: 100%;
}
.source-row:hover {
  background: #141823;
}
.source-row[data-active='true'] {
  background: var(--accent-tint);
  border-color: var(--accent-border);
}
.source-row[data-disabled='true'] {
  opacity: 0.6;
}
.source-entry {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}
.source-entry .source-row {
  min-width: 0;
  flex: 1;
}
.source-entry[data-disabled='true'] {
  opacity: 0.6;
}
.cover {
  width: 30px;
  height: 30px;
  flex: none;
  border-radius: 7px;
  display: grid;
  place-content: center;
  font-size: 13px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.92);
  background: linear-gradient(135deg, var(--accent), var(--teal));
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
}
.cover[data-pending='true'] {
  background: linear-gradient(135deg, var(--warning), var(--danger));
}
.cover.art {
  object-fit: contain;
  background: var(--surface-raised);
}
.cover.neutral {
  background: #171c27;
  border: 1px solid #232a38;
  color: #8b97a9;
  font-size: 14px;
  font-weight: 400;
}
.source-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.source-name {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.source-meta {
  font-size: var(--size-meta);
  color: var(--text-muted);
}
.review-badge {
  flex: none;
  font-size: var(--size-meta);
  font-weight: 700;
  color: var(--accent-hover);
  background: var(--accent-tint);
  border: 1px solid var(--accent-border);
  border-radius: 6px;
  padding: 1px 7px;
}
.divider {
  height: 1px;
  background: #161b26;
  margin: 5px 2px;
  flex: none;
}
.review {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  position: relative; /* anchors the floating selection pill */
}
.context {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 13px;
  flex: none;
  min-width: 0;
}
.context h2 {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.01em;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  flex: 0 1 auto;
}
.context-sub {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
  flex: none;
}
.spacer {
  flex: 1;
}
.ghost {
  background: transparent;
  border: none;
  color: var(--text-muted-bright);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  flex: none;
  padding: 0;
}
.ghost:hover {
  color: var(--accent-hover);
}
.ghost.danger {
  color: var(--danger-text);
}
.ghost:disabled {
  opacity: 0.5;
  cursor: default;
}
.banner {
  display: flex;
  align-items: center;
  gap: 10px;
  border-radius: 9px;
  padding: 9px 12px;
  margin-bottom: 12px;
  font-size: 12.5px;
  flex: none;
}
.banner[data-tone='error'] {
  background: var(--danger-tint);
  border: 1px solid var(--danger-border);
  color: var(--danger-text);
}
.banner[data-tone='success'] {
  background: var(--success-tint);
  border: 1px solid var(--success-border);
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
.btn-secondary.small {
  padding: 5px 10px;
  font-size: 12px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  flex-wrap: wrap;
  flex: none;
}
.chip {
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  color: #8b97a9;
  background: #12151d;
  border: 1px solid var(--border-2);
}
.chip[data-active='true'] {
  color: var(--text-primary);
  background: rgba(77, 163, 255, 0.14);
  border-color: var(--accent-border);
}
.sel-float-anchor {
  position: absolute;
  bottom: 18px;
  left: 0;
  right: 0;
  display: flex;
  justify-content: center;
  z-index: 6;
  pointer-events: none;
}
.sel-float-anchor > * {
  pointer-events: auto;
}
.sel-action {
  background: rgba(77, 163, 255, 0.16);
  color: var(--accent-hover);
  border: 1px solid var(--accent-border);
  padding: 4px 11px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.sel-action.apply {
  background: var(--teal-tint);
  color: var(--teal);
  border-color: var(--teal-border);
}
.sel-action:disabled {
  opacity: 0.55;
  cursor: default;
}
.sel-hint {
  font-size: 12px;
  color: var(--text-muted);
}
.table {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  overflow: clip;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.table-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 18px;
  border-bottom: 1px solid var(--border-subtle-2);
  font-size: var(--size-meta);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  font-weight: 600;
  flex: none;
}
.table-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
/* windowing: rows are absolutely positioned inside a wrapper sized to the
   full list — the row markup and classes themselves are untouched */
.v-rows {
  position: relative;
}
.v-rows > .row {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
}
.cell-check {
  width: 26px;
  display: flex;
  align-items: center;
  flex: none;
  align-self: stretch; /* the whole cell height stays clickable */
}
.cell-title {
  flex: 1;
  min-width: 0;
}
.cell-status {
  flex: none;
}
.cell-actions {
  /* room for the 3 action buttons (28px each + 4px gaps) so they never get
     squeezed narrower than tall — owner feedback 07/07 */
  width: 96px;
  flex: none;
  display: flex;
  align-items: center;
  gap: 4px;
  justify-content: flex-end;
}
.row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: var(--row-padding-y) 18px;
  border-bottom: 1px solid var(--border-subtle);
}
.row:hover {
  background: #0f131b;
}
.row[data-selected='true'] {
  background: rgba(77, 163, 255, 0.06);
}
.row-title {
  font-size: 13.5px;
  font-weight: 500;
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.row-title-line {
  display: flex;
  align-items: center;
  gap: 8px;
}
.row-title-line .row-title {
  min-width: 0;
}
.row-meta {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 2px;
  font-size: 11.5px;
  min-width: 0;
}
.artist {
  color: var(--text-muted-bright);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.dot {
  color: #2a3140;
  flex: none;
}
.conf[data-tone='success'] {
  color: var(--success);
}
.conf[data-tone='accent'] {
  color: var(--accent);
}
.conf[data-tone='warning'] {
  color: var(--warning);
}
.br {
  color: var(--text-muted-bright);
  flex: none;
}
.restored-flash {
  color: var(--success);
  flex: none;
}
.mono {
  font-family: var(--font-mono);
}
.action {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid #2a3140;
  color: var(--text-secondary);
  border-radius: 7px;
  font-size: 15px;
  line-height: 1;
  padding: 0;
  cursor: pointer;
  text-decoration: none;
}
.action .ic {
  width: 15px;
  height: 15px;
}
.action:hover {
  color: var(--accent-hover);
  border-color: var(--accent-border);
}
.table-empty {
  padding: 46px 18px;
  text-align: center;
}
.empty-glyph {
  font-size: 22px;
  opacity: 0.4;
  margin-bottom: 8px;
}
.empty-title {
  font-size: 13.5px;
  color: var(--text-secondary);
  font-weight: 500;
}
.empty-body {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}
</style>
