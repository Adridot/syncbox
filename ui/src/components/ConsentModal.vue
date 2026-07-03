<script setup lang="ts">
// The 428 consent surface (SPEC-DESIGN §6/§8): AnlzReplaceModal (relink
// that replaces a file association — cues/beatgrid/waveform outside the
// backup) and IrreversibleDeleteModal (permanent audio delete on cloud/
// exFAT). Both require a NAMED consent checkbox BEFORE the action; the DB
// stays reversible either way. Rendered globally by App.vue from the
// consent store, driving the api client's per-call 428 loop.
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useConsentStore } from '../stores/consent'
import ModalShell from './ModalShell.vue'

const { t } = useI18n()
const consent = useConsentStore()
const agreed = ref(false)

// Queued 428s reuse this one modal instance (pending never goes null between
// them), so reset the named checkbox whenever the current request changes.
watch(
  () => consent.pending,
  () => {
    agreed.value = false
  },
)

function close() {
  consent.deny()
}
function confirm() {
  if (!agreed.value) return
  consent.grant()
}
</script>

<template>
  <ModalShell v-if="consent.pending" width="460px" @close="close">
    <div class="body">
      <div class="title-row">
        <div class="glyph">{{ consent.pending.kind === 'permanent_delete' ? '⚠' : '🎚' }}</div>
        <h3>
          {{
            consent.pending.kind === 'permanent_delete'
              ? t('consent.permanentTitle')
              : t('consent.anlzTitle')
          }}
        </h3>
      </div>
      <p class="warn">
        {{
          consent.pending.kind === 'permanent_delete'
            ? t('consent.permanentBody')
            : t('consent.anlzBody')
        }}
      </p>
      <p v-if="consent.pending.path" class="path mono">{{ consent.pending.path }}</p>
      <p class="reversible">{{ t('consent.reversible') }}</p>

      <label class="consent-check">
        <input v-model="agreed" type="checkbox" />
        <span>{{
          consent.pending.kind === 'permanent_delete'
            ? t('consent.permanentCheck')
            : t('consent.anlzCheck')
        }}</span>
      </label>

      <div class="actions">
        <button class="btn-ghost" @click="close">{{ t('common.cancel') }}</button>
        <button class="btn-danger" :disabled="!agreed" @click="confirm">
          {{ t('consent.proceed') }}
        </button>
      </div>
    </div>
  </ModalShell>
</template>

<style scoped>
.body {
  padding: 22px;
}
.title-row {
  display: flex;
  align-items: center;
  gap: 9px;
}
.glyph {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: var(--danger-tint);
  border: 1px solid var(--danger-border);
  color: var(--danger-text);
  display: grid;
  place-content: center;
  font-size: 18px;
  flex: none;
}
h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}
.warn {
  color: var(--text-secondary);
  font-size: 13px;
  margin: 12px 0 0;
  line-height: 1.5;
}
.path {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted-bright);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  margin-top: 10px;
  word-break: break-all;
}
.reversible {
  font-size: 12px;
  color: var(--text-muted-bright);
  margin-top: 10px;
}
.consent-check {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  margin-top: 14px;
  padding: 11px 13px;
  background: var(--danger-tint);
  border: 1px solid var(--danger-border);
  border-radius: 9px;
  font-size: 12.5px;
  color: var(--danger-text);
  cursor: pointer;
}
.consent-check input {
  accent-color: var(--danger);
  margin-top: 1px;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
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
.btn-danger {
  background: var(--danger);
  border: none;
  color: #06131f;
  padding: 9px 18px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.btn-danger:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
