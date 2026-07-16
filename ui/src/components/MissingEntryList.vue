<script setup lang="ts">
// Shared missing-entry list (M4.9 collection tab + M4.10 center):
// purchase-first legal path (§5.5/§5.13 — links open in the SYSTEM browser,
// the sidecar never contacts stores), manual relink, §5.5 status
// transitions with a D22 inline undo, and the G3 collection remove.
// Every action surfaces its outcome (B1). Optional acquisition appears only
// when the backend marks it available; purchase links remain first.
// Row layout (owner decision 15/07): checkbox selection + floating bulk bar
// for the groupable actions; per row only the buy CTA stays visible, the
// rest lives in a ⋯ menu.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api, requestConsent } from '../api/client'
import type { DeezerSearchResult, MissingEntry } from '../api/types'
import {
  acquisitionLabelKey,
  humanizeAcquisitionError,
  useAcquisitionQueue,
} from '../lib/acquisition'
import { openExternal } from '../shell'
import { useJobsStore } from '../stores/jobs'
import { useStatusStore } from '../stores/status'
import DeezerSearchPanel from './DeezerSearchPanel.vue'
import ManualRelinkModal from './ManualRelinkModal.vue'
import ScopeBadge from './ScopeBadge.vue'
import SelectionBar from './SelectionBar.vue'
import SpotifyAttributionLink from './SpotifyAttributionLink.vue'
import StatusBadge from './StatusBadge.vue'

const props = defineProps<{ entries: MissingEntry[]; showScope?: boolean }>()
const emit = defineEmits<{ changed: [] }>()
const { t } = useI18n()
const status = useStatusStore()
const jobs = useJobsStore()

const banner = ref<{ tone: 'error' | 'success'; text: string; undo?: MissingEntry[] } | null>(null)
const relinkEntry = ref<MissingEntry | null>(null)
const relinkBusy = ref(false)
const relinkError = ref<string | null>(null)
const purchaseMenu = ref<string | null>(null)
const rowMenu = ref<string | null>(null)

function describe(cause: unknown): string {
  return cause instanceof ApiError ? cause.message : t('common.networkError')
}

function entryKey(entry: MissingEntry): string {
  return `${entry.scope}:${String(entry.id)}`
}

// popovers close on any outside click; toggles stop propagation
function closeMenus() {
  purchaseMenu.value = null
  rowMenu.value = null
}
onMounted(() => document.addEventListener('click', closeMenus))
onUnmounted(() => document.removeEventListener('click', closeMenus))

function toggleRowMenu(entry: MissingEntry) {
  const key = entryKey(entry)
  rowMenu.value = rowMenu.value === key ? null : key
  purchaseMenu.value = null
}

// --- selection (bulk over the groupable actions — owner decision 15/07) ----
const selected = ref<Set<string>>(new Set())

// entries change (reload, resolve) — drop keys that no longer exist
watch(
  () => props.entries,
  (list) => {
    const keys = new Set(list.map(entryKey))
    const next = new Set([...selected.value].filter((key) => keys.has(key)))
    if (next.size !== selected.value.size) selected.value = next
    pruneAcq(keys)
  },
)

// --- Deezer acquisition: UI-driven queue, live badge per row + x/N counter -
const {
  states: acqStates,
  batch: acqBatch,
  running: acqRunning,
  run: runAcq,
  prune: pruneAcq,
} = useAcquisitionQueue()

// manual search (panel with 30 s preview); a pick downloads the chosen
// recording even when the row itself has no ISRC
const searchFor = ref<MissingEntry | null>(null)
const searchQuery = computed(() =>
  searchFor.value
    ? [searchFor.value.artist, searchFor.value.title].filter(Boolean).join(' ')
    : '',
)
const searchable = (entry: MissingEntry) =>
  Boolean(entry.acquisition?.available || entry.acquisition?.reason === 'missing_isrc')

function acquisitionBody(entry: MissingEntry, deezerTrackId?: number): Record<string, unknown> {
  return {
    scope: entry.scope,
    row_id: entry.scope === 'collection' ? undefined : entry.id,
    content_id: entry.scope === 'collection' ? entry.content_id : undefined,
    // collection: relink the Rekordbox row to the downloaded file — that is
    // the whole point of downloading a missing collection file (owner
    // 16/07). ANLZ consent runs through the standard 428 loop BEFORE the
    // download starts. Requires Rekordbox closed, like every mutation.
    relink: entry.scope === 'collection' ? true : undefined,
    deezer_track_id: deezerTrackId,
  }
}

