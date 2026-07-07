<script setup lang="ts">
// Bulk tag edition in DELTA add/remove (D16 — never a union overwrite).
// Searchable picker over the /api/mytags catalog with per-row +/− toggles
// (SPEC-DESIGN §6 BulkTagBar + TagPicker); the CTA reflects the exact delta.
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../api/client'
import type { LibraryTrack, MyTag } from '../api/types'
import ModalShell from './ModalShell.vue'

const props = defineProps<{ trackIds: number[] }>()
const emit = defineEmits<{ close: []; applied: [tracks: LibraryTrack[]] }>()
const { t } = useI18n()

const catalog = ref<MyTag[] | null>(null)
const catalogError = ref<string | null>(null)
const query = ref('')
const add = ref<string[]>([])
const remove = ref<string[]>([])
const applying = ref(false)
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    catalog.value = (await api.get<{ tags: MyTag[] }>('/api/mytags')).tags
  } catch (cause) {
    // B1: the picker says WHY it has no catalog; free-text entry still works
    catalogError.value = cause instanceof ApiError ? cause.message : t('common.networkError')
    catalog.value = []
  }
})

const results = computed(() => {
  const q = query.value.trim().toLowerCase()
  const list = catalog.value ?? []
  return q ? list.filter((tag) => tag.name.toLowerCase().includes(q)) : list
})

const exactMatch = computed(() =>
  (catalog.value ?? []).some((tag) => tag.name.toLowerCase() === query.value.trim().toLowerCase()),
)

function toggle(list: typeof add, other: typeof remove, name: string) {
  other.value = other.value.filter((x) => x !== name)
  list.value = list.value.includes(name)
    ? list.value.filter((x) => x !== name)
    : [...list.value, name]
}
const toggleAdd = (name: string) => toggle(add, remove, name)
const toggleRemove = (name: string) => toggle(remove, add, name)
function createTag() {
  toggleAdd(query.value.trim())
  query.value = ''
}

const summary = computed(() => {
  const parts = []
  if (add.value.length) parts.push(`+${add.value.length}`)
  if (remove.value.length) parts.push(`−${remove.value.length}`)
  return parts.join(' ')
})

async function apply() {
  applying.value = true
  error.value = null
  try {
    const body = await api.post<{ tracks: LibraryTrack[] }>('/api/library/tracks/tags', {
      track_ids: props.trackIds,
      add: add.value,
      remove: remove.value,
    })
    emit('applied', body.tracks)
  } catch (cause) {
    // B1: never a silent no-op on a confirmed action
    error.value = cause instanceof ApiError ? cause.message : t('common.networkError')
  } finally {
    applying.value = false
  }
}
</script>

