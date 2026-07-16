<script setup lang="ts">
// The destructive request echoes the complete displayed plan so execution
// cannot silently diverge from the preview. Consent retries preserve it via
// the shared API client.
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

const actionOrder = [
  'delete_with_event',
  'migrate_to_collection',
  'keep_in_place',
  'already_permanent',
] as const
const groupedTracks = computed(() =>
  actionOrder
    .map((action) => ({
      action,
      tracks: preview.value?.tracks.filter((track) => track.action === action) ?? [],
    }))
    .filter((group) => group.tracks.length > 0),
)
const unresolved = computed(() => preview.value?.unresolved ?? [])
const deleteCount = computed(
  () => preview.value?.tracks.filter((track) => track.action === 'delete_with_event').length ?? 0,
)

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

        <section class="categories">
          <h4>{{ t('events.del.tracksCount', preview.tracks.length) }}</h4>
          <div v-if="!preview.tracks.length" class="empty">
            {{ t('events.del.noTracks') }}
          </div>
          <details
            v-for="group in groupedTracks"
            :key="group.action"
            class="category"
            :data-action="group.action"
          >
            <summary>
              <span>{{ t(`events.del.action.${group.action}`) }}</span>
              <span class="count">{{ group.tracks.length }}</span>
            </summary>
            <p class="category-help">
              {{ t(`events.del.actionHelp.${group.action}`) }}
            </p>
            <div v-for="track in group.tracks" :key="track.content_id" class="compact-track">
              <div>
                <div class="track-title">
                  {{ track.title || t('missing.untitled') }}
                </div>
                <div class="track-artist">{{ track.artist || '—' }}</div>
              </div>
              <span v-if="track.retaining_mytags.length" class="tags">
                {{ track.retaining_mytags.join(', ') }}
              </span>
            </div>
          </details>
        </section>

        <section v-if="unresolved.length" class="issues">
          <h4>{{ t('events.del.unresolved', unresolved.length) }}</h4>
          <article v-for="issue in unresolved" :key="issue.id" class="issue">
            <div class="track-title">
              {{ issue.title || t('missing.untitled') }}
            </div>
            <div class="track-artist">{{ issue.artist || '—' }}</div>
            <p>{{ t(`events.del.issue.${issue.kind}`) }}</p>
          </article>
        </section>

        <details class="technical">
          <summary>{{ t('events.del.technicalDetails') }}</summary>
          <div v-for="track in preview.tracks" :key="track.content_id" class="technical-track">
            <div class="track-title">
              {{ track.title || t('missing.untitled') }}
            </div>
            <div class="mono path-item">
              {{ track.content_id }} · {{ track.source_path || '—' }}
            </div>
            <div v-if="track.destination_path" class="mono path-item">
              → {{ track.destination_path }}
            </div>
            <div class="path-item">
              {{
                track.anlz_update_required
                  ? t('events.del.anlzRequired')
                  : t('events.del.anlzUnchanged')
              }}
            </div>
          </div>
          <div
            v-for="path in preview.expected_file_deletions"
            :key="path"
            class="mono path-item danger"
          >
            {{ path }}
          </div>
        </details>
      </div>
      <div class="note">{{ t('events.del.note') }}</div>
      <div v-if="error" class="error-row">{{ error }}</div>
      <div class="actions">
        <button class="btn-secondary" @click="emit('close')">
          {{ t('common.cancel') }}
        </button>
        <button
          class="confirm"
          :disabled="status.rbOpen || busy || jobs.jobRunning || !preview || unresolved.length > 0"
          @click="confirm"
        >
          {{
            status.rbOpen
              ? t('rbGuard.blocked')
              : unresolved.length
                ? t('events.del.resolveFirst')
                : t('events.del.confirmCount', deleteCount)
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
.categories,
.issues,
.technical {
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
.categories,
.issues {
  padding: 13px;
}
h4 {
  margin: 0 0 9px;
  color: var(--text-secondary-bright);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
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
.path {
  overflow-wrap: anywhere;
}
.category {
  padding: 9px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.category:last-child {
  border-bottom: none;
}
.category summary,
.technical summary {
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
}
.category summary {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-weight: 600;
}
.count {
  color: var(--text-primary);
  font-family: var(--font-mono);
}
.category[data-action='delete_with_event'] .count {
  color: var(--danger-text);
}
.category[data-action='migrate_to_collection'] .count {
  color: var(--accent-hover);
}
.category-help {
  color: var(--text-muted);
  font-size: 11.5px;
  margin: 8px 0;
}
.compact-track {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
  border-top: 1px solid var(--border-subtle);
}
.tags {
  color: var(--text-muted-bright);
  font-size: 11px;
  text-align: right;
}
.issue {
  border: 1px solid var(--danger-border);
  background: var(--danger-tint);
  border-radius: 8px;
  padding: 10px;
}
.issue + .issue {
  margin-top: 8px;
}
.issue p {
  color: var(--danger-text);
  font-size: 12px;
  margin: 7px 0 0;
}
.technical {
  padding: 10px 13px;
}
.technical-track {
  padding: 10px 0;
  border-bottom: 1px solid var(--border-subtle);
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
