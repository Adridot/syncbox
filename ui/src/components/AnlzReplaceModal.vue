<script setup lang="ts">
// ANLZ consent (SPEC-UNIFIED §5.5/§3.1): relinking REPLACES a file
// association; cues/beatgrid/waveform live in ANLZ files OUTSIDE the backup
// guarantee. Named consent BEFORE the replacement. v1 framing = relink to
// an owned local file (the mockup's re-download wording is deprecated).
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import ModalShell from './ModalShell.vue'

const emit = defineEmits<{ cancel: []; confirm: [] }>()
const { t } = useI18n()
const consent = ref(false)
</script>

<template>
  <ModalShell width="520px" @close="emit('cancel')">
    <div class="body">
      <div class="head">
        <div class="glyph">↻</div>
        <h3>{{ t('consent.anlz.title') }}</h3>
      </div>
      <i18n-t tag="p" class="lead" keypath="consent.anlz.lead">
        <template #cues>
          <b>{{ t('consent.anlz.cues') }}</b>
        </template>
        <template #uncovered>
          <b class="warn">{{ t('consent.anlz.uncovered') }}</b>
        </template>
      </i18n-t>
      <div class="note">{{ t('consent.anlz.reversibleNote') }}</div>
      <label class="consent">
        <input v-model="consent" type="checkbox" />
        <span>{{ t('consent.anlz.checkbox') }}</span>
      </label>
      <div class="actions">
        <button class="btn-secondary" @click="emit('cancel')">{{ t('common.cancel') }}</button>
        <button class="confirm" :disabled="!consent" @click="emit('confirm')">
          {{ t('consent.anlz.confirm') }}
        </button>
      </div>
    </div>
  </ModalShell>
</template>

<style scoped>
.body {
  padding: 22px;
}
.head {
  display: flex;
  align-items: center;
  gap: 11px;
}
.glyph {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: var(--warning-tint);
  border: 1px solid var(--warning-border);
  display: grid;
  place-content: center;
  font-size: 18px;
  color: var(--warning-text);
}
h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}
.lead {
  color: var(--text-secondary-bright);
  font-size: 13.5px;
  margin: 13px 0 0;
  line-height: 1.55;
}
.lead .warn {
  color: var(--warning-text);
}
.note {
  background: rgba(52, 211, 153, 0.06);
  border: 1px solid rgba(52, 211, 153, 0.22);
  border-radius: 9px;
  padding: 11px 13px;
  margin-top: 13px;
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.5;
}
.consent {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  cursor: pointer;
  margin-top: 14px;
  background: rgba(245, 181, 68, 0.06);
  border: 1px solid rgba(245, 181, 68, 0.22);
  border-radius: 11px;
  padding: 13px 14px;
}
.consent input {
  accent-color: var(--warning);
  margin-top: 2px;
}
.consent span {
  font-size: 13px;
  color: var(--warning-text);
  font-weight: 600;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}
.confirm {
  background: var(--warning);
  border: none;
  color: #1f1503;
  padding: 9px 18px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.confirm:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
