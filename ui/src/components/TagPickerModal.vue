<script setup lang="ts">
// BulkTagBar + TagPicker (SPEC-DESIGN §6, D16): tag edits are ADD/REMOVE
// DELTAS, never a union overwrite. Searchable picker over known MyTags with
// per-row +/− toggles, delta chips, and a live summary. A track can be both
// in add and remove? No — a tag is add XOR remove XOR untouched.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '../api/client'
import { useLibraryStore } from '../stores/library'
import type { LibraryTrack } from '../stores/library'
import ModalShell from './ModalShell.vue'

const { t } = useI18n()
const props = defineProps<{ trackIds: number[]; sourceIds: number[] }>()
const emit = defineEmits<{ close: []; applied: [] }>()
const library = useLibraryStore()

const add = ref<string[]>([])
const remove = ref<string[]>([])
const query = ref('')
const newTag = ref('')
const submitting = ref(false)

const results = computed(() => {
  const q = query.value.trim().toLowerCase()
  return library.knownTags.filter((tag) => !q || tag.toLowerCase().includes(q))
})

function toggleAdd(tag: string) {
  remove.value = remove.value.filter((x) => x !== tag)
  add.value = add.value.includes(tag) ? add.value.filter((x) => x !== tag) : [...add.value, tag]
}
function toggleRemove(tag: string) {
  add.value = add.value.filter((x) => x !== tag)
  remove.value = remove.value.includes(tag)
    ? remove.value.filter((x) => x !== tag)
    : [...remove.value, tag]
}
function addFresh() {
  const value = newTag.value.trim()
  if (value && !add.value.includes(value)) {
    remove.value = remove.value.filter((x) => x !== value)
    add.value.push(value)
  }
  newTag.value = ''
}

const summary = computed(() => {
  const parts: string[] = []
  if (add.value.length) parts.push(`+${add.value.length}`)
  if (remove.value.length) parts.push(`−${remove.value.length}`)
  return parts.join(' · ') || t('library.tags.noDelta')
})

