<script setup lang="ts">
// Permanent file deletion on a trash-less volume (cloud/exFAT) — consent
// BEFORE, never after (SPEC-DESIGN §6/§8). The DB row stays reversible;
// only the audio is final. CTA armed by the named checkbox only.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import ModalShell from './ModalShell.vue'

defineProps<{ path?: string }>()
const emit = defineEmits<{ cancel: []; confirm: [] }>()
const { t } = useI18n()
const consent = ref(false)
</script>

<template>
  <ModalShell width="520px" @close="emit('cancel')">
    <div class="body">
      <div class="head">
        <div class="glyph">⚠</div>
        <h3>{{ t('consent.irreversible.title') }}</h3>
      </div>
      <i18n-t tag="p" class="lead" keypath="consent.irreversible.lead">
        <template #volume>
          <b>{{ t('consent.irreversible.volume') }}</b>
        </template>
        <template #lost>
          <b class="danger">{{ t('consent.irreversible.lost') }}</b>
        </template>
      </i18n-t>
      <div v-if="path" class="path mono">{{ path }}</div>
      <div class="note">{{ t('consent.irreversible.reversibleNote') }}</div>
      <label class="consent">
        <input v-model="consent" type="checkbox" />
        <span>{{ t('consent.irreversible.checkbox') }}</span>
      </label>
      <div class="actions">
        <button class="btn-secondary" @click="emit('cancel')">{{ t('common.cancel') }}</button>
        <button class="confirm" :disabled="!consent" @click="emit('confirm')">
          {{ t('consent.irreversible.confirm') }}
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
  background: var(--danger-tint);
  border: 1px solid var(--danger-border);
  display: grid;
  place-content: center;
  font-size: 19px;
}
h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--danger-text);
  margin: 0;
}
.lead {
  color: var(--text-secondary-bright);
  font-size: 13.5px;
  margin: 13px 0 0;
  line-height: 1.55;
}
.lead .danger {
  color: var(--danger-text);
}
.path {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 11px 13px;
  margin-top: 13px;
  font-size: 12px;
  color: var(--text-secondary);
  word-break: break-all;
}
.mono {
  font-family: var(--font-mono);
}
.note {
  font-size: 12.5px;
  color: var(--text-muted-bright);
  margin-top: 11px;
  line-height: 1.5;
}
.consent {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  cursor: pointer;
  margin-top: 14px;
  background: rgba(247, 110, 110, 0.06);
  border: 1px solid rgba(247, 110, 110, 0.24);
  border-radius: 11px;
  padding: 13px 14px;
}
.consent input {
  accent-color: var(--danger);
  margin-top: 2px;
}
.consent span {
  font-size: 13px;
  color: var(--danger-text);
  font-weight: 600;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}
.confirm {
  background: rgba(247, 110, 110, 0.16);
  border: 1px solid rgba(247, 110, 110, 0.4);
  color: var(--danger-text);
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
