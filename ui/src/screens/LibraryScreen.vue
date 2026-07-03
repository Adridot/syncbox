<script setup lang="ts">
// Bibliothèque (SPEC-DESIGN §2/§6): source master list (aggregate row +
// searchable per-source rows with review-count badges) + TrackReviewTable
// (status filter chips, select-all over FILTERED rows, confidence/bitrate
// chips, match method hidden) + BulkTagBar/TagPicker + ReMatchModal (G2) +
// ignore/restore (D22 inline) + missing rows linking to the Missing center.
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { ApiError, api } from '../api/client'
import AddSourceModal from '../components/AddSourceModal.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import LoadingState from '../components/LoadingState.vue'
import ReMatchModal from '../components/ReMatchModal.vue'
import StatusBadge from '../components/StatusBadge.vue'
import TagPickerModal from '../components/TagPickerModal.vue'
import { openExternal } from '../shell'
import { useHealthStore } from '../stores/health'
import { useJobsStore } from '../stores/jobs'
import { useLibraryStore, type LibraryTrack } from '../stores/library'
import { useSettingsStore } from '../stores/settings'

const { t } = useI18n()
const router = useRouter()
const library = useLibraryStore()
const health = useHealthStore()
const jobs = useJobsStore()
const settings = useSettingsStore()

const loading = ref(true)
const error = ref<'spotify_404' | 'generic' | null>(null)
type TrackWithSource = LibraryTrack & { sourceId: number }

const search = ref('')
const selectedSource = ref<number | null>(null) // null = "all sources"
const statusFilter = ref('all')
const checked = ref<Set<number>>(new Set())
const showAddSource = ref(false)
const rematchTrack = ref<TrackWithSource | null>(null)
const showTagPicker = ref(false)

// "Tous" hides ignored/removed_from_source (SPEC-DESIGN §6).
const HIDDEN_FROM_ALL = new Set(['ignored', 'removed_from_source'])
const FILTERS = ['all', 'new', 'matched', 'conflict', 'ready', 'missing', 'ignored']

onMounted(load)

async function load() {
  loading.value = true
  error.value = null
  try {
    if (!settings.loaded) await settings.load()
    if (!settings.configured) {
      loading.value = false
      return
    }
    await library.loadSources()
    pushReviewCount()
  } catch (err) {
    if (err instanceof ApiError && err.code === 'spotify_api_error' && err.body.status_code === 404)
      error.value = 'spotify_404'
    else if (err instanceof ApiError) error.value = 'generic'
  } finally {
    loading.value = false
  }
}

function pushReviewCount() {
  const total = library.sources.reduce((sum, s) => sum + library.reviewCountOf(s.id), 0)
  health.setLibraryReviewCount(total)
}

const filteredSources = computed(() => {
  const q = search.value.trim().toLowerCase()
  return library.sources.filter((s) => !q || s.name.toLowerCase().includes(q))
})

const activeTracks = computed<TrackWithSource[]>(() => {
  if (selectedSource.value === null) return library.allTracks
  return (library.tracksBySource[selectedSource.value] ?? []).map((track) => ({
    ...track,
    sourceId: selectedSource.value as number,
  }))
})

const visibleTracks = computed(() =>
  activeTracks.value.filter((track) => {
    if (statusFilter.value === 'all') return !HIDDEN_FROM_ALL.has(track.status)
    return track.status === statusFilter.value
  }),
)

const contextLabel = computed(() =>
  selectedSource.value === null
    ? t('library.allSources')
    : (library.sources.find((s) => s.id === selectedSource.value)?.name ?? ''),
)

function selectSource(id: number | null) {
  selectedSource.value = id
  checked.value = new Set()
}

function toggle(id: number) {
  const next = new Set(checked.value)
  next.has(id) ? next.delete(id) : next.add(id)
  checked.value = next
}
const allChecked = computed(
  () => visibleTracks.value.length > 0 && visibleTracks.value.every((t) => checked.value.has(t.id)),
)
function toggleAll() {
  // select-all operates over the FILTERED rows only (SPEC-DESIGN §9).
  checked.value = allChecked.value ? new Set() : new Set(visibleTracks.value.map((t) => t.id))
}

const checkedSourceIds = computed(() => {
  const ids = new Set<number>()
  visibleTracks.value.forEach((track) => {
    if (checked.value.has(track.id)) ids.add(track.sourceId)
  })
  return [...ids]
})

function confChip(track: LibraryTrack): string | null {
  return track.confidence !== null && track.confidence > 0 ? `${track.confidence}` : null
}

