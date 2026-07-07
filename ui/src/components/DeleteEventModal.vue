<script setup lang="ts">
// Delete-event preview (D11/D23): the preview IS the API's dry-run payload
// (an empty body is a preview server-side; the destructive call sends
// dry_run:false explicitly). The confirmation text reflects the exact
// executed payload (B10) and the CTA carries the RB guard — like apply.
// A 428 permanent-delete consent (cloud/exFAT staging) flows through the
// global ConsentHost broker.
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../api/client'
import type { EventDeletePreview, EventSummary } from '../api/types'
import { useJobsStore } from '../stores/jobs'
import { useStatusStore } from '../stores/status'
import ModalShell from './ModalShell.vue'

const props = defineProps<{ event: EventSummary }>()
const emit = defineEmits<{ close: []; deleted: [] }>()
const { t } = useI18n()
const status = useStatusStore()
const jobs = useJobsStore()

const preview = ref<EventDeletePreview | null>(null)
const loadError = ref<string | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    preview.value = await api.post<EventDeletePreview>(`/api/events/${props.event.id}/delete`, {})
  } catch (cause) {
    loadError.value = cause instanceof ApiError ? cause.message : t('common.networkError')
  }
})

const softDeleted = computed(
  () => preview.value?.contents.filter((entry) => entry.action === 'soft_delete').length ?? 0,
)
const kept = computed(
  () => preview.value?.contents.filter((entry) => entry.action === 'keep').length ?? 0,
)

async function confirm() {
  busy.value = true
  error.value = null
  try {
    await api.post(`/api/events/${props.event.id}/delete`, { dry_run: false })
    emit('deleted')
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
        <div class="glyph">🗑</div>
        <h3>{{ t('events.del.title', { name: event.name }) }}</h3>
      </div>
      <p class="lead">{{ t('events.del.lead') }}</p>

      <div v-if="loadError" class="error-row">{{ loadError }}</div>
      <div v-else-if="!preview" class="hint">{{ t('common.loading') }}</div>
      <div v-else class="preview">
        <div class="line">
          <span>{{ t('events.del.playlistLine') }}</span>
          <span class="mono">{{
            preview.playlists.length ? t('events.del.removed') : '—'
          }}</span>
        </div>
        <div class="line">
          <span>{{ t('events.del.artifactsLine') }}</span>
          <span class="mono">{{ t('events.del.filesCount', preview.artifacts.length) }}</span>
        </div>
        <div class="line">
          <span>{{ t('events.del.softDeleteLine') }}</span>
          <span class="mono danger">{{ softDeleted }}</span>
        </div>
        <div class="line">
          <span>{{ t('events.del.keptLine') }}</span>
          <span class="mono teal">{{ kept }}</span>
        </div>
      </div>
      <div class="note">{{ t('events.del.note') }}</div>
      <div v-if="error" class="error-row">{{ error }}</div>
      <div class="actions">
        <button class="btn-secondary" @click="emit('close')">{{ t('common.cancel') }}</button>
        <button
          class="confirm"
          :disabled="status.rbOpen || busy || jobs.jobRunning || !preview"
          @click="confirm"
        >
          {{ status.rbOpen ? t('rbGuard.blocked') : t('events.del.confirm') }}
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
  background: var(--danger-tint);
  border: 1px solid var(--danger-border);
  display: grid;
  place-content: center;
  font-size: 18px;
}
h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
  color: var(--danger-text);
}
.lead {
  color: var(--text-muted-bright);
  font-size: 13px;
  margin: 11px 0 0;
}
.hint {
  color: var(--text-muted);
  font-size: 12.5px;
  margin-top: 13px;
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
  opacity: 0.55;
  cursor: default;
}
</style>
