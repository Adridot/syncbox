<script setup lang="ts">
// Events (SPEC-DESIGN §2, SPEC-UNIFIED §5.7/§11.2): event cards (lifecycle
// badges, pending "+N", ready/missing counters) + workspace (segmented
// progress bar from real counts, filters with counts, AddTrackByLink
// Spotify-only, match/claim, "Modifié" banner, rename pending-only) +
// Apply/Reapply/Delete modals (previews from real payloads, RB-guarded CTAs).
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../api/client'
import ApplyEventModal from '../components/ApplyEventModal.vue'
import DeleteEventModal from '../components/DeleteEventModal.vue'
import EmptyState from '../components/EmptyState.vue'
import GuardedButton from '../components/GuardedButton.vue'
import LoadingState from '../components/LoadingState.vue'
import NewEventModal from '../components/NewEventModal.vue'
import ReapplyEventModal from '../components/ReapplyEventModal.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { extractTrackId } from '../lib/spotify-link'
import { useEventsStore, type EventTrack } from '../stores/events'
import { useHealthStore } from '../stores/health'
import { useSettingsStore } from '../stores/settings'

const { t } = useI18n()
const events = useEventsStore()
const health = useHealthStore()
const settings = useSettingsStore()

const loading = ref(true)
const showNew = ref(false)
const showApply = ref(false)
const showReapply = ref(false)
const showDelete = ref(false)
const trackFilter = ref('all')
const link = ref('')
const adding = ref(false)
const linkError = ref<string | null>(null)
const renaming = ref(false)
const renameValue = ref('')

const FILTERS = ['all', 'ready', 'missing', 'pending']

onMounted(load)

async function load() {
  loading.value = true
  if (!settings.loaded) await settings.load()
  if (!settings.configured) {
    loading.value = false
    return
  }
  await events.loadEvents()
  if (events.events.length && !events.current) await select(events.events[0].id)
  pushAttention()
  loading.value = false
}

function pushAttention() {
  // events needing attention = pending delta or ready-to-apply
  const count = events.events.filter(
    (e) => e.pending_delta > 0 || e.status === 'pending',
  ).length
  health.setEventsAttentionCount(count)
}

async function select(id: number) {
  await events.loadEvent(id)
  trackFilter.value = 'all'
}

const visibleTracks = computed<EventTrack[]>(() => {
  const tracks = events.current?.tracks ?? []
  if (trackFilter.value === 'all') return tracks
  if (trackFilter.value === 'pending') return tracks.filter((tk) => tk.added_after_apply === 1)
  if (trackFilter.value === 'ready')
    return tracks.filter((tk) => tk.status === 'ready' || tk.status === 'imported')
  return tracks.filter((tk) => tk.status === trackFilter.value)
})

// pending tracks sort to the TOP (staged, §11.2)
const sortedTracks = computed(() =>
  [...visibleTracks.value].sort((a, b) => b.added_after_apply - a.added_after_apply),
)

const barSegments = computed(() => {
  const { ready, missing, pending, total } = events.counts
  if (!total) return { ready: 0, missing: 0, pending: 0 }
  return {
    ready: (ready / total) * 100,
    missing: (missing / total) * 100,
    pending: (pending / total) * 100,
  }
})

function filterCount(filter: string): number {
  const c = events.counts
  if (filter === 'ready') return c.ready
  if (filter === 'missing') return c.missing
  if (filter === 'pending') return c.pending
  return c.total
}

async function addTrack() {
  const id = extractTrackId(link.value)
  if (!id || !events.current) {
    linkError.value = t('events.workspace.badLink')
    return
  }
  adding.value = true
  linkError.value = null
  try {
    await api.post(`/api/events/${events.current.id}/tracks`, { spotify_track_id: id })
    await api.post(`/api/events/${events.current.id}/match`)
    await events.reload()
    pushAttention()
    link.value = ''
  } catch (err) {
    linkError.value = err instanceof ApiError ? err.message : t('events.workspace.addFailed')
  } finally {
    adding.value = false
  }
}

async function matchAll() {
  if (!events.current) return
  await api.post(`/api/events/${events.current.id}/match`)
  await events.reload()
}
async function claimReady() {
  if (!events.current) return
  await api.post(`/api/events/${events.current.id}/claim`)
  await events.reload()
}

function startRename() {
  if (!events.current || events.current.status !== 'pending') return
  renameValue.value = events.current.name
  renaming.value = true
}
async function commitRename() {
  if (!events.current) return
  const name = renameValue.value.trim()
  if (name && name !== events.current.name) {
    await api.patch(`/api/events/${events.current.id}`, { name })
    await events.reload()
  }
  renaming.value = false
}

function confColor(track: EventTrack): string {
  if (track.confidence === null) return 'var(--text-muted)'
  if (track.confidence >= 82) return 'var(--accent)'
  if (track.confidence >= 60) return 'var(--warning-text)'
  return 'var(--text-muted-bright)'
}

function openPrimary() {
  events.isReapply ? (showReapply.value = true) : (showApply.value = true)
}
</script>