async function ignore(track: LibraryTrack & { sourceId: number }) {
  const updated = await api.post<LibraryTrack>(`/api/library/tracks/${track.id}/ignore`)
  library.replaceTrack(track.sourceId, updated)
  pushReviewCount()
}
async function restore(track: LibraryTrack & { sourceId: number }) {
  const updated = await api.post<LibraryTrack>(`/api/library/tracks/${track.id}/restore`)
  library.replaceTrack(track.sourceId, updated)
  pushReviewCount()
}

function onMatched(sourceId: number, updated: LibraryTrack) {
  library.replaceTrack(sourceId, updated)
  pushReviewCount()
}

async function syncAll() {
  try {
    await api.post('/api/sources/sync')
    await library.loadSources()
    pushReviewCount()
  } catch (err) {
    if (err instanceof ApiError && err.code === 'spotify_api_error' && err.body.status_code === 404)
      error.value = 'spotify_404'
  }
}

async function reconnectSpotify() {
  const { url } = await api.get<{ url: string }>('/api/spotify/authorize')
  await openExternal(url)
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

    <LoadingState v-if="loading" :rows="6" />

    <ErrorState
      v-else-if="error === 'spotify_404'"
      :title="t('library.error.privateTitle')"
      :body="t('library.error.privateBody')"
    >
      <button class="btn-ghost" @click="load">{{ t('common.retry') }}</button>
      <button class="btn-primary" @click="reconnectSpotify">{{ t('library.error.connect') }}</button>
    </ErrorState>

    <section v-else-if="!settings.configured" class="card unconfigured">
      <h3>{{ t('dashboard.unconfigured.title') }}</h3>
      <p>{{ t('dashboard.unconfigured.body') }}</p>
      <router-link to="/settings" class="btn-primary">{{ t('nav.settings') }}</router-link>
    </section>

    <EmptyState
      v-else-if="!library.sources.length"
      icon="≡"
      :title="t('library.empty.title')"
      :body="t('library.empty.body')"
    >
      <button class="btn-primary" @click="showAddSource = true">
        {{ t('library.empty.add') }}
      </button>
    </EmptyState>

    <div v-else class="grid">
      <!-- LEFT: source master list -->
      <aside class="master">
        <div class="master-head">
          <div class="master-title">
            <span>{{ t('library.sources') }}</span>
            <span class="mono count">{{ filteredSources.length }}</span>
            <button class="add-btn" :title="t('library.addSource.title')" @click="showAddSource = true">
              +
            </button>
          </div>
          <div class="master-search">
            <span>⌕</span>
            <input v-model="search" :placeholder="t('library.filterPlaylists')" />
          </div>
        </div>
        <div class="master-list">
          <div class="src-row" :data-active="selectedSource === null" @click="selectSource(null)">
            <div class="src-cover all">≡</div>
            <div class="src-text">
              <div class="src-name">{{ t('library.allSources') }}</div>
              <div class="mono src-sub">
                {{ library.sources.reduce((s, x) => s + library.reviewCountOf(x.id), 0) }}
                {{ t('library.toReview') }}
              </div>
            </div>
          </div>
          <div class="divider" />
          <div
            v-for="source in filteredSources"
            :key="source.id"
            class="src-row"
            :data-active="selectedSource === source.id"
            @click="selectSource(source.id)"
          >
            <div class="src-cover">{{ (source.name || '?')[0] }}</div>
            <div class="src-text">
              <div class="src-name">{{ source.name || source.spotify_playlist_id }}</div>
              <div class="mono src-sub">
                {{ (library.tracksBySource[source.id] ?? []).length }} {{ t('library.addSource.tracks') }}
              </div>
            </div>
            <span v-if="library.reviewCountOf(source.id) > 0" class="review-badge">{{
              library.reviewCountOf(source.id)
            }}</span>
          </div>
        </div>
      </aside>

      <!-- RIGHT: review surface -->
      <div class="review">
        <div class="review-head">
          <h2>{{ contextLabel }}</h2>
          <span class="ctx-sub">{{ visibleTracks.length }} {{ t('library.shown') }}</span>
          <button v-if="selectedSource !== null" class="btn-link" @click="selectSource(null)">
            ↩ {{ t('library.allSources') }}
          </button>
        </div>

        <div class="filters">
          <button
            v-for="filter in FILTERS"
            :key="filter"
            class="chip-btn"
            :data-active="statusFilter === filter"
            @click="statusFilter = filter"
          >
            {{ filter === 'all' ? t('library.filterAll') : t(`status.${filter}`) }}
          </button>
          <span class="spacer" />
          <div v-if="checked.size" class="bulk-bar">
            <span class="bulk-count"><span class="mono">{{ checked.size }}</span> {{ t('library.selected') }}</span>
            <button class="bulk-edit" @click="showTagPicker = true">{{ t('library.editTags') }}</button>
            <button class="bulk-clear" @click="checked = new Set()">✕</button>
          </div>
          <span v-else class="bulk-hint">{{ t('library.bulkHint') }}</span>
        </div>

        <div class="table">
          <div class="thead">
            <span class="cb"><input type="checkbox" :checked="allChecked" @change="toggleAll" /></span>
            <span class="col-title">{{ t('library.colTitle') }}</span>
            <span class="col-status">{{ t('library.colStatus') }}</span>
            <span class="col-action" />
          </div>
          <div class="tbody">
            <div v-for="track in visibleTracks" :key="track.id" class="trow">
              <span class="cb"
                ><input type="checkbox" :checked="checked.has(track.id)" @change="toggle(track.id)"
              /></span>
              <div class="tcell">
                <div class="ttitle">{{ track.title }}</div>
                <div class="tmeta">
                  <span class="tartist">{{ track.artist }}</span>
                  <template v-if="confChip(track)"
                    ><span class="dot">·</span
                    ><span class="conf-chip">{{ confChip(track) }}</span></template
                  >
                </div>
              </div>
              <span class="col-status"><StatusBadge :status="track.status" /></span>
              <span class="col-action">
                <button
                  v-if="track.status === 'missing'"
                  class="row-btn"
                  :title="t('library.action.purchase')"
                  @click="router.push('/missing/library')"
                >
                  ↓
                </button>
                <button
                  v-else-if="track.status === 'ignored'"
                  class="row-btn"
                  :title="t('library.action.restore')"
                  @click="restore(track)"
                >
                  ↩
                </button>
                <button
                  v-else-if="['conflict', 'new'].includes(track.status)"
                  class="row-btn"
                  :title="t('library.action.rematch')"
                  @click="rematchTrack = track"
                >
                  ⟳
                </button>
                <button
                  v-if="!['ignored', 'removed_from_source', 'imported'].includes(track.status)"
                  class="row-btn subtle"
                  :title="t('library.action.ignore')"
                  @click="ignore(track)"
                >
                  ⊘
                </button>
              </span>
            </div>
            <div v-if="!visibleTracks.length" class="table-empty">
              <div class="empty-glyph">✓</div>
              <div class="empty-title">{{ t('library.tableEmpty.title') }}</div>
              <p>{{ t('library.tableEmpty.body') }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <AddSourceModal
      v-if="showAddSource"
      @close="showAddSource = false"
      @added="(id) => { selectSource(id); pushReviewCount() }"
    />
    <ReMatchModal
      v-if="rematchTrack"
      :track="rematchTrack"
      @close="rematchTrack = null"
      @matched="(updated) => onMatched(rematchTrack!.sourceId, updated)"
    />
    <TagPickerModal
      v-if="showTagPicker"
      :track-ids="[...checked]"
      :source-ids="checkedSourceIds"
      @close="showTagPicker = false"
      @applied="checked = new Set()"
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
.btn-secondary {
  background: #14171f;
  border: 1px solid #2a3140;
  color: var(--text-secondary-bright);
  padding: 9px 15px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 7px;
  white-space: nowrap;
  flex: none;
}
.btn-secondary:disabled {
  opacity: 0.55;
  cursor: default;
}
.btn-icon {
  color: var(--accent);
}
.grid {
  display: grid;
  grid-template-columns: 288px minmax(0, 1fr);
  gap: 20px;
  flex: 1;
  min-height: 0;
}
.master {
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 13px;
  overflow: clip;
}
.master-head {
  padding: 13px 14px 11px;
  border-bottom: 1px solid var(--border-subtle-2);
  flex: none;
}
.master-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
}
.count {
  font-size: 11px;
  color: var(--text-muted-bright);
  background: #12151d;
  border: 1px solid var(--border-2);
  border-radius: 6px;
  padding: 1px 7px;
}
.add-btn {
  margin-left: auto;
  background: var(--accent-tint);
  border: 1px solid var(--accent-border);
  color: var(--accent-hover);
  width: 26px;
  height: 26px;
  border-radius: 7px;
  font-size: 16px;
  cursor: pointer;
}
.master-search {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 8px;
  padding: 6px 10px;
  color: var(--text-muted);
}
.master-search input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-secondary-bright);
  font-family: inherit;
  font-size: 12.5px;
}
.master-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.src-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  border-radius: 8px;
  cursor: pointer;
}
.src-row:hover {
  background: #141823;
}
.src-row[data-active='true'] {
  background: var(--accent-tint);
}
.src-cover {
  width: 30px;
  height: 30px;
  flex: none;
  border-radius: 7px;
  background: linear-gradient(135deg, #1db954, var(--teal));
  display: grid;
  place-content: center;
  color: rgba(255, 255, 255, 0.9);
  font-size: 13px;
  font-weight: 700;
}
.src-cover.all {
  background: #171c27;
  border: 1px solid #232a38;
  color: #8b97a9;
}
.src-text {
  flex: 1;
  min-width: 0;
}
.src-name {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.src-sub {
  font-size: 11px;
  color: var(--text-muted);
}
.review-badge {
  font-family: var(--font-mono);
  font-size: var(--size-meta);
  background: var(--warning-tint);
  border: 1px solid var(--warning-border);
  color: var(--warning-text);
  border-radius: 6px;
  padding: 1px 6px;
}
.divider {
  height: 1px;
  background: #161b26;
  margin: 5px 2px;
}
.review {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.review-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 13px;
  flex: none;
}
.review-head h2 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ctx-sub {
  font-size: 12px;
  color: var(--text-muted);
}
.btn-link {
  margin-left: auto;
  background: transparent;
  border: none;
  color: var(--text-muted-bright);
  font-size: 12px;
  cursor: pointer;
}
.filters {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  flex-wrap: wrap;
  flex: none;
}
.chip-btn {
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  color: var(--text-secondary);
  padding: 5px 11px;
  border-radius: 7px;
  font-size: 12px;
  cursor: pointer;
}
.chip-btn[data-active='true'] {
  background: var(--accent-tint);
  border-color: var(--accent-border);
  color: var(--accent-hover);
}
.spacer {
  flex: 1;
}
.bulk-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--accent-tint);
  border: 1px solid var(--accent-border);
  border-radius: 9px;
  padding: 5px 6px 5px 12px;
}
.bulk-count {
  font-size: 12px;
  color: var(--accent-hover);
  font-weight: 600;
}
.bulk-edit {
  background: var(--accent-tint);
  color: var(--accent-hover);
  border: 1px solid var(--accent-border);
  padding: 4px 11px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.bulk-clear {
  background: transparent;
  color: var(--text-muted-bright);
  border: none;
  font-size: 12px;
  cursor: pointer;
}
.bulk-hint {
  font-size: 12px;
  color: var(--text-muted);
}
.table {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 13px;
  overflow: clip;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.thead {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 18px;
  border-bottom: 1px solid var(--border-subtle-2);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  font-weight: 600;
  flex: none;
}
.cb {
  width: 16px;
  display: flex;
}
.cb input {
  accent-color: var(--accent);
  cursor: pointer;
}
.col-title {
  flex: 1;
}
.col-status {
  flex: none;
}
.col-action {
  width: 62px;
  display: flex;
  gap: 4px;
  justify-content: flex-end;
  flex: none;
}
.tbody {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.trow {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: var(--row-padding-y) 18px;
  border-bottom: 1px solid var(--border-subtle);
}
.trow:hover {
  background: #0f131b;
}
.tcell {
  flex: 1;
  min-width: 0;
}
.ttitle {
  font-size: 13.5px;
  font-weight: 500;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tmeta {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 2px;
  font-size: 11.5px;
  min-width: 0;
}
.tartist {
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
.conf-chip {
  font-family: var(--font-mono);
  color: var(--text-muted-bright);
  flex: none;
}
.row-btn {
  width: 26px;
  height: 26px;
  border-radius: 7px;
  border: 1px solid var(--border-2);
  background: var(--surface-raised);
  color: var(--text-secondary-bright);
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
}
.row-btn.subtle {
  color: var(--text-muted);
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
.table-empty p {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}
.mono {
  font-family: var(--font-mono);
}
.card {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 18px;
}
.unconfigured {
  text-align: center;
}
.unconfigured p {
  color: var(--text-secondary);
  margin: 8px 0 16px;
}
.btn-ghost {
  background: #14171f;
  border: 1px solid #2a3140;
  color: var(--text-secondary);
  padding: 9px 16px;
  border-radius: 9px;
  font-size: 13px;
  cursor: pointer;
}
.btn-primary {
  background: var(--accent);
  border: none;
  color: #06131f;
  padding: 9px 18px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  display: inline-block;
}
</style>
