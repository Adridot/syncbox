<script setup lang="ts">
// Untagged tab (SPEC-DESIGN §2/§6, D15): 4 sorted categories (junk <
// dup_of_tagged < alt_version < review), selection over the FILTERED rows,
// delete with a REAL skip report (protected/tagged/not-found), and the
// minimal junk-pattern editor (D7: list/add/delete a regex). RB-guarded.
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '../../api/client'
import GuardedButton from '../../components/GuardedButton.vue'
import { useHealthStore } from '../../stores/health'

const { t } = useI18n()
const health = useHealthStore()

interface UntaggedTrack {
  content_id: string
  title: string | null
  artist: string | null
  category: 'junk' | 'dup_of_tagged' | 'alt_version' | 'review'
}
interface Pattern {
  id: number
  pattern: string
}

const tracks = ref<UntaggedTrack[]>([])
const patterns = ref<Pattern[]>([])
const checked = ref<Set<string>>(new Set())
const categoryFilter = ref('all')
const newPattern = ref('')
const showEditor = ref(false)
const skipReport = ref<Array<{ content_id: string; reason: string }> | null>(null)

const CATEGORIES = ['all', 'junk', 'dup_of_tagged', 'alt_version', 'review']

onMounted(load)

async function load() {
  const [t1, p1] = await Promise.all([
    api.get<{ tracks: UntaggedTrack[] }>('/api/untagged'),
    api.get<{ patterns: Pattern[] }>('/api/untagged/patterns'),
  ])
  tracks.value = t1.tracks
  patterns.value = p1.patterns
  health.setUntaggedCount(t1.tracks.length)
}

const visible = computed(() =>
  categoryFilter.value === 'all'
    ? tracks.value
    : tracks.value.filter((tk) => tk.category === categoryFilter.value),
)

function toggle(id: string) {
  const next = new Set(checked.value)
  next.has(id) ? next.delete(id) : next.add(id)
  checked.value = next
}
const allChecked = computed(
  () => visible.value.length > 0 && visible.value.every((tk) => checked.value.has(tk.content_id)),
)
function toggleAll() {
  // selection is bound to the VISIBLE (filtered) rows only (SPEC-DESIGN §9).
  checked.value = allChecked.value ? new Set() : new Set(visible.value.map((tk) => tk.content_id))
}

async function deleteSelected() {
  skipReport.value = null
  const body = await api.post<{ soft_deleted: string[]; skipped: Array<{ content_id: string; reason: string }> }>(
    '/api/untagged/delete',
    { content_ids: [...checked.value] },
  )
  skipReport.value = body.skipped.length ? body.skipped : null
  checked.value = new Set()
  await load()
}

async function addPattern() {
  const value = newPattern.value.trim()
  if (!value) return
  await api.post('/api/untagged/patterns', { pattern: value })
  newPattern.value = ''
  await load()
}
async function removePattern(id: number) {
  await api.delete(`/api/untagged/patterns/${id}`)
  await load()
}
</script>