async function onDeezerPick(result: DeezerSearchResult) {
  const entry = searchFor.value
  searchFor.value = null
  if (entry) await acquire(entry, result.id)
}

const allSelected = computed(
  () => props.entries.length > 0 && props.entries.every((entry) => selected.value.has(entryKey(entry))),
)
function toggleAll() {
  selected.value = allSelected.value ? new Set() : new Set(props.entries.map(entryKey))
}
function toggleOne(entry: MissingEntry) {
  const next = new Set(selected.value)
  const key = entryKey(entry)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  selected.value = next
}

const selectedEntries = computed(() =>
  props.entries.filter((entry) => selected.value.has(entryKey(entry))),
)
const ignorable = computed(() => selectedEntries.value.filter((entry) => entry.scope !== 'collection'))
const acquirable = computed(() => selectedEntries.value.filter((entry) => entry.acquisition?.available))
const removable = computed(() => selectedEntries.value.filter((entry) => entry.scope === 'collection'))

async function openPurchaseUrl(url: string) {
  banner.value = null
  try {
    await openExternal(url)
  } catch {
    banner.value = { tone: 'error', text: t('missing.purchaseOpenFailed') }
  }
}

async function buy(entry: MissingEntry) {
  if (entry.purchase_links.length === 1) {
    await openPurchaseUrl(entry.purchase_links[0].url)
    return
  }
  purchaseMenu.value = purchaseMenu.value === entryKey(entry) ? null : entryKey(entry)
  rowMenu.value = null
}

async function openPurchase(url: string) {
  purchaseMenu.value = null
  await openPurchaseUrl(url)
}

async function act(request: () => Promise<unknown>, success?: string, undo?: MissingEntry[]) {
  banner.value = null
  try {
    await request()
    if (success) banner.value = { tone: 'success', text: success, undo }
    emit('changed')
    return true
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
    return false
  }
}

const ignoreOne = (entry: MissingEntry) =>
  api.post(`/api/missing/${entry.scope}/${entry.id}/status`, { status: 'ignored' })

const ignore = (entry: MissingEntry) =>
  act(() => ignoreOne(entry), t('missing.ignored', { title: entry.title ?? '' }), [entry])

// D22 inline undo: restore puts the PRIOR status back, never 'new'
async function restore(entries: MissingEntry[]) {
  banner.value = null
  try {
    for (const entry of entries)
      await api.post(`/api/missing/${entry.scope}/${entry.id}/restore`)
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
  }
  emit('changed')
}

const removeOne = (entry: MissingEntry) =>
  api.post(`/api/missing/collection/${entry.content_id}/remove`)

const removeCollection = (entry: MissingEntry) =>
  act(() => removeOne(entry), t('missing.removed', { title: entry.title ?? '' }))

async function acquire(entry: MissingEntry, deezerTrackId?: number) {
  banner.value = null
  const key = entryKey(entry)
  const { ok } = await runAcq([{ key, body: acquisitionBody(entry, deezerTrackId) }], describe)
  const reason = humanizeAcquisitionError(t, acqStates.value[key]?.error)
  banner.value = ok
    ? { tone: 'success', text: t('missing.acquired', { title: entry.title ?? '' }) }
    : {
        tone: 'error',
        text:
          t('missing.acquisitionFailed', { title: entry.title ?? '' }) +
          (reason ? ` (${reason})` : ''),
      }
  emit('changed')
}

// --- bulk actions: sequential over the selection, one aggregate banner -----
async function bulkIgnore() {
  banner.value = null
  const done: MissingEntry[] = []
  let failure: string | null = null
  for (const entry of ignorable.value) {
    try {
      await ignoreOne(entry)
      done.push(entry)
    } catch (cause) {
      failure = describe(cause)
      break
    }
  }
  banner.value = failure
    ? { tone: 'error', text: failure }
    : { tone: 'success', text: t('missing.bulkIgnored', { n: done.length }), undo: done }
  selected.value = new Set()
  emit('changed')
}

