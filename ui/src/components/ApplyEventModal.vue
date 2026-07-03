<script setup lang="ts">
// ApplyEventModal (SPEC-DESIGN §6): preview of the smart-playlist write,
// built from the event's current ready/missing counts. Distinct from the
// delete preview. CTA carries the RB guard (GuardedButton). Apply has no
// server dry-run — the counts ARE the exact plan.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '../api/client'
import { useEventsStore } from '../stores/events'
import GuardedButton from './GuardedButton.vue'
import ModalShell from './ModalShell.vue'

const { t } = useI18n()
const events = useEventsStore()
const emit = defineEmits<{ close: []; applied: [] }>()
const submitting = ref(false)

async function confirm() {
  if (!events.current) return
  submitting.value = true
  try {
    await api.post(`/api/events/${events.current.id}/apply`)
    await events.reload()
    emit('applied')
    emit('close')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <ModalShell v-if="events.current" width="480px" @close="emit('close')">
    <div class="body">
      <div class="title-row">
        <div class="glyph success">✓</div>
        <h3>{{ t('events.apply.title', { name: events.current.name }) }}</h3>
      </div>
      <p class="lede">{{ t('events.apply.lede') }}</p>
      <div class="preview">
        <div class="prow">
          <span>{{ t('events.apply.playlist') }}</span>
          <span class="mono ok">Event Imports › {{ events.current.name }}</span>
        </div>
        <div class="prow">
          <span>{{ t('events.apply.tagged', { tag: events.current.default_tag }) }}</span>
          <span class="mono">{{ events.counts.ready }}</span>
        </div>
        <div class="prow">
          <span>{{ t('events.apply.missingIgnored') }}</span>
          <span class="mono danger">{{ events.counts.missing }}</span>
        </div>
      </div>
      <div class="note">{{ t('events.apply.note') }}</div>
      <div class="actions">
        <button class="btn-ghost" @click="emit('close')">{{ t('common.cancel') }}</button>
        <GuardedButton
          :label="t('events.apply.confirm')"
          tone="primary"
          :disabled="submitting"
          @click="confirm"
        />
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
  display: grid;
  place-content: center;
  font-size: 18px;
  flex: none;
}
.glyph.success {
  background: var(--success-tint);
  border: 1px solid var(--success-border);
  color: var(--success);
}
h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}
.lede {
  color: var(--text-muted-bright);
  font-size: 13px;
  margin: 11px 0 0;
  line-height: 1.5;
}
.preview {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 13px;
  margin-top: 13px;
  font-size: 13px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.prow {
  display: flex;
  justify-content: space-between;
  color: var(--text-secondary);
}
.mono {
  font-family: var(--font-mono);
  color: var(--text-secondary-bright);
}
.ok {
  color: #5fe0b0;
}
.danger {
  color: var(--danger-text);
}
.note {
  font-size: 12px;
  color: var(--text-muted-bright);
  margin-top: 11px;
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
</style>