<template>
  <div>
    <div class="intro">{{ t('untagged.intro') }}</div>

    <div class="filters">
      <button
        v-for="cat in CATEGORIES"
        :key="cat"
        class="chip-btn"
        :data-active="categoryFilter === cat"
        @click="categoryFilter = cat"
      >
        {{ cat === 'all' ? t('library.filterAll') : t(`untagged.category.${cat}`) }}
      </button>
      <span class="spacer" />
      <button class="btn-ghost sm" @click="showEditor = !showEditor">
        {{ t('untagged.patterns.toggle') }}
      </button>
    </div>

    <!-- minimal junk-pattern editor (D7) -->
    <div v-if="showEditor" class="editor">
      <div class="editor-label">{{ t('untagged.patterns.title') }}</div>
      <div class="pattern-rows">
        <div v-for="pattern in patterns" :key="pattern.id" class="pattern-row">
          <span class="mono">{{ pattern.pattern }}</span>
          <button class="del" @click="removePattern(pattern.id)">✕</button>
        </div>
        <div v-if="!patterns.length" class="no-patterns">{{ t('untagged.patterns.empty') }}</div>
      </div>
      <div class="pattern-add">
        <input
          v-model="newPattern"
          class="mono"
          :placeholder="t('untagged.patterns.placeholder')"
          @keydown.enter="addPattern"
        />
        <button class="btn-ghost sm" @click="addPattern">{{ t('untagged.patterns.add') }}</button>
      </div>
    </div>

    <div v-if="skipReport" class="skip-report">
      {{ t('untagged.skipReport', { n: skipReport.length }) }}
      <span v-for="s in skipReport" :key="s.content_id" class="skip-chip"
        >{{ s.content_id }}: {{ t(`untagged.skip.${s.reason}`) }}</span
      >
    </div>

    <div class="table">
      <div class="thead">
        <span class="cb"><input type="checkbox" :checked="allChecked" @change="toggleAll" /></span>
        <span v-if="checked.size" class="sel-info"
          ><span class="mono">{{ checked.size }}</span> {{ t('library.selected') }}</span
        >
        <span v-else class="sel-hint">{{ t('untagged.selectAll') }}</span>
        <span class="spacer" />
        <GuardedButton
          v-if="checked.size"
          :label="t('untagged.deleteSelected')"
          tone="danger"
          @click="deleteSelected"
        />
      </div>
      <div v-for="track in visible" :key="track.content_id" class="urow">
        <span class="cb"
          ><input type="checkbox" :checked="checked.has(track.content_id)" @change="toggle(track.content_id)"
        /></span>
        <div class="utext">
          <div class="utitle mono">{{ track.title || '∅' }}</div>
          <div class="uartist">{{ track.artist }}</div>
        </div>
        <span class="cat-badge" :data-cat="track.category">{{ t(`untagged.category.${track.category}`) }}</span>
      </div>
      <div v-if="!visible.length" class="empty">{{ t('untagged.empty') }}</div>
    </div>
  </div>
</template>

<style scoped>
.intro {
  font-size: 12.5px;
  color: var(--text-muted-bright);
  margin-bottom: 13px;
  line-height: 1.5;
}
.filters {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 14px;
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
}
.chip-btn[data-active='true'] {
  background: var(--accent-tint);
  border-color: var(--accent-border);
  color: var(--accent-hover);
}
.spacer {
  flex: 1;
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
.editor {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 11px;
  padding: 14px;
  margin-bottom: 16px;
}
.editor-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 10px;
}
.pattern-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pattern-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 7px;
  padding: 6px 10px;
  font-size: 12.5px;
}
.mono {
  font-family: var(--font-mono);
}
.del {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
}
.no-patterns {
  font-size: 12px;
  color: var(--text-muted);
}
.pattern-add {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.pattern-add input {
  flex: 1;
  background: var(--surface-raised);
  border: 1px solid #2a3140;
  border-radius: 7px;
  padding: 7px 10px;
  color: var(--text-secondary-bright);
  font-size: 12.5px;
  outline: none;
}
.skip-report {
  background: var(--warning-tint);
  border: 1px solid var(--warning-border);
  border-radius: 9px;
  padding: 11px 13px;
  margin-bottom: 14px;
  font-size: 12.5px;
  color: var(--warning-text);
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.skip-chip {
  font-family: var(--font-mono);
  font-size: 11px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 5px;
  padding: 2px 6px;
}
.table {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 13px;
  overflow: clip;
}
.thead {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 9px 18px;
  border-bottom: 1px solid var(--border-subtle-2);
}
.cb input {
  accent-color: var(--accent);
  cursor: pointer;
}
.sel-info {
  font-size: 12px;
  color: var(--accent-hover);
  font-weight: 600;
}
.sel-hint {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  font-weight: 600;
}
.urow {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: var(--row-padding-y) 18px;
  border-bottom: 1px solid var(--border-subtle);
}
.utext {
  flex: 1;
  min-width: 0;
}
.utitle {
  font-size: 13px;
  font-weight: 500;
}
.uartist {
  font-size: 12px;
  color: var(--text-muted-bright);
}
.cat-badge {
  font-size: var(--size-meta);
  border-radius: 6px;
  padding: 2px 8px;
  font-weight: 500;
}
.cat-badge[data-cat='junk'] {
  background: var(--danger-tint);
  color: var(--danger-text);
}
.cat-badge[data-cat='dup_of_tagged'] {
  background: var(--uncertain-tint);
  color: var(--uncertain);
}
.cat-badge[data-cat='alt_version'] {
  background: var(--accent-tint);
  color: var(--accent-hover);
}
.cat-badge[data-cat='review'] {
  background: var(--neutral-tint);
  color: var(--text-secondary-bright);
}
.empty {
  padding: 34px;
  text-align: center;
  font-size: 12.5px;
  color: var(--text-muted);
}
</style>
