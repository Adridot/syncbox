<script setup lang="ts">
// Untagged (§5.8): 4 categories sorted junk < dup < alt < review, selection
// bound to the VISIBLE filter (never hidden rows — the exact regression §9
// calls out), D15 delete with the REAL skip report, and the minimal D7
// junk-pattern editor (list / add / delete a regex). Removal is always a
// reversible Rekordbox row soft-delete and never touches audio.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../../api/client'
import type { UntaggedTrack } from '../../api/types'
import ErrorState from '../../components/ErrorState.vue'
import LoadingState from '../../components/LoadingState.vue'
import SelectionBar from '../../components/SelectionBar.vue'
import { useRefreshOnReturn } from '../../lib/refresh'
import { useHealthStore } from '../../stores/health'
import { useJobsStore } from '../../stores/jobs'
import { useStatusStore } from '../../stores/status'

const { t } = useI18n()
const health = useHealthStore()
const status = useStatusStore()
const jobs = useJobsStore()

const CATEGORIES = ['all', 'junk', 'dup_of_tagged', 'alt_version', 'review'] as const
type Category = (typeof CATEGORIES)[number]

const tracks = ref<UntaggedTrack[] | null>(null)
const loadError = ref<string | null>(null)
const filter = ref<Category>('all')
const selection = ref<Set<string>>(new Set())
const banner = ref<{ tone: 'error' | 'success'; text: string } | null>(null)

const patterns = ref<Array<{ id: number; pattern: string }>>([])
const newPattern = ref('')
const patternError = ref<string | null>(null)

function describe(cause: unknown): string {
  return cause instanceof ApiError ? cause.message : t('common.networkError')
}

async function load() {
  loadError.value = null
  try {
    const [list, pats] = await Promise.all([
      api.get<{ tracks: UntaggedTrack[] }>('/api/untagged'),
      api.get<{ patterns: Array<{ id: number; pattern: string }> }>('/api/untagged/patterns'),
    ])
    tracks.value = list.tracks
    patterns.value = pats.patterns
    health.setUntaggedCount(list.tracks.length)
  } catch (cause) {
    loadError.value = describe(cause)
  }
}
// skeleton on first load only; keep-alive re-entries refresh silently
useRefreshOnReturn(() => void load())

const visible = computed(() =>
  filter.value === 'all'
    ? (tracks.value ?? [])
    : (tracks.value ?? []).filter((track) => track.category === filter.value),
)
const countOf = computed(() => {
  const counts: Record<string, number> = { all: tracks.value?.length ?? 0 }
  for (const track of tracks.value ?? [])
    counts[track.category] = (counts[track.category] ?? 0) + 1
  return counts
})

// selection is bound to the visible filter: switching filters clears it
watch(filter, () => {
  selection.value = new Set()
})

