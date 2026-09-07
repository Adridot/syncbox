<script setup lang="ts">
// Snapshot link imports (SPEC-UNIFIED §11.1 revision): paste a track, album
// or playlist link from a supported provider, preview its entries, pick some,
// confirm. Same add-row geometry the Spotify-only field had, so the workspace
// keeps its rhythm; the preview is a table section, not a card in a card.
import { computed, nextTick, onMounted, onUnmounted, onUpdated, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NetworkError, api } from '../api/client'
import type { EventLinkImport, LinkImportEntry } from '../api/types'
import { openExternal } from '../shell'

const props = defineProps<{ eventId: number }>()
const emit = defineEmits<{ committed: []; layout: [] }>()
const { t, te } = useI18n()
const link = ref('')
const current = ref<EventLinkImport | null>(null)
const history = ref<Pick<EventLinkImport, 'id' | 'state' | 'source_provider' | 'canonical_url'>[]>([])
const selected = ref<string[]>([])
const readd = ref(false)
const busy = ref(false)
const errorCode = ref('')
const readErrorId = ref<string | null>(null)
const opening = ref(false)
const input = ref<HTMLInputElement | null>(null)
const previewHeading = ref<HTMLElement | null>(null)
const needsChoice = ref(false)
let token = crypto.randomUUID()
function changedLink() { token = crypto.randomUUID(); needsChoice.value = false }
let disposed = false
let revision = 0
let timer: ReturnType<typeof setTimeout> | undefined
const root = `/api/events/${props.eventId}/link-imports`
const inactive = new Set(['removed', 'ignored', 'removed_upstream'])
const entries = computed(() => current.value?.manifest?.entries ?? [])
const selectable = (entry: LinkImportEntry) => entry.available && !entry.repeated && (!entry.existing_status || (readd.value && inactive.has(entry.existing_status)))
const selectedKeys = computed(() => selected.value.filter(key => entries.value.some(entry => entry.entry_key === key && selectable(entry))))
const resolving = computed(() => ['queued', 'resolving'].includes(current.value?.state ?? ''))
const hasInactive = computed(() => entries.value.some(entry => inactive.has(entry.existing_status ?? '')))
const unavailable = computed(() => entries.value.filter(entry => !entry.available).length)
// a component/setup failure gets a shortcut to Settings next to the message
const needsSetup = computed(() => /web_audio|component|spotify_authentication_required/.test(errorCode.value))
const humanize = (code: string) => te(`linkImport.errors.${code}`) ? t(`linkImport.errors.${code}`) : code
const error = computed(() => errorCode.value === 'network_error' ? t('common.networkError') : humanize(errorCode.value))
const providerLabel = (provider: string) => te(`providers.${provider}`) ? t(`providers.${provider}`) : provider
const stateLabel = (state: string) => te(`linkImport.states.${state}`) ? t(`linkImport.states.${state}`) : state

/** One chip per entry explains why it cannot be picked (or was already). */
function entryNote(entry: LinkImportEntry): { key: string; tone: 'danger' | 'muted' | 'warning' } | null {
  if (!entry.available) return { key: 'unavailable', tone: 'danger' }
  if (entry.repeated) return { key: 'repeated', tone: 'muted' }
  if (entry.existing_status) return inactive.has(entry.existing_status) ? { key: 'removed', tone: 'warning' } : { key: 'alreadyPresent', tone: 'muted' }
  return null
}

function setError(code: string) {
  errorCode.value = code
}

function report(cause: unknown) {
  const code = cause instanceof NetworkError ? 'network_error' : cause instanceof Error ? cause.message : String(cause)
  needsChoice.value = code === 'video_or_playlist_choice_required'
  setError(needsChoice.value ? '' : code)
}

async function read(id: string) {
  const reading = ++revision
  clearTimeout(timer)
  if (current.value?.id !== id) {
    current.value = null
    selected.value = []
    readd.value = false
    opening.value = true
  }
  try {
    const row = await api.get<EventLinkImport>(`${root}/${id}`)
    if (disposed || reading !== revision) return
    readErrorId.value = null
    const firstReady = current.value?.id !== id || current.value?.state !== 'ready'
    if (current.value?.id !== id) readd.value = false
    current.value = row
    history.value = history.value.map(item => item.id === id ? row : item)
    if (row.state === 'ready' && firstReady) selected.value = row.manifest?.entries.filter(selectable).map(entry => entry.entry_key) ?? []
    setError(row.state === 'failed' ? row.error ?? 'provider_metadata_unavailable' : '')
    if (row.state === 'ready' && firstReady) {
      await nextTick()
      if (!disposed && reading === revision) previewHeading.value?.focus()
    }
    if (resolving.value) timer = setTimeout(() => void read(id), 500)
  } catch (cause) {
    if (!disposed && reading === revision) { readErrorId.value = id; report(cause) }
  } finally { if (reading === revision) opening.value = false }
}

