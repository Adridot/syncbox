<script setup lang="ts">
// Apply preview (SPEC-DESIGN §6): what the write will do, from the REAL
// track counts. Creates the smart playlist under "Event Imports" and tags
// ready tracks; missing tracks are skipped. RB guard re-checked on the CTA.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../api/client'
import type { EventSummary } from '../api/types'
import type { EventCounts } from '../lib/events'
import { useJobsStore } from '../stores/jobs'
import { useStatusStore } from '../stores/status'
import ModalShell from './ModalShell.vue'

const props = defineProps<{ event: EventSummary; counts: EventCounts }>()
const emit = defineEmits<{ close: []; applied: [] }>()
const { t } = useI18n()
const status = useStatusStore()
const jobs = useJobsStore()

const busy = ref(false)
const error = ref<string | null>(null)

async function confirm() {
  busy.value = true
  error.value = null
  try {
    await api.post(`/api/events/${props.event.id}/apply`)
    emit('applied')
  } catch (cause) {
    // B1: 423/409/… surfaced in place, never a silent no-op
    error.value = cause instanceof ApiError ? cause.message : t('common.networkError')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <ModalShell width="540px" @close="emit('close')">
    <div class="body">
      <div class="head">
        <div class="glyph">✓</div>
        <h3>{{ t('events.apply.title', { name: event.name }) }}</h3>
      </div>
      <i18n-t tag="p" class="lead" keypath="events.apply.lead">
        <template #parent>
          <b>Event Imports</b>
        </template>
      </i18n-t>
      <div class="preview">
        <div class="line">
          <span>{{ t('events.apply.playlistLine') }}</span>
          <span class="mono teal">{{ event.name }}</span>
        </div>
        <div class="line">
          <span>{{ t('events.apply.taggedLine', { tag: event.default_tag }) }}</span>
          <span class="mono">{{ counts.ready }}</span>
        </div>
        <div class="line">
          <span>{{ t('events.apply.missingLine') }}</span>
          <span class="mono danger">{{ counts.missing }}</span>
        </div>
      </div>
      <div class="note">{{ t('events.apply.backupNote') }}</div>
      <div v-if="error" class="error-row">{{ error }}</div>
      <div class="actions">
        <button class="btn-secondary" @click="emit('close')">{{ t('common.cancel') }}</button>
        <button
          class="confirm"
          :disabled="status.rbOpen || busy || jobs.jobRunning"
          @click="confirm"
        >
          {{ status.rbOpen ? t('rbGuard.blocked') : t('events.apply.confirm') }}
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
  gap: 9px;
}
.glyph {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: var(--success-tint);
  border: 1px solid var(--success-border);
  display: grid;
  place-content: center;
  font-size: 18px;
  color: var(--success);
}
h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}
.lead {
  color: var(--text-muted-bright);
  font-size: 13px;
  margin: 11px 0 0;
  line-height: 1.5;
}
.lead b {
  color: var(--text-secondary-bright);
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
.line {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--text-secondary);
}
.mono {
  font-family: var(--font-mono);
  color: var(--text-secondary-bright);
}
.mono.teal {
  color: #5fe0b0;
}
.mono.danger {
  color: var(--danger-text);
}
.note {
  font-size: 12px;
  color: var(--text-muted-bright);
  margin-top: 11px;
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
  margin-top: 18px;
}
.confirm {
  background: var(--success);
  border: none;
  color: #06131f;
  padding: 9px 18px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.confirm:disabled {
  opacity: 0.55;
  cursor: default;
}
</style>
