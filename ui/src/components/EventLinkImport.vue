<script setup lang="ts">
import { computed, onMounted, onUnmounted, onUpdated, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ApiError, api } from '../api/client'
import type { EventLinkImport, LinkImportEntry } from '../api/types'
import { openExternal } from '../shell'

const props = defineProps<{ eventId: number }>()
const emit = defineEmits<{ committed: []; layout: [] }>()
const { t, te } = useI18n()
const link = ref('')
const current = ref<EventLinkImport | null>(null)
const history = ref<Pick<EventLinkImport, 'id' | 'state' | 'source_provider'>[]>([])
const selected = ref<string[]>([])
const readd = ref(false)
const busy = ref(false)
const error = ref('')
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
const humanize = (code: string) => te(`linkImport.errors.${code}`) ? t(`linkImport.errors.${code}`) : code

function report(cause: unknown) {
  const code = cause instanceof ApiError ? cause.message : cause instanceof Error ? cause.message : String(cause)
  needsChoice.value = code === 'video_or_playlist_choice_required'
  error.value = needsChoice.value ? '' : humanize(code)
}

async function read(id: string) {
  const reading = ++revision
  clearTimeout(timer)
  try {
    const row = await api.get<EventLinkImport>(`${root}/${id}`)
    if (disposed || reading !== revision) return
    const firstReady = current.value?.id !== id || current.value?.state !== 'ready'
    if (current.value?.id !== id) readd.value = false
    current.value = row
    history.value = history.value.map(item => item.id === id ? row : item)
    if (row.state === 'ready' && firstReady) selected.value = row.manifest?.entries.filter(selectable).map(entry => entry.entry_key) ?? []
    error.value = row.state === 'failed' ? humanize(row.error ?? 'provider_metadata_unavailable') : ''
    if (resolving.value) timer = setTimeout(() => void read(id), 500)
  } catch (cause) { if (!disposed && reading === revision) report(cause) }
}

async function restore() {
  const restoring = revision
  try {
    const result = await api.get<{ imports: typeof history.value }>(root)
    if (disposed || restoring !== revision) return
    history.value = result.imports ?? []
    if (history.value[0]) await read(history.value[0].id)
  } catch (cause) { if (!disposed) report(cause) }
}

async function start(choice?: 'track' | 'playlist') {
  if (!link.value.trim() || busy.value) return
  busy.value = true
  error.value = ''
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
  } catch (cause) { report(cause) }
  finally { busy.value = false }
}

async function commit() {
  if (busy.value || !current.value || !selectedKeys.value.length) return
  busy.value = true
  error.value = ''
  const id = current.value.id
  try {
    await api.post(`${root}/${current.value.id}/commit`, { selected_keys: selectedKeys.value, readd_keys: readd.value ? selectedKeys.value.filter(key => inactive.has(entries.value.find(entry => entry.entry_key === key)?.existing_status ?? '')) : [] })
    link.value = ''
    token = crypto.randomUUID()
    await read(id)
    emit('committed')
  } catch (cause) { report(cause) }
  finally { busy.value = false }
}

async function dismiss() {
  if (busy.value || !current.value) return
  busy.value = true
  ++revision
  clearTimeout(timer)
  try {
    await api.delete(`${root}/${current.value.id}`)
    clearTimeout(timer)
    current.value = null
    error.value = ''
    token = crypto.randomUUID()
  } catch (cause) { report(cause) }
  finally { busy.value = false }
}

async function retry() {
  if (busy.value || !current.value) return
  busy.value = true
  error.value = ''
  try { await api.post(`${root}/${current.value.id}/retry`); await read(current.value.id) }
  catch (cause) { report(cause) }
  finally { busy.value = false }
}

onMounted(restore)
onUpdated(() => emit('layout'))
onUnmounted(() => { disposed = true; ++revision; clearTimeout(timer) })
</script>