async function restore() {
  const restoring = revision
  try {
    const result = await api.get<{ imports: typeof history.value }>(root)
    if (disposed || restoring !== revision) return
    history.value = result.imports ?? []
    if (history.value[0]) await read(history.value[0].id)
  } catch (cause) {
    if (!disposed && restoring === revision) { readErrorId.value = ''; report(cause) }
  }
}

async function start(choice?: 'track' | 'playlist') {
  if (!link.value.trim() || busy.value) return
  busy.value = true
  setError('')
  readErrorId.value = null
  opening.value = false
  needsChoice.value = false
  ++revision
  clearTimeout(timer)
  try {
    const row = await api.post<EventLinkImport>(root, { url: link.value.trim(), request_token: token, choice })
    if (disposed) return
    current.value = row
    history.value = [row, ...history.value.filter(item => item.id !== row.id)]
    readd.value = false
    selected.value = row.state === 'ready' ? row.manifest?.entries.filter(selectable).map(entry => entry.entry_key) ?? [] : []
    await read(row.id)
    await nextTick()
    if (!disposed && current.value?.state === 'ready') previewHeading.value?.focus()
  } catch (cause) { report(cause) }
  finally { busy.value = false }
}

async function commit() {
  if (busy.value || !current.value || !selectedKeys.value.length) return
  busy.value = true
  setError('')
  const id = current.value.id
  try {
    const result = await api.post<EventLinkImport['result']>(`${root}/${id}/commit`, { selected_keys: selectedKeys.value, readd_keys: readd.value ? selectedKeys.value.filter(key => inactive.has(entries.value.find(entry => entry.entry_key === key)?.existing_status ?? '')) : [] })
    if (disposed) return
    current.value = { ...current.value, state: 'committed', result }
    history.value = history.value.map(item => item.id === id ? { ...item, state: 'committed' } : item)
    link.value = ''
    token = crypto.randomUUID()
    emit('committed')
    busy.value = false
    await nextTick()
    input.value?.focus()
  } catch (cause) { report(cause) }
  finally { busy.value = false }
}

async function dismiss() {
  if (busy.value || !current.value) return
  busy.value = true
  ++revision
  clearTimeout(timer)
  const id = current.value.id
  try {
    await api.delete(`${root}/${id}`)
    if (disposed) return
    clearTimeout(timer)
    current.value = null
    history.value = history.value.filter(item => item.id !== id)
    readErrorId.value = null
    setError('')
    token = crypto.randomUUID()
    busy.value = false
    await nextTick()
    input.value?.focus()
  } catch (cause) { report(cause) }
  finally { busy.value = false }
}

async function retry() {
  if (busy.value || !current.value) return
  busy.value = true
  setError('')
  try { await api.post(`${root}/${current.value.id}/retry`); await read(current.value.id) }
  catch (cause) { report(cause) }
  finally { busy.value = false }
}

function openSource() {
  if (current.value) openExternal(current.value.canonical_url).catch(report)
}

onMounted(restore)
onUpdated(() => emit('layout'))
onUnmounted(() => { disposed = true; ++revision; clearTimeout(timer) })
</script>

