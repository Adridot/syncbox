<script setup lang="ts">
// A mutation CTA that reflects the RB-open guard (SPEC-DESIGN §8): when
// Rekordbox is open it shows "Rekordbox ouvert — bloqué" and is disabled,
// instead of looking clickable. Used by apply/delete/reapply/smartfixes —
// wherever a write is gated on mutationAllowed (D11/D23 consistency).
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useStatusStore } from '../stores/status'

const props = withDefaults(
  defineProps<{ label: string; tone?: 'primary' | 'danger' | 'warning'; disabled?: boolean }>(),
  { tone: 'primary', disabled: false },
)
const emit = defineEmits<{ click: [] }>()
const { t } = useI18n()
const status = useStatusStore()

const blocked = computed(() => status.rbOpen)
const text = computed(() => (blocked.value ? t('rbGuard.blocked') : props.label))
</script>

<template>
  <button
    class="guarded"
    :data-tone="tone"
    :data-blocked="blocked"
    :disabled="blocked || disabled"
    @click="emit('click')"
  >
    {{ text }}
  </button>
</template>

<style scoped>
.guarded {
  border: none;
  padding: 9px 18px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  color: #06131f;
}
.guarded[data-tone='primary'] {
  background: var(--accent);
}
.guarded[data-tone='danger'] {
  background: var(--danger);
}
.guarded[data-tone='warning'] {
  background: var(--warning);
}
.guarded[data-blocked='true'] {
  background: var(--warning-tint);
  border: 1px solid var(--warning-border);
  color: var(--warning-text);
  cursor: not-allowed;
}
.guarded:disabled:not([data-blocked='true']) {
  opacity: 0.5;
  cursor: default;
}
</style>
