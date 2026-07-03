<script setup lang="ts">
// ReapplyEventModal (SPEC-DESIGN §6, SPEC-UNIFIED §11.2): delta preview —
// "added & ready" vs "added & missing" — for an applied event with pending
// additions. CTA = exact payload ("Ré-appliquer · N changement(s)", B10),
// RB-guarded. Only the delta is written; already-applied tracks untouched.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '../api/client'
import { useEventsStore } from '../stores/events'
import GuardedButton from './GuardedButton.vue'
import ModalShell from './ModalShell.vue'

const { t } = useI18n()
const events = useEventsStore()
const emit = defineEmits<{ close: []; applied: [] }>()
const submitting = ref(false)

// Delta = tracks added after the last apply, split by readiness.
const delta = computed(() => {
  const pending = (events.current?.tracks ?? []).filter((tk) => tk.added_after_apply === 1)
  return {
    ready: pending.filter((tk) => tk.status === 'ready' || tk.status === 'imported').length,
    missing: pending.filter((tk) => tk.status === 'missing').length,
    total: pending.length,
  }
})

async function confirm() {
  if (!events.current) return
  submitting.value = true
  try {
    await api.post(`/api/events/${events.current.id}/reapply`)
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
        <div class="glyph warn">↻</div>
        <h3>{{ t('events.reapply.title', { name: events.current.name }) }}</h3>
      </div>
      <p class="lede">{{ t('events.reapply.lede') }}</p>
      <div class="preview">
        <div class="prow">
          <span>{{ t('events.reapply.playlistUpdated') }}</span>
          <span class="mono ok">Event Imports › {{ events.current.name }}</span>
        </div>
        <div class="prow">
          <span>{{ t('events.reapply.addedReady') }}</span>
          <span class="mono ok">+{{ delta.ready }}</span>
        </div>
        <div v-if="delta.missing > 0" class="prow">
          <span>{{ t('events.reapply.addedMissing') }}</span>
          <span class="mono danger">+{{ delta.missing }}</span>
        </div>
      </div>
      <div class="note">{{ t('events.reapply.note') }}</div>
      <div class="actions">
        <button class="btn-ghost" @click="emit('close')">{{ t('common.cancel') }}</button>
        <GuardedButton
          :label="t('events.reapply.confirm', { n: delta.total })"
          tone="warning"
          :disabled="submitting || delta.total === 0"
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
.glyph.warn {
  background: var(--warning-tint);
  border: 1px solid var(--warning-border);
  color: var(--warning);
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