async function apply() {
  if (!add.value.length && !remove.value.length) return
  submitting.value = true
  try {
    const { tracks } = await api.post<{ tracks: LibraryTrack[] }>('/api/library/tracks/tags', {
      track_ids: props.trackIds,
      add: add.value,
      remove: remove.value,
    })
    // fold the updated rows back into their source lists
    const bySource = new Map(props.sourceIds.map((id) => [id, id]))
    tracks.forEach((updated) => {
      for (const sourceId of bySource.keys()) library.replaceTrack(sourceId, updated)
    })
    emit('applied')
    emit('close')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <ModalShell width="520px" @close="emit('close')">
    <div class="body">
      <h3>{{ t('library.tags.title') }}</h3>
      <p class="lede">{{ t('library.tags.lede') }}</p>

      <div class="delta-block">
        <div class="delta-label add">{{ t('library.tags.add') }}</div>
        <div class="chips">
          <span v-for="tag in add" :key="tag" class="chip add" @click="toggleAdd(tag)">{{ tag }} ✕</span>
          <span v-if="!add.length" class="empty-chip">{{ t('library.tags.addEmpty') }}</span>
        </div>
      </div>
      <div class="delta-block">
        <div class="delta-label remove">{{ t('library.tags.remove') }}</div>
        <div class="chips">
          <span v-for="tag in remove" :key="tag" class="chip remove" @click="toggleRemove(tag)"
            >{{ tag }} ✕</span
          >
          <span v-if="!remove.length" class="empty-chip">{{ t('library.tags.removeEmpty') }}</span>
        </div>
      </div>

      <div class="picker">
        <div class="picker-search">
          <span>⌕</span>
          <input
            v-model="query"
            :placeholder="t('library.tags.search', { n: library.knownTags.length })"
          />
        </div>
        <div class="picker-list">
          <div v-for="tag in results" :key="tag" class="picker-row">
            <span class="picker-name">{{ tag }}</span>
            <button class="pm add" :data-on="add.includes(tag)" @click="toggleAdd(tag)">+</button>
            <button class="pm remove" :data-on="remove.includes(tag)" @click="toggleRemove(tag)">
              −
            </button>
          </div>
          <div v-if="!results.length && !query" class="picker-empty">
            {{ t('library.tags.noKnownTags') }}
          </div>
        </div>
        <div class="fresh">
          <input
            v-model="newTag"
            :placeholder="t('library.tags.freshTag')"
            @keydown.enter.prevent="addFresh"
          />
          <button class="btn-ghost sm" @click="addFresh">{{ t('library.tags.addFresh') }}</button>
        </div>
      </div>

      <div class="summary">
        <span class="mono">{{ trackIds.length }}</span> {{ t('library.tags.tracks') }} ·
        <span class="mono accent">{{ summary }}</span>
      </div>

      <div class="actions">
        <button class="btn-ghost" @click="emit('close')">{{ t('common.cancel') }}</button>
        <button
          class="btn-primary"
          :disabled="(!add.length && !remove.length) || submitting"
          @click="apply"
        >
          {{ t('library.tags.applyDelta') }}
        </button>
      </div>
    </div>
  </ModalShell>
</template>

<style scoped>
.body {
  padding: 22px;
}
h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}
.lede {
  color: var(--text-muted-bright);
  font-size: 13px;
  margin: 5px 0 0;
  line-height: 1.5;
}
.delta-block {
  margin-top: 14px;
}
.delta-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 600;
  margin-bottom: 7px;
}
.delta-label.add {
  color: #5fe0b0;
}
.delta-label.remove {
  color: var(--danger-text);
}
.chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  min-height: 30px;
}
.chip {
  padding: 4px 10px;
  border-radius: 7px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.chip.add {
  background: var(--success-tint);
  color: #5fe0b0;
  border: 1px solid var(--success-border);
}
.chip.remove {
  background: var(--danger-tint);
  color: var(--danger-text);
  border: 1px solid var(--danger-border);
}
.empty-chip {
  font-size: 12px;
  color: var(--text-muted);
  padding: 4px 0;
}
.picker {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 11px;
  padding: 13px;
  margin-top: 16px;
}
.picker-search {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface-raised);
  border: 1px solid #2a3140;
  border-radius: 8px;
  padding: 8px 11px;
  color: var(--text-muted);
}
.picker-search input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-secondary-bright);
  font-family: inherit;
  font-size: 13px;
}
.picker-list {
  max-height: 200px;
  overflow-y: auto;
  margin-top: 8px;
}
.picker-row {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 2px;
}
.picker-name {
  flex: 1;
  font-size: 13px;
  color: var(--text-secondary-bright);
}
.pm {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  border: 1px solid var(--border-2);
  background: var(--surface-raised);
  color: var(--text-muted-bright);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}
.pm.add[data-on='true'] {
  background: var(--success-tint);
  border-color: var(--success-border);
  color: #5fe0b0;
}
.pm.remove[data-on='true'] {
  background: var(--danger-tint);
  border-color: var(--danger-border);
  color: var(--danger-text);
}
.picker-empty {
  padding: 18px;
  text-align: center;
  font-size: 12.5px;
  color: var(--text-muted);
}
.fresh {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.fresh input {
  flex: 1;
  background: var(--surface-raised);
  border: 1px solid #2a3140;
  border-radius: 8px;
  padding: 7px 10px;
  color: var(--text-secondary-bright);
  font-family: inherit;
  font-size: 12.5px;
  outline: none;
}
.summary {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 11px 13px;
  margin-top: 14px;
  font-size: 12.5px;
  color: var(--text-secondary);
}
.mono {
  font-family: var(--font-mono);
}
.accent {
  color: var(--accent-hover);
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 16px;
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
.btn-ghost.sm {
  padding: 7px 12px;
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
}
.btn-primary:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