async function bulkRemove() {
  banner.value = null
  let n = 0
  let failure: string | null = null
  for (const entry of removable.value) {
    try {
      await removeOne(entry)
      n += 1
    } catch (cause) {
      failure = describe(cause)
      break
    }
  }
  banner.value = failure
    ? { tone: 'error', text: failure }
    : { tone: 'success', text: t('missing.bulkRemoved', { n }) }
  selected.value = new Set()
  emit('changed')
}

async function bulkAcquire() {
  banner.value = null
  const targets = acquirable.value
  // ONE ANLZ consent covers the whole selected batch (owner 16/07) — the
  // per-call 428 loop would pop the modal once per collection file
  let anlzGranted = false
  if (targets.some((entry) => entry.scope === 'collection')) {
    anlzGranted = await requestConsent('anlz')
    if (!anlzGranted) return
  }
  selected.value = new Set()
  const { ok, failed } = await runAcq(
    targets.map((entry) => ({
      key: entryKey(entry),
      body: {
        ...acquisitionBody(entry),
        ...(anlzGranted && entry.scope === 'collection' ? { anlz_consent: true } : {}),
      },
    })),
    describe,
  )
  banner.value = {
    tone: failed ? 'error' : 'success',
    text: t('missing.bulkAcquireDone', { ok, failed }),
  }
  emit('changed')
}

async function pickRelink(path: string) {
  const entry = relinkEntry.value
  if (!entry) return
  relinkBusy.value = true
  relinkError.value = null
  try {
    if (entry.scope === 'collection') {
      // real FolderPath re-association — 428 ANLZ consent via the broker
      await api.post(`/api/missing/collection/${entry.content_id}/relink`, { path })
    } else {
      // app-side §5.5 transition: the user relinked it lawfully
      await api.post(`/api/missing/${entry.scope}/${entry.id}/status`, { status: 'relinked' })
    }
    relinkEntry.value = null
    banner.value = { tone: 'success', text: t('missing.relinked', { title: entry.title ?? '' }) }
    emit('changed')
  } catch (cause) {
    relinkError.value = describe(cause)
  } finally {
    relinkBusy.value = false
  }
}

async function markNone() {
  const entry = relinkEntry.value
  if (!entry) return
  if (entry.scope !== 'collection') {
    // "none of these candidates" -> the row needs a manual relink later
    await act(() =>
      api.post(`/api/missing/${entry.scope}/${entry.id}/status`, {
        status: 'manual_relink_needed',
      }),
    )
  }
  relinkEntry.value = null
}
</script>

