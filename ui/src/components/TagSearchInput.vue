<script setup lang="ts">
// Small searchable MyTag adder (AddSourceModal default tags): suggestions
// from the /api/mytags catalog + free-text creation (the §5.6 pre-exist
// rule bites at apply time, surfaced there).
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { MyTag } from '../api/types'

const props = defineProps<{ catalog: MyTag[]; exclude: string[] }>()
const emit = defineEmits<{ pick: [name: string] }>()
const { t } = useI18n()

const query = ref('')

const suggestions = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return []
  return props.catalog
    .filter((tag) => !props.exclude.includes(tag.name) && tag.name.toLowerCase().includes(q))
    .slice(0, 6)
})

const exactMatch = computed(() =>
  props.catalog.some((tag) => tag.name.toLowerCase() === query.value.trim().toLowerCase()),
)

function pick(name: string) {
  emit('pick', name)
  query.value = ''
}

function onEnter() {
  const raw = query.value.trim()
  if (!raw) return
  const suggestion = suggestions.value[0]
  pick(suggestion && exactMatch.value ? suggestion.name : raw)
}
</script>

<template>
  <div class="tag-input">
    <input
      v-model="query"
      type="text"
      :placeholder="t('tags.addPlaceholder')"
      @keydown.enter.prevent="onEnter"
    />
    <div v-if="suggestions.length || (query.trim() && !exactMatch)" class="suggestions">
      <button
        v-for="tag in suggestions"
        :key="tag.name"
        type="button"
        class="suggestion"
        @click="pick(tag.name)"
      >
        <span>{{ tag.name }}</span>
        <span v-if="tag.category" class="cat mono">{{ tag.category }}</span>
      </button>
      <button
        v-if="query.trim() && !exactMatch"
        type="button"
        class="suggestion create"
        @click="pick(query.trim())"
      >
        {{ t('tags.create', { name: query.trim() }) }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.tag-input {
  position: relative;
  display: inline-block;
  min-width: 140px;
}
input {
  width: 100%;
  background: transparent;
  border: 1px dashed #2a3140;
  border-radius: 7px;
  padding: 4px 10px;
  color: var(--text-secondary-bright);
  font: inherit;
  font-size: 12px;
  outline: none;
}
input:focus {
  border-color: var(--accent-border);
}
.suggestions {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  min-width: 220px;
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 9px;
  box-shadow: var(--shadow-overlay);
  z-index: 10;
  overflow: hidden;
}
.suggestion {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  padding: 7px 11px;
  background: transparent;
  border: none;
  color: var(--text-secondary-bright);
  font-size: 12.5px;
  cursor: pointer;
  text-align: left;
}
.suggestion:hover {
  background: var(--accent-tint);
}
.suggestion.create {
  color: var(--accent-hover);
  border-top: 1px solid var(--border-subtle-2);
}
.cat {
  font-size: var(--size-meta);
  color: var(--text-muted);
}
.mono {
  font-family: var(--font-mono);
}
</style>
