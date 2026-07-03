<script setup lang="ts">
// DeleteEventModal (SPEC-DESIGN §6/§8, D11/D23, B10): the preview is the
// server's dry-run payload (empty body = preview); the destructive call
// sends {dry_run:false}. The confirmation text == the executed payload. The
// CTA carries the RB guard, re-checked at commit (D11/D23).
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '../api/client'
import { useEventsStore } from '../stores/events'
import GuardedButton from './GuardedButton.vue'
import ModalShell from './ModalShell.vue'

const { t } = useI18n()
const events = useEventsStore()
const emit = defineEmits<{ close: []; deleted: [] }>()

interface DeletePreview {
  tag_id: string | null
  contents: Array<{ content_id: string; title: string; action: string; reason: string }>
  playlists: Array<{ playlist_id: string; name: string }>
  artifacts: string[]
}

const preview = ref<DeletePreview | null>(null)
const loading = ref(true)
const submitting = ref(false)

onMounted(async () => {
  if (!events.current) return
  // empty body -> dry_run defaults to true (preview, zero writes)
  preview.value = await api.post<DeletePreview>(`/api/events/${events.current.id}/delete`)
  loading.value = false
})

async function confirm() {
  if (!events.current) return
  submitting.value = true
  try {
    // explicit destructive call; consent (428 permanent-delete) is handled
    // by the api client's global broker if a staging file needs it.
    await api.post(`/api/events/${events.current.id}/delete`, { dry_run: false })
    emit('deleted')
    emit('close')
  } finally {
    submitting.value = false
  }
}

const softDeleteCount = () =>
  preview.value?.contents.filter((c) => c.action === 'soft_delete').length ?? 0
</script>

<template>
  <ModalShell v-if="events.current" width="480px" @close="emit('close')">
    <div class="body">
      <div class="title-row">
        <div class="glyph danger">🗑</div>
        <h3 class="danger-title">{{ t('events.delete.title', { name: events.current.name }) }}</h3>
      </div>
      <p class="lede">{{ t('events.delete.lede') }}</p>

      <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
      <div v-else-if="preview" class="preview">
        <div class="prow">
          <span>{{ t('events.delete.smartPlaylist') }}</span>
          <span class="mono">{{ preview.playlists.length ? t('events.delete.removed') : '—' }}</span>
        </div>
        <div class="prow">
          <span>{{ t('events.delete.artifacts') }}</span>
          <span class="mono">{{ preview.artifacts.length }} {{ t('events.delete.files') }}</span>
        </div>
        <div class="prow">
          <span>{{ t('events.delete.eventOnlyTracks') }}</span>
          <span class="mono danger">{{ softDeleteCount() }}</span>
        </div>
        <div class="prow">
          <span>{{ t('events.delete.otherTags') }}</span>
          <span class="mono ok">{{ t('events.delete.kept') }}</span>
        </div>
      </div>

      <div class="note">{{ t('events.delete.note') }}</div>
      <div class="actions">
        <button class="btn-ghost" @click="emit('close')">{{ t('common.cancel') }}</button>
        <GuardedButton
          :label="t('events.delete.confirm')"
          tone="danger"
          :disabled="submitting || loading"
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
.glyph.danger {
  background: var(--danger-tint);
  border: 1px solid var(--danger-border);
  color: var(--danger-text);
}
h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}
.danger-title {
  color: var(--danger-text);
}
.lede {
  color: var(--text-muted-bright);
  font-size: 13px;
  margin: 11px 0 0;
  line-height: 1.5;
}
.loading {
  color: var(--text-muted-bright);
  font-size: 13px;
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
