<script setup lang="ts">
// Re-apply delta preview (§11.2): ONLY the pending additions are written;
// the smart playlist / MyTag are updated, never duplicated. CTA carries the
// exact change count (B10 safety) and the RB guard.
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
    await api.post(`/api/events/${props.event.id}/reapply`)
    emit('applied')
  } catch (cause) {
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
        <div class="glyph">↻</div>
        <h3>{{ t('events.reapply.title', { name: event.name }) }}</h3>
      </div>
      <i18n-t tag="p" class="lead" keypath="events.reapply.lead">
        <template #delta>
          <b>{{ t('events.reapply.deltaWord') }}</b>
        </template>
      </i18n-t>
      <div class="preview">
        <div class="line">
          <span>{{ t('events.reapply.playlistLine') }}</span>
          <span class="mono teal">{{ event.name }}</span>
        </div>
        <div class="line">
          <span>{{ t('events.reapply.readyLine') }}</span>
          <span class="mono teal">+{{ counts.pendReady }}</span>
        </div>
        <div v-if="counts.pendMissing" class="line">
          <span>{{ t('events.reapply.missingLine') }}</span>
          <span class="mono danger">+{{ counts.pendMissing }}</span>
        </div>
      </div>
      <div class="note">{{ t('events.reapply.note') }}</div>
      <div v-if="error" class="error-row">{{ error }}</div>
      <div class="actions">
        <button class="btn-secondary" @click="emit('close')">{{ t('common.cancel') }}</button>
        <button
          class="confirm"
          :disabled="status.rbOpen || busy || jobs.jobRunning"
          @click="confirm"
        >
          {{
            status.rbOpen
              ? t('rbGuard.blocked')
              : t('events.reapply.confirm', counts.pendReady)
          }}
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
  background: var(--warning-tint);
  border: 1px solid var(--warning-border);
  display: grid;
  place-content: center;
  font-size: 18px;
  color: var(--warning);
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
  opacity: 0.55;
  cursor: default;
}
</style>