<template>
  <div>
    <div v-if="banner" class="banner" :data-tone="banner.tone" role="status">
      <span class="banner-text">{{ banner.text }}</span>
      <button v-if="banner.undo?.length" class="undo" @click="restore(banner.undo)">
        {{ t('missing.undo') }}
      </button>
      <button class="banner-close" :aria-label="t('common.close')" @click="banner = null">✕</button>
    </div>

    <div v-if="acqBatch" class="acq-progress" role="status">
      <span class="acq-spinner" aria-hidden="true" />
      {{ t('missing.acqProgress', { done: acqBatch.done, total: acqBatch.total }) }}
    </div>

    <div class="list">
      <div v-if="entries.length" class="list-head">
        <span class="cell-check">
          <input
            type="checkbox"
            :checked="allSelected"
            :aria-label="t('missing.selectAll')"
            @change="toggleAll"
          />
        </span>
        <span class="head-label">{{ t('missing.selectAll') }}</span>
      </div>
      <div
        v-for="entry in entries"
        :key="entryKey(entry)"
        class="row hover-reveal"
        :data-selected="selected.has(entryKey(entry))"
      >
        <span class="cell-check">
          <input
            type="checkbox"
            :checked="selected.has(entryKey(entry))"
            :aria-label="entry.title ?? ''"
            @change="toggleOne(entry)"
          />
        </span>
        <div class="row-text">
          <div class="row-title-line">
            <div class="row-title">
              {{ entry.title || t('missing.untitled')
              }}<template v-if="entry.artist"> — {{ entry.artist }}</template>
            </div>
            <SpotifyAttributionLink
              v-if="entry.spotify_track_id"
              kind="track"
              :spotify-id="entry.spotify_track_id"
            />
          </div>
          <div v-if="entry.file_path" class="row-path mono">{{ entry.file_path }}</div>
          <div v-if="acqStates[entryKey(entry)]?.error" class="row-error">
            {{ humanizeAcquisitionError(t, acqStates[entryKey(entry)]?.error) }}
          </div>
        </div>
        <ScopeBadge v-if="showScope" :scope="entry.scope" />
        <span
          v-if="acqStates[entryKey(entry)]"
          class="acq-badge"
          :data-phase="acqStates[entryKey(entry)]?.phase"
        >
          {{ t(acquisitionLabelKey(acqStates[entryKey(entry)])) }}
        </span>
        <StatusBadge
          v-else-if="entry.scope !== 'collection' && entry.status"
          :status="entry.status"
        />
        <span class="actions">
          <!-- legal path FIRST, prominent (§6.5); absent for removed_from_source -->
          <span v-if="entry.purchase_links.length" class="menu-wrap">
            <button
              class="buy"
              :aria-expanded="
                entry.purchase_links.length > 1
                  ? purchaseMenu === entryKey(entry)
                  : undefined
              "
              @click.stop="buy(entry)"
            >
              {{
                entry.purchase_links.length === 1
                  ? t('missing.buyOn', { store: entry.purchase_links[0].store })
                  : t('missing.buyMenu', { n: entry.purchase_links.length })
              }}
            </button>
            <span
              v-if="entry.purchase_links.length > 1 && purchaseMenu === entryKey(entry)"
              class="menu buy-menu"
            >
              <button
                v-for="link in entry.purchase_links"
                :key="link.store"
                class="menu-item"
                @click="openPurchase(link.url)"
              >
                {{ link.store }}
              </button>
            </span>
          </span>
          <span class="menu-wrap">
            <button
              class="more"
              :data-tip="t('missing.moreActions')"
              :aria-label="t('missing.moreActions')"
              :aria-expanded="rowMenu === entryKey(entry)"
              @click.stop="toggleRowMenu(entry)"
            >
              ⋯
            </button>
            <span v-if="rowMenu === entryKey(entry)" class="menu">
              <button
                v-if="entry.acquisition?.available"
                class="menu-item"
                :disabled="jobs.jobRunning || acqRunning"
                @click="acquire(entry)"
              >
                {{ t('missing.acquireDeezer') }}
              </button>
              <button
                v-if="searchable(entry)"
                class="menu-item"
                :disabled="jobs.jobRunning || acqRunning"
                @click="searchFor = entry"
              >
                {{ t('missing.searchDeezer') }}
              </button>
              <button class="menu-item" @click="relinkEntry = entry">
                {{ t('missing.relinkCta') }}
              </button>
              <button
                v-if="entry.scope !== 'collection'"
                class="menu-item"
                @click="ignore(entry)"
              >
                {{ t('missing.ignoreCta') }}
              </button>
              <button
                v-else
                class="menu-item danger"
                :disabled="status.rbOpen || jobs.jobRunning"
                :title="status.rbOpen ? t('rbGuard.blocked') : t('missing.removeTitle')"
                @click="removeCollection(entry)"
              >
                {{ status.rbOpen ? t('rbGuard.blocked') : t('missing.removeCta') }}
              </button>
            </span>
          </span>
        </span>
      </div>
      <div v-if="!entries.length" class="empty">
        <div class="empty-glyph">✓</div>
        <div class="empty-title">{{ t('missing.emptyTitle') }}</div>
        <p class="empty-body">{{ t('missing.emptyBody') }}</p>
      </div>
    </div>

    <div class="sel-float-anchor">
      <SelectionBar :count="selected.size" @clear="selected = new Set()">
        <button v-if="ignorable.length" class="sel-action" @click="bulkIgnore">
          {{ t('missing.bulkIgnore', { n: ignorable.length }) }}
        </button>
        <button
          v-if="acquirable.length"
          class="sel-action"
          :disabled="jobs.jobRunning || acqRunning"
          @click="bulkAcquire"
        >
          {{ t('missing.bulkAcquire', { n: acquirable.length }) }}
        </button>
        <button
          v-if="removable.length"
          class="sel-action danger"
          :disabled="status.rbOpen || jobs.jobRunning"
          :title="status.rbOpen ? t('rbGuard.blocked') : t('missing.removeTitle')"
          @click="bulkRemove"
        >
          {{ status.rbOpen ? t('rbGuard.blocked') : t('missing.bulkRemove', { n: removable.length }) }}
        </button>
      </SelectionBar>
    </div>

    <ManualRelinkModal
      v-if="relinkEntry"
      :entry="relinkEntry"
      :busy="relinkBusy"
      :error="relinkError"
      @close="relinkEntry = null"
      @pick="pickRelink"
      @none="markNone"
    />

    <DeezerSearchPanel
      v-if="searchFor"
      :initial-query="searchQuery"
      :context-label="searchFor.title ?? ''"
      @close="searchFor = null"
      @pick="onDeezerPick"
    />
  </div>