<template>
  <main class="screen">
    <header class="head">
      <div>
        <h1>{{ t('nav.events') }}</h1>
        <p class="tagline">{{ t('events.tagline') }}</p>
      </div>
      <button class="btn-primary" @click="showNew = true">{{ t('events.new.button') }}</button>
    </header>

    <LoadingState v-if="loading" :rows="4" />

    <section v-else-if="!settings.configured" class="card unconfigured">
      <h3>{{ t('dashboard.unconfigured.title') }}</h3>
      <p>{{ t('dashboard.unconfigured.body') }}</p>
      <router-link to="/settings" class="btn-primary">{{ t('nav.settings') }}</router-link>
    </section>

    <EmptyState
      v-else-if="!events.events.length"
      icon="◆"
      :title="t('events.empty.title')"
      :body="t('events.empty.body')"
    >
      <button class="btn-primary" @click="showNew = true">{{ t('events.new.button') }}</button>
    </EmptyState>

    <template v-else>
      <!-- event cards -->
      <div class="cards">
        <div
          v-for="event in events.events"
          :key="event.id"
          class="event-card"
          :data-active="events.current?.id === event.id"
          @click="select(event.id)"
        >
          <div class="card-top">
            <div class="card-name">{{ event.name }}</div>
            <span v-if="event.pending_delta > 0" class="pend-badge"
              >+{{ event.pending_delta }} {{ t('events.pending') }}</span
            >
          </div>
          <div class="card-badge"><StatusBadge :status="event.status" /></div>
          <div class="card-counters">
            <span class="mono">{{ event.n_tracks }}</span> {{ t('events.card.tracks') }}
          </div>
        </div>
      </div>

      <!-- workspace -->
      <div v-if="events.current" class="workspace">
        <div class="ws-head">
          <div class="ws-title">
            <template v-if="!renaming">
              <span class="ws-name">{{ events.current.name }}</span>
              <button
                v-if="events.current.status === 'pending'"
                class="rename-btn"
                :title="t('events.workspace.rename')"
                @click="startRename"
              >
                ✎
              </button>
            </template>
            <input
              v-else
              v-model="renameValue"
              class="rename-input"
              @keydown.enter="commitRename"
              @blur="commitRename"
            />
            <StatusBadge :status="events.current.status" />
          </div>
          <div class="ws-actions">
            <GuardedButton :label="t('events.workspace.delete')" tone="danger" @click="showDelete = true" />
            <GuardedButton
              :label="events.isReapply ? t('events.workspace.reapply', { n: events.current.pending_delta }) : t('events.workspace.apply')"
              tone="primary"
              @click="openPrimary"
            />
          </div>
        </div>

        <!-- segmented progress bar (real counts) -->
        <div class="ws-progress">
          <div class="bar">
            <div class="seg ready" :style="{ width: `${barSegments.ready}%` }" />
            <div class="seg missing" :style="{ width: `${barSegments.missing}%` }" />
            <div class="seg pending" :style="{ width: `${barSegments.pending}%` }" />
          </div>
          <div class="legend">
            <span class="leg"><i class="sw ready" /><span class="mono">{{ events.counts.ready }}</span> {{ t('events.legend.ready') }}</span>
            <span class="leg"><i class="sw missing" /><span class="mono">{{ events.counts.missing }}</span> {{ t('events.legend.missing') }}</span>
            <span v-if="events.counts.pending" class="leg"><i class="sw pending" /><span class="mono">{{ events.counts.pending }}</span> {{ t('events.legend.pending') }}</span>
            <span class="spacer" />
            <span class="total"><span class="mono">{{ events.counts.total }}</span> {{ t('events.legend.total') }}</span>
          </div>
        </div>

        <!-- Modifié banner (§11.2) -->
        <div v-if="events.counts.pending > 0 && events.hasPriorApply" class="modified-banner">
          <span>⚠</span>
          <span
            >{{ t('events.modifiedBanner', { n: events.counts.pending }) }}</span
          >
        </div>

        <!-- add track by link (Spotify-only) -->
        <div class="add-row">
          <div class="add-field">
            <span>🔗</span>
            <input
              v-model="link"
              :placeholder="t('events.workspace.linkPlaceholder')"
              @keydown.enter="addTrack"
            />
          </div>
          <button class="btn-accent" :disabled="adding" @click="addTrack">
            {{ adding ? t('events.workspace.resolving') : t('events.workspace.add') }}
          </button>
        </div>
        <div v-if="linkError" class="link-error">{{ linkError }}</div>

        <!-- filters + secondary actions -->
        <div class="ws-filters">
          <button
            v-for="filter in FILTERS"
            :key="filter"
            class="chip-btn"
            :data-active="trackFilter === filter"
            @click="trackFilter = filter"
          >
            {{ filter === 'all' ? t('library.filterAll') : t(`events.legend.${filter}`) }}
            <span class="chip-n">{{ filterCount(filter) }}</span>
          </button>
          <span class="spacer" />
          <button class="btn-ghost sm" @click="matchAll">{{ t('events.workspace.rematchAll') }}</button>
          <button class="btn-ghost sm" @click="claimReady">{{ t('events.workspace.claim') }}</button>
        </div>

        <!-- track table -->
        <div class="track-table">
          <div v-for="track in sortedTracks" :key="track.id" class="track-row">
            <div class="tk-text">
              <div class="tk-title">
                <span>{{ track.title }}</span>
                <span v-if="track.added_after_apply === 1" class="added-tag">{{ t('events.added') }}</span>
              </div>
              <div class="tk-artist">{{ track.artist }}</div>
            </div>
            <span class="tk-status"><StatusBadge :status="track.status" /></span>
            <span class="tk-conf mono" :style="{ color: confColor(track) }">{{
              track.confidence ?? '—'
            }}</span>
          </div>
          <div v-if="!sortedTracks.length" class="tbl-empty">{{ t('events.workspace.emptyFilter') }}</div>
        </div>
      </div>
    </template>

    <NewEventModal v-if="showNew" @close="showNew = false" @created="select" />
    <ApplyEventModal v-if="showApply" @close="showApply = false" @applied="pushAttention" />
    <ReapplyEventModal v-if="showReapply" @close="showReapply = false" @applied="pushAttention" />
    <DeleteEventModal
      v-if="showDelete"
      @close="showDelete = false"
      @deleted="() => { events.current = null; load() }"
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
.event-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 13px;
  padding: 14px;
  cursor: pointer;
}
.event-card:hover {
  border-color: #2a3242;
}
.event-card[data-active='true'] {
  border-color: var(--accent-border);
  background: var(--accent-tint);
}
.card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.card-name {
  font-weight: 600;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pend-badge {
  flex: none;
  font-size: 10.5px;
  font-weight: 700;
  color: var(--warning-text);
  background: var(--warning-tint);
  border: 1px solid var(--warning-border);
  border-radius: 6px;
  padding: 2px 7px;
  white-space: nowrap;
}
.card-badge {
  margin-top: 11px;
}
.card-counters {
  margin-top: 12px;
  font-size: 12px;
  color: var(--text-muted);
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
  display: flex;
  align-items: center;
  gap: 10px;
}
.ws-name {
  font-weight: 600;
  font-size: 15px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rename-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 13px;
}
.rename-input {
  background: var(--surface-raised);
  border: 1px solid var(--accent-border);
  border-radius: 7px;
  padding: 5px 9px;
  color: var(--text-primary);
  font-family: inherit;
  font-size: 14px;
  outline: none;
}
.ws-actions {
  display: flex;
  gap: 8px;
  flex: none;
}
.ws-progress {
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
.mono {
  font-family: var(--font-mono);
  color: var(--text-secondary-bright);
}
.modified-banner {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 12px 18px;
  border-bottom: 1px solid var(--border-subtle-2);
  background: rgba(245, 181, 68, 0.07);
  font-size: 12.5px;
  color: var(--warning-text);
}
.add-row {
  display: flex;
  gap: 8px;
  padding: 12px 18px;
  border-bottom: 1px solid var(--border-subtle-2);
  background: #0a0d14;
}
.add-field {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface-raised);
  border: 1px solid #2a3140;
  border-radius: 8px;
  padding: 8px 12px;
  color: var(--text-muted);
  min-width: 0;
}
.add-field input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-secondary-bright);
  font-family: var(--font-mono);
  font-size: 12.5px;
}
.btn-accent {
  background: var(--accent);
  border: none;
  color: #06131f;
  padding: 8px 15px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  flex: none;
}
.btn-accent:disabled {
  opacity: 0.5;
  cursor: default;
}
.link-error {
  padding: 8px 18px 0;
  font-size: 12px;
  color: var(--danger-text);
}
.ws-filters {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 11px 18px;
  border-bottom: 1px solid var(--border-subtle-2);
  flex-wrap: wrap;
}
.chip-btn {
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  color: var(--text-secondary);
  padding: 5px 11px;
  border-radius: 7px;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}
.chip-btn[data-active='true'] {
  background: var(--accent-tint);
  border-color: var(--accent-border);
  color: var(--accent-hover);
}
.chip-n {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
}
.btn-ghost.sm {
  background: #14171f;
  border: 1px solid #2a3140;
  color: var(--text-secondary);
  padding: 5px 11px;
  border-radius: 7px;
  font-size: 12px;
  cursor: pointer;
}
.track-table {
  max-height: 420px;
  overflow-y: auto;
}
.track-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: var(--row-padding-y) 18px;
  border-bottom: 1px solid var(--border-subtle);
}
.tk-text {
  flex: 1;
  min-width: 0;
}
.tk-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  font-weight: 500;
}
.tk-title span:first-child {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.added-tag {
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
.tk-artist {
  font-size: 12px;
  color: var(--text-muted-bright);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tk-status {
  flex: none;
}
.tk-conf {
  width: 40px;
  text-align: right;
  font-size: 13px;
  flex: none;
}
.tbl-empty {
  padding: 34px;
  text-align: center;
  font-size: 12.5px;
  color: var(--text-muted);
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
.btn-primary {
  background: var(--accent);
  border: none;
  color: #06131f;
  padding: 9px 18px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  text-decoration: none;
  display: inline-block;
}
</style>
