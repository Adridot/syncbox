<script setup lang="ts">
// Shared missing-entry list (M4.9 collection tab + M4.10 center):
// purchase-first legal path (§5.5/§5.13 — links open in the SYSTEM browser,
// the sidecar never contacts stores), manual relink, §5.5 status
// transitions with a D22 inline undo, and the G3 collection remove.
// Every action surfaces its outcome (B1). Optional acquisition appears only
// when the backend marks it available; purchase links remain first.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../api/client'
import type { MissingEntry } from '../api/types'
import { openExternal } from '../shell'
import { useJobsStore } from '../stores/jobs'
import { useStatusStore } from '../stores/status'
import ManualRelinkModal from './ManualRelinkModal.vue'
import ScopeBadge from './ScopeBadge.vue'
import SpotifyAttributionLink from './SpotifyAttributionLink.vue'
import StatusBadge from './StatusBadge.vue'

defineProps<{ entries: MissingEntry[]; showScope?: boolean }>()
const emit = defineEmits<{ changed: [] }>()
const { t } = useI18n()
const status = useStatusStore()
const jobs = useJobsStore()

const banner = ref<{ tone: 'error' | 'success'; text: string; undo?: MissingEntry } | null>(null)
const relinkEntry = ref<MissingEntry | null>(null)
const relinkBusy = ref(false)
const relinkError = ref<string | null>(null)
const purchaseMenu = ref<string | null>(null)

function describe(cause: unknown): string {
  return cause instanceof ApiError ? cause.message : t('common.networkError')
}

function entryKey(entry: MissingEntry): string {
  return `${entry.scope}:${String(entry.id)}`
}

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
}

async function openPurchase(url: string) {
  purchaseMenu.value = null
  await openPurchaseUrl(url)
}

async function act(request: () => Promise<unknown>, success?: string, undo?: MissingEntry) {
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

const ignore = (entry: MissingEntry) =>
  act(
    () => api.post(`/api/missing/${entry.scope}/${entry.id}/status`, { status: 'ignored' }),
    t('missing.ignored', { title: entry.title ?? '' }),
    entry,
  )

const restore = (entry: MissingEntry) =>
  act(() => api.post(`/api/missing/${entry.scope}/${entry.id}/restore`))

const removeCollection = (entry: MissingEntry) =>
  act(
    () => api.post(`/api/missing/collection/${entry.content_id}/remove`),
    t('missing.removed', { title: entry.title ?? '' }),
  )

async function acquire(entry: MissingEntry) {
  banner.value = null
  try {
    const job = await api.post<{ status: string }>('/api/acquisition/jobs', {
        scope: entry.scope,
        row_id: entry.scope === 'collection' ? undefined : entry.id,
        content_id: entry.scope === 'collection' ? entry.content_id : undefined,
    })
    banner.value = {
      tone: job.status === 'downloaded' ? 'success' : 'error',
      text: t(
        job.status === 'downloaded' ? 'missing.acquired' : 'missing.acquisitionFailed',
        { title: entry.title ?? '' },
      ),
    }
    emit('changed')
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
  }
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
      <!-- D22 inline undo: restore puts the PRIOR status back, never 'new' -->
      <button v-if="banner.undo" class="undo" @click="restore(banner.undo)">
        {{ t('missing.undo') }}
      </button>
      <button class="banner-close" :aria-label="t('common.close')" @click="banner = null">✕</button>
    </div>

    <div class="list">
      <div v-for="entry in entries" :key="entryKey(entry)" class="row">
        <div class="row-text">
          <div class="row-title">
            {{ entry.title || t('missing.untitled')
            }}<template v-if="entry.artist"> — {{ entry.artist }}</template>
          </div>
          <div v-if="entry.file_path" class="row-path mono">{{ entry.file_path }}</div>
        </div>
        <ScopeBadge v-if="showScope" :scope="entry.scope" />
        <StatusBadge
          v-if="entry.scope !== 'collection' && entry.status"
          :status="entry.status"
        />
        <span class="actions">
          <SpotifyAttributionLink
            v-if="entry.spotify_track_id"
            compact
            kind="track"
            :spotify-id="entry.spotify_track_id"
          />
          <!-- legal path FIRST, prominent (§6.5); absent for removed_from_source -->
          <button
            v-if="entry.purchase_links.length"
            class="buy"
            :aria-expanded="
              entry.purchase_links.length > 1
                ? purchaseMenu === entryKey(entry)
                : undefined
            "
            @click="buy(entry)"
          >
            {{
              entry.purchase_links.length === 1
                ? t('missing.buyOn', { store: entry.purchase_links[0].store })
                : t('missing.buyMenu', { n: entry.purchase_links.length })
            }}
          </button>
          <span
            v-if="entry.purchase_links.length > 1 && purchaseMenu === entryKey(entry)"
            class="buy-menu"
          >
            <button
              v-for="link in entry.purchase_links"
              :key="link.store"
              class="buy-menu-item"
              @click="openPurchase(link.url)"
            >
              {{ link.store }}
            </button>
          </span>
          <button
            v-if="entry.acquisition?.available"
            class="secondary"
            :disabled="jobs.jobRunning"
            @click="acquire(entry)"
          >
            {{ t('missing.acquireDeezer') }}
          </button>
          <button class="secondary" @click="relinkEntry = entry">
            {{ t('missing.relinkCta') }}
          </button>
          <button
            v-if="entry.scope !== 'collection'"
            class="secondary"
            @click="ignore(entry)"
          >
            {{ t('missing.ignoreCta') }}
          </button>
          <button
            v-else
            class="remove"
            :disabled="status.rbOpen || jobs.jobRunning"
            :title="status.rbOpen ? t('rbGuard.blocked') : t('missing.removeTitle')"
            @click="removeCollection(entry)"
          >
            {{ status.rbOpen ? t('rbGuard.blocked') : t('missing.removeCta') }}
          </button>
        </span>
      </div>
      <div v-if="!entries.length" class="empty">
        <div class="empty-glyph">✓</div>
        <div class="empty-title">{{ t('missing.emptyTitle') }}</div>
        <p class="empty-body">{{ t('missing.emptyBody') }}</p>
      </div>
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
  overflow: clip;
}
.row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 13px 18px;
  border-bottom: 1px solid var(--border-subtle);
}
.row-text {
  flex: 1;
  min-width: 0;
}
.row-title {
  font-size: 13.5px;
  font-weight: 500;
}
.row-path {
  font-size: 11.5px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mono {
  font-family: var(--font-mono);
}
.actions {
  display: flex;
  gap: 7px;
  flex: none;
  flex-wrap: wrap;
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
.buy-menu {
  display: inline-flex;
  gap: 4px;
  padding: 3px;
  border: 1px solid var(--teal-border);
  border-radius: 8px;
  background: var(--surface-raised);
}
.buy-menu-item {
  background: transparent;
  border: none;
  color: var(--teal);
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.buy-menu-item:hover {
  background: var(--teal-tint);
}
.secondary {
  background: transparent;
  border: 1px solid #2a3140;
  color: var(--text-secondary);
  padding: 6px 12px;
  border-radius: 7px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.secondary:hover {
  color: var(--accent-hover);
  border-color: var(--accent-border);
}
.remove {
  background: transparent;
  border: 1px solid #2a3140;
  color: var(--danger-text);
  padding: 6px 12px;
  border-radius: 7px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.remove:disabled {
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