const allVisibleSelected = computed(
  () =>
    visible.value.length > 0 &&
    visible.value.every((track) => selection.value.has(track.content_id)),
)
function toggleAll() {
  const next = new Set(selection.value)
  if (allVisibleSelected.value) visible.value.forEach((track) => next.delete(track.content_id))
  else visible.value.forEach((track) => next.add(track.content_id))
  selection.value = next
}
function toggleOne(id: string) {
  const next = new Set(selection.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selection.value = next
}

async function deleteSelection() {
  banner.value = null
  try {
    const result = await api.post<{
      soft_deleted: string[]
      skipped: Array<{ content_id: string; reason: string }>
    }>('/api/untagged/delete', { content_ids: [...selection.value] })
    // The skip report is exact: stale tagged/not-found rows are named.
    const skippedText = result.skipped.length
      ? ' · ' +
        t('untagged.skipped', result.skipped.length) +
        ' (' +
        result.skipped.map((skip) => t(`untagged.skipReason.${skip.reason}`, skip.reason)).join(', ') +
        ')'
      : ''
    banner.value = {
      tone: result.skipped.length ? 'error' : 'success',
      text: t('untagged.deleted', result.soft_deleted.length) + skippedText,
    }
    selection.value = new Set()
    await load()
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
  }
}

async function addPattern() {
  patternError.value = null
  if (!newPattern.value.trim()) return
  try {
    await api.post('/api/untagged/patterns', { pattern: newPattern.value.trim() })
    newPattern.value = ''
    await load()
  } catch (cause) {
    patternError.value = describe(cause) // invalid regex -> 400, surfaced
  }
}

async function removePattern(id: number) {
  patternError.value = null
  try {
    await api.delete(`/api/untagged/patterns/${id}`)
    await load()
  } catch (cause) {
    patternError.value = describe(cause)
  }
}
</script>

<template>
  <div>
    <i18n-t tag="p" class="intro" keypath="untagged.intro">
      <template #junk><span class="cat-junk">junk</span></template>
      <template #dup><span class="cat-dup">{{ t('untagged.cat.dup_of_tagged') }}</span></template>
      <template #alt><span class="cat-alt">{{ t('untagged.cat.alt_version') }}</span></template>
      <template #review><span class="cat-review">{{ t('untagged.cat.review') }}</span></template>
    </i18n-t>

    <LoadingState v-if="tracks === null && !loadError" :rows="5" />
    <ErrorState v-else-if="loadError" :title="t('untagged.loadErrorTitle')" :body="loadError">
      <button class="btn-secondary" @click="load">{{ t('common.retry') }}</button>
    </ErrorState>

    <template v-else>
      <div class="toolbar">
        <button
          v-for="category in CATEGORIES"
          :key="category"
          class="chip"
          :data-active="filter === category"
          @click="filter = category"
        >
          {{ category === 'all' ? t('untagged.cat.all') : t(`untagged.cat.${category}`) }}
          <span class="chip-n mono">{{ countOf[category] ?? 0 }}</span>
        </button>
      </div>

      <div v-if="banner" class="banner" :data-tone="banner.tone" role="status">
        <span class="banner-text">{{ banner.text }}</span>
        <button class="banner-close" @click="banner = null">✕</button>
      </div>

      <div class="table">
        <div class="table-head">
          <span class="cell-check">
            <input
              type="checkbox"
              :checked="allVisibleSelected"
              :aria-label="t('untagged.selectAll')"
              @change="toggleAll"
            />
          </span>
          <span class="head-label">{{ t('untagged.selectAll') }}</span>
        </div>
        <div v-for="track in visible" :key="track.content_id" class="row">
          <span class="cell-check">
            <input
              type="checkbox"
              :checked="selection.has(track.content_id)"
              :aria-label="track.title ?? ''"
              @change="toggleOne(track.content_id)"
            />
          </span>
          <div class="row-text">
            <div class="row-title mono">{{ track.title || t('missing.untitled') }}</div>
            <div class="row-artist">{{ track.artist }}</div>
          </div>
          <span class="ownership-chip" :data-ownership="track.ownership">{{
            t(`ownership.${track.ownership}`)
          }}</span>
          <span class="cat-badge" :data-cat="track.category">{{
            t(`untagged.cat.${track.category}`)
          }}</span>
        </div>
        <div v-if="!visible.length" class="table-empty">{{ t('untagged.empty') }}</div>
      </div>

      <!-- floating pill: the table never shifts when a selection starts -->
      <div class="sel-float-anchor">
        <SelectionBar :count="selection.size" @clear="selection = new Set()">
          <button
            class="delete-sel"
            :disabled="status.rbOpen || jobs.jobRunning"
            @click="deleteSelection"
          >
            {{ status.rbOpen ? t('rbGuard.blocked') : t('untagged.deleteSelection') }}
          </button>
        </SelectionBar>
      </div>

      <!-- D7 minimal junk-pattern editor -->
      <details class="patterns">
        <summary>{{ t('untagged.patterns.title', { n: patterns.length }) }}</summary>
        <p class="patterns-help">{{ t('untagged.patterns.help') }}</p>
        <div class="pattern-add">
          <input
            v-model="newPattern"
            type="text"
            class="mono"
            :placeholder="t('untagged.patterns.placeholder')"
            @keydown.enter.prevent="addPattern"
          />
          <button class="btn-secondary small" @click="addPattern">
            {{ t('untagged.patterns.add') }}
          </button>
        </div>
        <div v-if="patternError" class="pattern-error">{{ patternError }}</div>
        <div v-for="pattern in patterns" :key="pattern.id" class="pattern-row">
          <span class="mono pattern-text">{{ pattern.pattern }}</span>
          <button class="pattern-remove" @click="removePattern(pattern.id)">✕</button>
        </div>
      </details>
    </template>
  </div>
</template>

<style scoped>
.intro {
  font-size: 12.5px;
  color: var(--text-muted-bright);
  margin: 0 0 13px;
}
.cat-junk {
  color: var(--danger);
}
.cat-dup {
  color: var(--uncertain);
}
.cat-alt {
  color: var(--accent);
}
.cat-review {
  color: var(--text-secondary);
}
.toolbar {
  display: flex;
  gap: 7px;
  margin-bottom: 12px;
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
  background: #12151d;
  border: 1px solid var(--border-2);
}
.chip[data-active='true'] {
  color: var(--text-primary);
  background: rgba(77, 163, 255, 0.14);
  border-color: var(--accent-border);
}
.chip-n {
  font-size: var(--size-meta);
  color: var(--text-muted);
}
.banner {
  display: flex;
  align-items: center;
  gap: 10px;
  border-radius: 9px;
  padding: 9px 12px;
  margin-bottom: 12px;
  font-size: 12.5px;
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
}
.banner-close {
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
}
.table {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  overflow: clip;
}
.table-head {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 9px 18px;
  border-bottom: 1px solid var(--border-subtle-2);
  min-height: 38px;
  box-sizing: border-box;
}
.head-label {
  font-size: var(--size-meta);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  font-weight: 600;
}
.sel-float-anchor {
  position: sticky;
  bottom: 16px;
  display: flex;
  justify-content: center;
  z-index: 6;
}
.sel-float-anchor:not(:empty) {
  margin-top: 12px;
}
.delete-sel {
  background: rgba(247, 110, 110, 0.12);
  border: 1px solid rgba(247, 110, 110, 0.28);
  color: var(--danger-text);
  padding: 5px 11px;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.delete-sel:disabled {
  opacity: 0.55;
  cursor: default;
}
.cell-check {
  width: 26px;
  display: flex;
  align-items: center;
  flex: none;
  align-self: stretch; /* the whole cell height stays clickable */
}
.row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 11px 18px;
  border-bottom: 1px solid var(--border-subtle);
}
.row-text {
  flex: 1;
  min-width: 0;
}
.row-title {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.row-artist {
  font-size: 12px;
  color: var(--text-muted-bright);
}
.mono {
  font-family: var(--font-mono);
}
.ownership-chip {
  color: var(--text-muted-bright);
  font-size: var(--size-meta);
  white-space: nowrap;
}
.cat-badge {
  font-size: var(--size-meta);
  font-weight: 600;
  border-radius: 7px;
  padding: 2.5px 8px;
  white-space: nowrap;
}
.cat-badge[data-cat='junk'] {
  background: var(--danger-tint);
  border: 1px solid var(--danger-border);
  color: var(--danger-text);
}
.cat-badge[data-cat='dup_of_tagged'] {
  background: var(--uncertain-tint);
  border: 1px solid var(--uncertain-border);
  color: var(--uncertain);
}
.cat-badge[data-cat='alt_version'] {
  background: var(--accent-tint);
  border: 1px solid var(--accent-border);
  color: var(--accent-hover);
}
.cat-badge[data-cat='review'] {
  background: var(--neutral-tint);
  border: 1px solid var(--neutral-border);
  color: var(--text-secondary-bright);
}
.table-empty {
  padding: 34px;
  text-align: center;
  font-size: 12.5px;
  color: var(--text-muted);
}
.patterns {
  margin-top: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-inner);
  padding: 12px 14px;
}
.patterns summary {
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  color: var(--text-secondary-bright);
}
.patterns-help {
  font-size: 12px;
  color: var(--text-muted-bright);
  margin: 9px 0 10px;
  line-height: 1.5;
}
.pattern-add {
  display: flex;
  gap: 8px;
}
.pattern-add input {
  flex: 1;
  background: var(--surface-raised);
  border: 1px solid #2a3140;
  border-radius: 8px;
  padding: 7px 11px;
  color: var(--text-secondary-bright);
  font-size: 12.5px;
  outline: none;
}
.btn-secondary.small {
  padding: 6px 11px;
  font-size: 12px;
}
.pattern-error {
  margin-top: 8px;
  font-size: 12px;
  color: var(--danger-text);
}
.pattern-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 2px;
  border-bottom: 1px solid var(--border-subtle);
}
.pattern-row:last-child {
  border-bottom: none;
}
.pattern-text {
  flex: 1;
  font-size: 12.5px;
  color: var(--text-secondary-bright);
}
.pattern-remove {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 13px;
}
.pattern-remove:hover {
  color: var(--danger-text);
}
</style>