<template>
  <section class="link-import" :aria-label="t('linkImport.title')">
    <form class="input-row" @submit.prevent="start()">
      <label class="input-label">{{ t('linkImport.title') }}
        <input v-model="link" :placeholder="t('linkImport.placeholder')" :disabled="busy" @input="changedLink" />
      </label>
      <button class="btn-primary" :disabled="busy || !link.trim()">{{ t('linkImport.preview') }}</button>
    </form>
    <div v-if="needsChoice" class="actions" role="group" :aria-label="t('linkImport.chooseScope')">
      <span>{{ t('linkImport.chooseScope') }}</span>
      <button @click="start('track')">{{ t('linkImport.video') }}</button>
      <button @click="start('playlist')">{{ t('linkImport.playlist') }}</button>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
    <router-link v-if="error && /web_audio|component/.test(current?.error ?? '')" to="/settings">{{ t('linkImport.setup') }}</router-link>
    <label v-if="history.length > 1">{{ t('linkImport.recent') }}
      <select :disabled="busy" :value="current?.id" @change="read(($event.target as HTMLSelectElement).value)">
        <option v-for="item in history" :key="item.id" :value="item.id">{{ item.source_provider }} · {{ item.state }}</option>
      </select>
    </label>
    <div v-if="current && current.state !== 'dismissed'" class="preview">
      <button class="source" @click="openExternal(current.canonical_url).catch(report)">{{ current.source_provider }} ↗ {{ current.manifest?.title }}</button>
      <p v-if="resolving" role="status">{{ t('linkImport.resolving') }}</p>
      <p v-if="current.state === 'committed'" role="status">{{ t('linkImport.committed', { n: current.result?.added ?? 0 }) }}</p>
      <template v-if="current.state === 'ready'">
        <p>{{ t('linkImport.counts', { total: entries.length, selected: selectedKeys.length, unavailable: entries.filter(entry => !entry.available).length }) }}</p>
        <div class="actions">
          <button @click="selected = entries.filter(selectable).map(entry => entry.entry_key)">{{ t('linkImport.selectAll') }}</button>
          <button @click="selected = []">{{ t('linkImport.selectNone') }}</button>
          <label v-if="entries.some(entry => inactive.has(entry.existing_status ?? ''))"><input v-model="readd" type="checkbox" />{{ t('linkImport.readd') }}</label>
        </div>
        <div class="entries">
          <label v-for="entry in entries" :key="entry.entry_key" class="entry">
            <input v-model="selected" type="checkbox" :value="entry.entry_key" :disabled="!selectable(entry) || busy" />
            <span>{{ entry.position }}. {{ entry.title || entry.item_id || t('linkImport.unavailable') }} <small>{{ entry.artist }}</small></span>
            <small v-if="!entry.available">{{ t('linkImport.unavailable') }}</small>
            <small v-else-if="entry.repeated">{{ t('linkImport.repeated') }}</small>
            <small v-else-if="entry.existing_status">{{ t(inactive.has(entry.existing_status) ? 'linkImport.removed' : 'linkImport.alreadyPresent') }}</small>
          </label>
        </div>
        <p>{{ t('linkImport.noDownload') }}</p>
        <button class="btn-primary" :disabled="busy || !selectedKeys.length" @click="commit">{{ t('linkImport.confirm', { n: selectedKeys.length }) }}</button>
      </template>
      <button v-if="current.state === 'failed'" :disabled="busy" @click="retry">{{ t('linkImport.retry') }}</button>
      <button v-if="current.state !== 'committed'" :disabled="busy" @click="dismiss">{{ t('linkImport.dismiss') }}</button>
    </div>
  </section>
</template>

<style scoped>
.link-import { margin: 14px 0; display: grid; gap: 10px; }
.input-row, .actions { display: flex; gap: 10px; align-items: end; flex-wrap: wrap; }
.input-label { flex: 1; display: grid; gap: 6px; min-width: 220px; }
input:not([type='checkbox']) { width: 100%; box-sizing: border-box; padding: 10px; }
.preview { border: 1px solid var(--border); border-radius: 10px; padding: 14px; }
.source { background: none; border: none; color: var(--text); text-align: left; cursor: pointer; }
.entries { max-height: 320px; overflow: auto; margin: 12px 0; }
.entry { display: flex; gap: 10px; padding: 9px 0; align-items: center; }
.entry span { flex: 1; }
small { color: var(--text-muted); }
[role='alert'] { color: var(--danger-text); }
button { cursor: pointer; padding: 7px 12px; }
</style>