<template>
  <section class="link-import" :aria-label="t('linkImport.title')">
    <form class="add-row" @submit.prevent="start()">
      <div class="link-box">
        <span class="glyph" aria-hidden="true">🔗</span>
        <input
          ref="input"
          v-model="link"
          type="text"
          class="mono"
          :placeholder="t('linkImport.placeholder')"
          :aria-label="t('linkImport.title')"
          :aria-invalid="!!error || undefined"
          autocomplete="off"
          :spellcheck="false"
          :disabled="busy"
          @input="changedLink"
        />
      </div>
      <button class="btn-primary add-btn" type="submit" :disabled="busy || !link.trim()">
        {{ busy ? t('common.loading') : t('linkImport.preview') }}
      </button>
    </form>

    <div v-if="history.length" class="history-row">
      <label :for="`import-history-${eventId}`">{{ t('linkImport.recent') }}</label>
      <select
        :id="`import-history-${eventId}`"
        class="history"
        :disabled="busy"
        :value="current?.id ?? ''"
        @change="read(($event.target as HTMLSelectElement).value)"
      >
        <option v-if="!current" value="" disabled>{{ t('linkImport.recent') }}</option>
        <option v-for="item in history" :key="item.id" :value="item.id">
          {{ providerLabel(item.source_provider) }} · {{ stateLabel(item.state) }} · {{ item.canonical_url }}
        </option>
      </select>
    </div>

    <div v-if="needsChoice" class="choice-row" role="group" :aria-label="t('linkImport.chooseScope')">
      <span class="choice-text">{{ t('linkImport.chooseScope') }}</span>
      <button class="btn-secondary tool" :disabled="busy" @click="start('track')">
        {{ t('linkImport.video') }}
      </button>
      <button class="btn-secondary tool" :disabled="busy" @click="start('playlist')">
        {{ t('linkImport.playlist') }}
      </button>
    </div>

    <div v-if="error" class="banner" data-tone="error" role="alert">
      <span class="banner-text">{{ error }}</span>
      <button v-if="readErrorId !== null" class="banner-link" :disabled="busy" @click="readErrorId ? read(readErrorId) : restore()">{{ t('linkImport.retry') }}</button>
      <router-link v-if="needsSetup" class="banner-link" to="/settings">{{ t('linkImport.setup') }}</router-link>
      <button class="banner-close" :aria-label="t('common.close')" @click="setError('')">✕</button>
    </div>

    <div v-if="opening && !current" class="preview-status" role="status">
      <span class="spinner" aria-hidden="true" />{{ t('common.loading') }}
    </div>

    <div v-if="current && current.state !== 'dismissed'" class="preview">
      <header class="preview-head">
        <div ref="previewHeading" class="preview-text" tabindex="-1">
          <h3 class="preview-title" :title="current.manifest?.title || current.canonical_url">{{ current.manifest?.title || current.canonical_url }}</h3>
          <div class="preview-sub">
            {{ providerLabel(current.source_provider) }}
            <template v-if="entries.length"> · {{ t('linkImport.entries', entries.length) }}</template>
          </div>
        </div>
        <button class="action-link" @click="openSource">{{ t('linkImport.open') }} ↗</button>
        <button
          v-if="current.state !== 'committed'"
          class="preview-close"
          :disabled="busy"
          :aria-label="t('linkImport.dismiss')"
          :data-tip="t('linkImport.dismiss')"
          @click="dismiss"
        >
          ✕
        </button>
      </header>

      <div v-if="resolving && !readErrorId" class="preview-status" role="status">
        <span class="spinner" aria-hidden="true" />{{ t('linkImport.resolving') }}
      </div>
      <div v-else-if="current.state === 'committed'" class="preview-status" data-tone="success" role="status">
        {{ t('linkImport.committed', { n: current.result?.added ?? 0 }) }}
      </div>
      <div v-else-if="current.state === 'failed'" class="preview-status">
        <button class="btn-secondary tool" :disabled="busy" @click="retry">{{ t('linkImport.retry') }}</button>
      </div>

      <template v-if="current.state === 'ready'">
        <div class="actions">
          <button class="btn-secondary tool" :disabled="busy" @click="selected = entries.filter(selectable).map(entry => entry.entry_key)">
            {{ t('linkImport.selectAll') }}
          </button>
          <button class="btn-secondary tool" :disabled="busy" @click="selected = []">
            {{ t('linkImport.selectNone') }}
          </button>
          <label v-if="hasInactive" class="toggle-row">
            <input v-model="readd" type="checkbox" :disabled="busy" />
            <span>{{ t('linkImport.readd') }}</span>
          </label>
          <span class="spacer" />
          <span class="counts" role="status" aria-live="polite" aria-atomic="true">
            {{ t('linkImport.counts', { selected: selectedKeys.length, total: entries.length }) }}
            <template v-if="unavailable"> · {{ t('linkImport.unavailableCount', unavailable) }}</template>
          </span>
        </div>
        <div class="entries">
          <label v-for="entry in entries" :key="entry.entry_key" class="entry" :data-off="!selectable(entry) || undefined">
            <input v-model="selected" type="checkbox" :value="entry.entry_key" :disabled="!selectable(entry) || busy" />
            <span class="cell-title">
              <span class="row-title" :title="entry.title || undefined">{{ entry.position }}. {{ entry.title || entry.item_id || t('linkImport.unavailable') }}</span>
              <span v-if="entry.artist" class="row-artist" :title="entry.artist">{{ entry.artist }}</span>
            </span>
            <span v-if="entryNote(entry)" class="entry-chip" :data-tone="entryNote(entry)!.tone">
              {{ t(`linkImport.${entryNote(entry)!.key}`) }}
            </span>
          </label>
        </div>
        <footer class="preview-foot">
          <span class="foot-note">{{ t('linkImport.noDownload') }}</span>
          <button class="btn-primary add-btn" :disabled="busy || !selectedKeys.length" @click="commit">
            {{ t('linkImport.confirm', { n: selectedKeys.length }) }}
          </button>
        </footer>
      </template>
    </div>
  </section>
