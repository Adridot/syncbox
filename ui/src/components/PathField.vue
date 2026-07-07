<script setup lang="ts">
// Path with REAL validation ticks (B3): ✓ appears only after the server
// confirmed the path (validate_directory / file check on PUT) — never for
// "any non-empty value". The caller re-validates stored paths on mount.
import { useI18n } from 'vue-i18n'

export type PathState = 'unknown' | 'checking' | 'valid' | 'invalid'

defineProps<{
  label: string
  modelValue: string
  state: PathState
  message?: string | null
  placeholder?: string
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string]; save: [] }>()
const { t } = useI18n()
</script>

<template>
  <div class="path-field">
    <div class="label">{{ label }}</div>
    <div class="row">
      <input
        :value="modelValue"
        type="text"
        class="mono"
        :placeholder="placeholder"
        :data-invalid="state === 'invalid'"
        @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
        @keydown.enter.prevent="emit('save')"
      />
      <span class="tick" :data-state="state">
        {{ state === 'valid' ? '✓' : state === 'invalid' ? '✕' : state === 'checking' ? '…' : '' }}
      </span>
      <button class="btn-secondary small" @click="emit('save')">
        {{ t('settings.paths.validate') }}
      </button>
    </div>
    <div v-if="state === 'invalid' && message" class="error">{{ message }}</div>
    <div class="help"><slot /></div>
  </div>
</template>

<style scoped>
.label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 5px;
}
.row {
  display: flex;
  align-items: center;
  gap: 8px;
}
input {
  flex: 1;
  min-width: 0;
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 8px;
  padding: 9px 11px;
  font-size: 12px;
  color: var(--text-secondary-bright);
  outline: none;
}
input:focus {
  border-color: var(--accent-border);
}
input[data-invalid='true'] {
  border-color: rgba(247, 110, 110, 0.35);
  color: var(--danger-text);
}
.mono {
  font-family: var(--font-mono);
}
.tick {
  width: 16px;
  text-align: center;
  font-size: 14px;
  flex: none;
}
.tick[data-state='valid'] {
  color: var(--success);
}
.tick[data-state='invalid'] {
  color: var(--danger);
}
.tick[data-state='checking'] {
  color: var(--text-muted);
}
.btn-secondary.small {
  padding: 7px 12px;
  font-size: 12px;
  flex: none;
}
.error {
  font-size: 12px;
  color: var(--danger-text);
  margin-top: 6px;
}
.help {
  font-size: 11.5px;
  color: var(--text-muted);
  margin-top: 6px;
  line-height: 1.5;
}
.help:empty {
  display: none;
}
</style>
