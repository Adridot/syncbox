<script setup lang="ts">
// The destructive request echoes the complete displayed plan so execution
// cannot silently diverge from the preview. Consent retries preserve it via
// the shared API client.
import { onMounted, ref } from 'vue'
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

async function confirm() {
  if (!preview.value) return
  busy.value = true
  error.value = null
  try {
    await api.post(`/api/events/${props.event.id}/delete`, {
      dry_run: false,
      plan: preview.value,
    })
    emit('deleted')
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : t('common.networkError')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <ModalShell width="760px" @close="emit('close')">
    <div class="body">
      <div class="head">
        <div class="glyph">🗑</div>
        <h3>{{ t('events.del.title', { name: event.name }) }}</h3>
      </div>
      <p class="lead">{{ t('events.del.lead') }}</p>

      <div v-if="loadError" class="error-row">{{ loadError }}</div>
      <div v-else-if="!preview" class="hint">{{ t('common.loading') }}</div>
      <div v-else class="preview">
        <div class="summary">
          <div class="line">
            <span>{{ t('events.del.tagLine') }}</span>
            <span class="mono">{{
              preview.tag_id ? `${event.default_tag} · ${preview.tag_id}` : '—'
            }}</span>
          </div>
          <div class="line">
            <span>{{ t('events.del.playlistLine') }}</span>
            <span class="mono">{{
              preview.playlists.length
                ? preview.playlists.map((playlist) => playlist.name).join(', ')
                : '—'
            }}</span>
          </div>
          <div class="line">
            <span>{{ t('events.del.expectedDeletions') }}</span>
            <span class="mono danger">{{
              t('events.del.filesCount', preview.expected_file_deletions.length)
            }}</span>
          </div>
        </div>

        <section class="tracks">
          <h4>{{ t('events.del.tracksCount', preview.tracks.length) }}</h4>
          <div v-if="!preview.tracks.length" class="empty">{{ t('events.del.noTracks') }}</div>
          <article
            v-for="track in preview.tracks"
            :key="track.content_id"
            class="track"
            :data-action="track.action"
          >
            <div class="track-head">
              <div>
                <div class="track-title">{{ track.title || t('missing.untitled') }}</div>
                <div class="track-artist">{{ track.artist || '—' }}</div>
              </div>
              <span class="action" :data-action="track.action">{{
                t(`events.del.action.${track.action}`)
              }}</span>
            </div>
            <dl class="track-grid">
              <div class="field wide">
                <dt>{{ t('events.del.sourcePath') }}</dt>
                <dd class="mono path">{{ track.source_path || '—' }}</dd>
              </div>
              <div class="field">
                <dt>{{ t('ownership.label') }}</dt>
                <dd :data-ownership="track.ownership">{{
                  t(`ownership.${track.ownership}`)
                }}</dd>
              </div>
              <div class="field">
                <dt>{{ t('events.del.retainingTags') }}</dt>
                <dd>{{
                  track.retaining_mytags.length
                    ? track.retaining_mytags.join(', ')
                    : t('events.del.noRetainingTags')
                }}</dd>
              </div>
              <div v-if="track.destination_path" class="field wide">
                <dt>{{ t('events.del.destinationPath') }}</dt>
                <dd class="mono path">{{ track.destination_path }}</dd>
              </div>
              <div class="field wide">
                <dt>{{ t('events.del.anlz') }}</dt>
                <dd :data-anlz-update="track.anlz_update_required">{{
                  track.anlz_update_required
                    ? t('events.del.anlzRequired')
                    : t('events.del.anlzUnchanged')
                }}</dd>
              </div>
            </dl>
          </article>
        </section>

        <div class="artifacts">
          <details>
            <summary>
              {{ t('events.del.xmlArtifacts') }} ·
              {{ t('events.del.filesCount', preview.xml_artifacts.length) }}
            </summary>
            <div v-if="!preview.xml_artifacts.length" class="empty">—</div>
            <div v-for="path in preview.xml_artifacts" :key="path" class="mono path-item">
              {{ path }}
            </div>
          </details>
          <details>
            <summary>
              {{ t('events.del.stagingArtifacts') }} ·
              {{ t('events.del.filesCount', preview.staging_artifacts.length) }}
            </summary>
            <div v-if="!preview.staging_artifacts.length" class="empty">—</div>
            <div v-for="path in preview.staging_artifacts" :key="path" class="mono path-item">
              {{ path }}
            </div>
          </details>
          <details :open="preview.expected_file_deletions.length > 0">
            <summary>
              {{ t('events.del.expectedDeletions') }} ·
              {{ t('events.del.filesCount', preview.expected_file_deletions.length) }}
            </summary>
            <div v-if="!preview.expected_file_deletions.length" class="empty">—</div>
            <div
              v-for="path in preview.expected_file_deletions"
              :key="path"
              class="mono path-item danger"
            >
              {{ path }}
            </div>
          </details>
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
  margin-top: 13px;
  font-size: 13px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.summary,
.tracks,
.artifacts {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
}
.summary {
  padding: 13px;
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
.mono.danger {
  color: var(--danger-text);
}
.tracks {
  padding: 13px;
}
h4 {
  margin: 0 0 9px;
  color: var(--text-secondary-bright);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.track {
  border: 1px solid var(--border-subtle-2);
  border-radius: 8px;
  padding: 11px;
}
.track + .track {
  margin-top: 8px;
}
.track-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.track-title {
  color: var(--text-primary);
  font-weight: 600;
}
.track-artist {
  color: var(--text-muted-bright);
  font-size: 12px;
  margin-top: 2px;
}
.action {
  border: 1px solid var(--neutral-border);
  border-radius: 6px;
  background: var(--neutral-tint);
  color: var(--text-secondary-bright);
  font-size: 11px;
  font-weight: 600;
  padding: 3px 7px;
  white-space: nowrap;
}
.action[data-action='migrate_to_collection'] {
  border-color: var(--accent-border);
  background: var(--accent-tint);
  color: var(--accent-hover);
}
.action[data-action='delete_with_event'] {
  border-color: var(--danger-border);
  background: var(--danger-tint);
  color: var(--danger-text);
}
.track-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 14px;
  margin: 10px 0 0;
}
.field {
  min-width: 0;
}
.field.wide {
  grid-column: 1 / -1;
}
dt {
  color: var(--text-muted);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
dd {
  color: var(--text-secondary-bright);
  font-size: 11.5px;
  margin: 2px 0 0;
}
.path {
  overflow-wrap: anywhere;
}
.artifacts {
  padding: 4px 13px;
}
details {
  padding: 9px 0;
  border-bottom: 1px solid var(--border-subtle);
}
details:last-child {
  border-bottom: none;
}
summary {
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
}
.path-item {
  font-size: 11px;
  overflow-wrap: anywhere;
  padding: 7px 0 0 16px;
}
.empty {
  color: var(--text-muted);
  font-size: 12px;
  padding-top: 4px;
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