</template>

<style scoped>
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
  min-width: 0;
}
.undo {
  background: transparent;
  border: 1px solid var(--success-border);
  color: var(--success);
  border-radius: 7px;
  padding: 3px 10px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.banner-close {
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
  padding: 0 2px;
}
.list {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  /* visible (was clip): row menus and data-tip tooltips must escape the
     card; first/last children carry the radius so corners still round */
  overflow: visible;
}
.list > :first-child {
  border-top-left-radius: var(--radius-card);
  border-top-right-radius: var(--radius-card);
}
.list > :last-child {
  border-bottom-left-radius: var(--radius-card);
  border-bottom-right-radius: var(--radius-card);
}
.list-head {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 9px 18px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: var(--size-meta);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  font-weight: 600;
}
.cell-check {
  width: 20px;
  display: flex;
  align-items: center;
  flex: none;
  align-self: stretch; /* the whole cell height stays clickable */
}
.row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 13px 18px;
  border-bottom: 1px solid var(--border-subtle);
}
.row:hover {
  background: #0f131b;
}
.row[data-selected='true'] {
  background: rgba(77, 163, 255, 0.06);
}
.row-text {
  flex: 1;
  min-width: 0;
}
.row-title-line {
  display: flex;
  align-items: center;
  gap: 8px;
}
.row-title {
  font-size: 13.5px;
  font-weight: 500;
  min-width: 0;
}
.row-path {
  font-size: 11.5px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
.mono {
  font-family: var(--font-mono);
}
.actions {
  display: flex;
  gap: 7px;
  flex: none;
  align-items: center;
  justify-content: flex-end;
}
.buy {
  background: var(--teal-tint);
  border: 1px solid var(--teal-border);
  color: var(--teal);
  padding: 6px 12px;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.menu-wrap {
  position: relative;
  display: inline-flex;
}
/* popover dropdown: never shifts the row (owner feedback 15/07) */
.menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 8;
  display: flex;
  flex-direction: column;
  min-width: 160px;
  padding: 4px;
  border: 1px solid var(--border-2);
  border-radius: 9px;
  background: var(--surface-raised);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.45);
}
.buy-menu {
  border-color: var(--teal-border);
}
.menu-item {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  padding: 7px 10px;
  border-radius: 6px;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  white-space: nowrap;
}
.buy-menu .menu-item {
  color: var(--teal);
  font-weight: 600;
}
.menu-item:hover {
  background: var(--accent-tint);
  color: var(--accent-hover);
}
.buy-menu .menu-item:hover {
  background: var(--teal-tint);
  color: var(--teal);
}
.menu-item.danger {
  color: var(--danger-text);
}
.menu-item:disabled {
  opacity: 0.55;
  cursor: default;
}
.more {
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
}
.more:hover,
.more[aria-expanded='true'] {
  color: var(--accent-hover);
  border-color: var(--accent-border);
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
.sel-action {
  background: rgba(77, 163, 255, 0.16);
  color: var(--accent-hover);
  border: 1px solid var(--accent-border);
  padding: 5px 11px;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.sel-action.danger {
  background: var(--danger-tint);
  color: var(--danger-text);
  border-color: var(--danger-border);
}
.sel-action:disabled {
  opacity: 0.55;
  cursor: default;
}
.empty {
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