</template>

<style scoped>
/* ---- add row: the geometry the Spotify-only field had ---- */
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
  padding: 0;
  border-radius: 0;
  color: var(--text-secondary-bright);
  font-size: 12.5px;
}
.link-box input.mono {
  font-family: var(--font-mono);
}
.link-box:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-tint);
}
.link-import :is(button, select, input[type='checkbox']):focus-visible,
.preview-text:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}
.history-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 18px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-muted-bright);
  font-size: 12px;
}
.history-row label {
  flex: none;
}
.add-btn {
  padding: 8px 15px;
  font-size: 12.5px;
  flex: none;
}
.tool {
  padding: 6px 12px;
  font-size: 12px;
}
.spacer {
  flex: 1;
}

/* ---- ambiguity + errors: the workspace's banner vocabulary ---- */
.choice-row,
.banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 18px;
  font-size: 12.5px;
  border-bottom: 1px solid var(--border-subtle-2);
}
.choice-text {
  color: var(--text-secondary-bright);
}
.banner[data-tone='error'] {
  background: var(--danger-tint);
  color: var(--danger-text);
}
.banner-text {
  flex: 1;
  min-width: 0;
}
.banner-link {
  color: inherit;
  font-weight: 600;
  white-space: nowrap;
  background: transparent;
  border: none;
  cursor: pointer;
}
.banner-close,
.preview-close {
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
  padding: 0 2px;
}

/* ---- preview: a table section, same rhythm as the tracklist ---- */
.preview {
  border-bottom: 1px solid var(--border-subtle-2);
}
.preview-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 18px;
  border-bottom: 1px solid var(--border-subtle);
}
.preview-text {
  flex: 1;
  min-width: 0;
}
.preview-title {
  margin: 0;
  font-size: 13.5px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.preview-sub {
  font-size: 11.5px;
  color: var(--text-muted-bright);
  margin-top: 2px;
}
.action-link {
  background: transparent;
  border: 1px solid #2a3140;
  color: var(--accent-hover);
  padding: 4px 11px;
  border-radius: 7px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
/* the app's select vocabulary (base.css) with a compact height; the extra
   right padding keeps the native chevron off the border */
.history {
  flex: 1;
  min-width: 0;
  max-width: 100%;
  padding: 5px 16px 5px 10px;
  font-size: 12px;
}
.preview-close {
  color: var(--text-secondary);
  font-size: 14px;
}
.preview-close:disabled {
  opacity: 0.55;
  cursor: default;
}
.preview-status {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 11px 18px;
  font-size: 12.5px;
  color: var(--text-secondary-bright);
}
.preview-status[data-tone='success'] {
  color: var(--success);
}
.spinner {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid var(--border-2);
  border-top-color: var(--accent);
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.actions {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 18px;
  border-bottom: 1px solid var(--border-subtle-2);
  flex-wrap: wrap;
}
.toggle-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: var(--text-secondary-bright);
  margin-left: 6px;
  cursor: pointer;
}
.counts {
  font-size: var(--size-meta);
  color: var(--text-muted);
}
.entries {
  max-height: 320px;
  overflow-y: auto;
}
.entry {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 9px 18px;
  border-bottom: 1px solid var(--border-subtle);
  cursor: pointer;
}
.entry:last-child {
  border-bottom: none;
}
.entry[data-off] {
  cursor: default;
}
.entry[data-off] .cell-title {
  opacity: 0.55;
}
.cell-title {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.row-title {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.row-artist {
  font-size: 11.5px;
  color: var(--text-muted-bright);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* same family as the tracklist's .added-chip / .adopted-chip */
.entry-chip {
  flex: none;
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  border-radius: 4px;
  padding: 1px 5px;
  color: var(--text-muted-bright);
  background: var(--surface-raised);
}
.entry-chip[data-tone='danger'] {
  color: var(--danger-text);
  background: var(--danger-tint);
}
.entry-chip[data-tone='warning'] {
  color: var(--warning-text);
  background: var(--warning-tint);
}
.preview-foot {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 18px;
  border-top: 1px solid var(--border-subtle-2);
}
.foot-note {
  flex: 1;
  min-width: 0;
  font-size: 11.5px;
  color: var(--text-muted-bright);
}
@media (max-width: 900px) {
  .preview-head, .preview-foot, .choice-row, .banner {
    flex-wrap: wrap;
  }
  .preview-text, .foot-note, .banner-text {
    flex-basis: 60%;
  }
  .choice-text { flex-basis: 100%; }
  .entry { gap: 8px; }
  .entry-chip { max-width: 35%; }
}
@media (prefers-reduced-motion: reduce) {
  .spinner { animation: none; }
}
</style>
