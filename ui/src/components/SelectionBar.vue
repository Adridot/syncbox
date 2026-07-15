<script setup lang="ts">
// Floating selection pill (owner decision 15/07): appears over the list
// instead of inside the toolbar so the table never shifts when a selection
// starts. Actions come through the slot; positioning is the parent's job
// (absolute or sticky anchor).
import { useI18n } from 'vue-i18n'

defineProps<{ count: number }>()
const emit = defineEmits<{ clear: [] }>()
const { t } = useI18n()
</script>

<template>
  <Transition name="selbar">
    <div v-if="count" class="selection-float" role="toolbar">
      <span class="float-count"
        ><span class="mono">{{ count }}</span> {{ t('library.selection.selected') }}</span
      >
      <slot />
      <button class="float-clear" :aria-label="t('common.close')" @click="emit('clear')">✕</button>
    </div>
  </Transition>
</template>

<style scoped>
.selection-float {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface-raised);
  border: 1px solid var(--accent-border);
  border-radius: 12px;
  padding: 7px 8px 7px 14px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.45);
}
.float-count {
  font-size: 12px;
  color: var(--accent-hover);
  font-weight: 600;
  white-space: nowrap;
}
.float-clear {
  background: transparent;
  color: var(--text-muted-bright);
  border: none;
  padding: 4px 6px;
  font-size: 12px;
  cursor: pointer;
}
.mono {
  font-family: var(--font-mono);
}
.selbar-enter-active,
.selbar-leave-active {
  transition: opacity 140ms ease, transform 140ms ease;
}
.selbar-enter-from,
.selbar-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>