<template>
  <ModalShell width="560px" @close="emit('close')">
    <div class="body">
      <h3>{{ t('tags.bulkTitle') }}</h3>
      <p class="sub">{{ t('tags.bulkSub') }}</p>

      <div class="delta-block">
        <div class="delta-label add-label">{{ t('tags.addLabel') }}</div>
        <div class="chips">
          <button v-for="name in add" :key="name" class="chip add" @click="add = add.filter((x) => x !== name)">
            {{ name }} ✕
          </button>
          <span v-if="!add.length" class="chips-empty">{{ t('tags.addEmpty') }}</span>
        </div>
      </div>
      <div class="delta-block">
        <div class="delta-label remove-label">{{ t('tags.removeLabel') }}</div>
        <div class="chips">
          <button
            v-for="name in remove"
            :key="name"
            class="chip remove"
            @click="remove = remove.filter((x) => x !== name)"
          >
            {{ name }} ✕
          </button>
          <span v-if="!remove.length" class="chips-empty">{{ t('tags.removeEmpty') }}</span>
        </div>
      </div>

      <div class="picker">
        <div class="search-row">
          <span class="glyph">⌕</span>
          <input
            v-model="query"
            type="text"
            :placeholder="t('tags.searchPlaceholder', { n: catalog?.length ?? 0 })"
          />
        </div>
        <div v-if="catalogError" class="catalog-error">{{ catalogError }}</div>
        <div class="cols-head">
          <span class="col-tag">MyTag</span>
          <span class="col-add">{{ t('tags.colAdd') }}</span>
          <span class="col-remove">{{ t('tags.colRemove') }}</span>
        </div>
        <div class="rows">
          <div v-for="tag in results" :key="tag.name" class="row">
            <div class="row-name">
              <span :class="{ chosen: add.includes(tag.name) || remove.includes(tag.name) }">{{
                tag.name
              }}</span>
              <span v-if="tag.category" class="cat mono">{{ tag.category }}</span>
            </div>
            <button
              class="toggle add-toggle"
              :data-active="add.includes(tag.name)"
              :aria-label="`+ ${tag.name}`"
              @click="toggleAdd(tag.name)"
            >
              +
            </button>
            <button
              class="toggle remove-toggle"
              :data-active="remove.includes(tag.name)"
              :aria-label="`− ${tag.name}`"
              @click="toggleRemove(tag.name)"
            >
              −
            </button>
          </div>
          <button v-if="query.trim() && !exactMatch" class="create-row" @click="createTag">
            {{ t('tags.create', { name: query.trim() }) }}
          </button>
          <div v-if="!results.length && !query.trim()" class="rows-empty">
            {{ t('tags.catalogEmpty') }}
          </div>
          <div v-else-if="!results.length" class="rows-empty">{{ t('tags.noMatch') }}</div>
        </div>
      </div>

      <div class="summary">
        <span class="mono">{{ props.trackIds.length }}</span>
        {{ t('tags.tracksUnit') }} ·
        <span class="mono delta">{{ summary || '—' }}</span>
      </div>

      <div v-if="error" class="error-row">{{ error }}</div>

      <div class="actions">
        <button class="btn-secondary" @click="emit('close')">{{ t('common.cancel') }}</button>
        <button
          class="btn-primary"
          :disabled="applying || (!add.length && !remove.length)"
          @click="apply"
        >
          {{ t('tags.applyDelta') }}
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
.sub {
  color: var(--text-muted-bright);
  font-size: 13px;
  margin: 5px 0 0;
  line-height: 1.5;
}
.delta-block {
  margin-top: 14px;
}
.delta-label {
  font-size: var(--size-meta);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 600;
  margin-bottom: 7px;
}
.add-label {
  color: #5fe0b0;
}
.remove-label {
  color: var(--danger-text);
}
.chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  min-height: 30px;
  align-items: center;
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
.chips-empty {
  font-size: 12px;
  color: var(--text-muted);
}
.picker {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 11px;
  padding: 13px;
  margin-top: 16px;
}
.search-row {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface-raised);
  border: 1px solid #2a3140;
  border-radius: 8px;
  padding: 8px 11px;
}
.search-row .glyph {
  color: var(--text-muted);
  font-size: 13px;
}
.search-row input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-secondary-bright);
  font: inherit;
  font-size: 13px;
}
.catalog-error {
  margin-top: 9px;
  font-size: 12px;
  color: var(--danger-text);
}
.cols-head {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: var(--size-label);
  color: var(--text-muted);
  margin: 9px 2px 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.col-tag {
  flex: 1;
}
.col-add {
  color: #5fe0b0;
}
.col-remove {
  color: var(--danger-text);
}
.rows {
  max-height: 208px;
  overflow-y: auto;
  scrollbar-gutter: stable;
  padding-right: 3px;
}
.row {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px 2px;
}
.row-name {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.row-name span:first-child {
  font-size: 13px;
  color: var(--text-secondary-bright);
}
.row-name .chosen {
  color: var(--text-primary);
  font-weight: 500;
}
.cat {
  font-size: var(--size-meta);
  color: var(--text-muted);
}
.toggle {
  width: 26px;
  height: 24px;
  border-radius: 6px;
  border: 1px solid #2a3140;
  background: transparent;
  color: var(--text-muted-bright);
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
}
.add-toggle[data-active='true'] {
  background: var(--success-tint);
  border-color: var(--success-border);
  color: #5fe0b0;
}
.remove-toggle[data-active='true'] {
  background: var(--danger-tint);
  border-color: var(--danger-border);
  color: var(--danger-text);
}
.create-row {
  width: 100%;
  text-align: left;
  padding: 7px 2px;
  background: transparent;
  border: none;
  color: var(--accent-hover);
  font-size: 12.5px;
  cursor: pointer;
}
.rows-empty {
  padding: 18px;
  text-align: center;
  font-size: 12.5px;
  color: var(--text-muted);
}
.summary {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 11px 13px;
  margin-top: 14px;
  font-size: 12.5px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 8px;
}
.summary .mono {
  color: var(--text-secondary-bright);
}
.summary .delta {
  color: var(--accent-hover);
}
.mono {
  font-family: var(--font-mono);
}
.error-row {
  margin-top: 12px;
  background: var(--danger-tint);
  border: 1px solid var(--danger-border);
  border-radius: 9px;
  padding: 9px 12px;
  color: var(--danger-text);
  font-size: 12.5px;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 16px;
}
</style>
