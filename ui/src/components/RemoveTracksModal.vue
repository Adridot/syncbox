<script setup lang="ts">
// add-event-track-removal — the only destructive Rekordbox write reachable
// without deleting the event, so it follows DeleteEventModal's contract to
// the letter: preview first, execute echoing that plan VERBATIM (the object
// is passed straight back, never rebuilt), consent handled by the shared API
// client's 428 loop. The screen's job here is that nobody clicks confirm
// without having read what leaves Rekordbox and what lands in the trash.
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../api/client'
import type {
  EventRemovalAction,
  EventRemovalTrackPlan,
  EventSummary,
  EventTrackRemovalPlan,
} from '../api/types'
import { useJobsStore } from '../stores/jobs'
import { useStatusStore } from '../stores/status'
import ModalShell from './ModalShell.vue'

const props = defineProps<{ event: EventSummary; trackIds: number[] }>()
const emit = defineEmits<{ close: []; removed: [n: number] }>()
const { t, te } = useI18n()
const status = useStatusStore()
const jobs = useJobsStore()

const plan = ref<EventTrackRemovalPlan | null>(null)
const loadError = ref<string | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)

const path = `/api/events/${props.event.id}/tracks/remove`

// destructive first: what the user can still lose is what they must read
const actionOrder: EventRemovalAction[] = [
  'delete_with_event',
  'never_applied',
  'keep_in_place',
  'already_permanent',
]
/** A row whose group refused the removal comes back labelled 'keep_in_place',
    but nothing is untagged for it — its entry or its file is still held by a
    track staying in the event. It gets its own group: this dialog must never
    announce an act it will not perform. */
const isShared = (track: EventRemovalTrackPlan) => track.shared_with_kept_track === true
const groupedTracks = computed(() => {
  const tracks = plan.value?.tracks ?? []
  const groups = actionOrder
    .map((action) => ({
      action,
      tracks: tracks.filter((track) => track.action === action && !isShared(track)),
    }))
    .filter((group) => group.tracks.length > 0)
  const shared = tracks.filter(isShared)
  return shared.length ? [...groups, { action: 'shared_with_kept_track', tracks: shared }] : groups
})
const unresolved = computed(() => plan.value?.unresolved ?? [])
const trackCount = computed(() => plan.value?.tracks.length ?? 0)
const fileCount = computed(() => plan.value?.expected_file_deletions.length ?? 0)
const rbDeleteCount = computed(
  () => plan.value?.tracks.filter((track) => track.action === 'delete_with_event').length ?? 0,
)
// the guard applies only to a batch that actually writes to Rekordbox: a
// never-applied batch touches the app database alone
const rbBlocked = computed(() => Boolean(plan.value?.needs_rekordbox) && status.rbOpen)

/** The sidecar's option vocabulary is snake_case; show the sentence when we
    have one, the raw token rather than nothing when the contract grows. */
function optionLabel(option: string): string {
  const key = `events.remove.option.${option}`
  return te(key) ? t(key) : option
}

onMounted(async () => {
  try {
    plan.value = await api.post<EventTrackRemovalPlan>(path, {
      track_ids: props.trackIds,
      dry_run: true,
    })
  } catch (cause) {
    loadError.value = cause instanceof ApiError ? cause.message : t('common.networkError')
  }
})

async function confirm() {
  if (!plan.value) return
  busy.value = true
  error.value = null
  try {
    // consent_to_permanent_delete is added by the API client's 428 loop, so
    // the body stays byte-identical to the preview's plan
    await api.post(path, {
      track_ids: props.trackIds,
      dry_run: false,
      plan: plan.value,
    })
    emit('removed', trackCount.value)
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : t('common.networkError')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <ModalShell width="720px" @close="emit('close')">
    <div class="body">
      <div class="head">
        <div class="glyph">🗑</div>
        <h3>{{ t('events.remove.title', { name: event.name }) }}</h3>
      </div>
      <p class="lead">{{ t('events.remove.lead') }}</p>

      <div v-if="loadError" class="error-row">{{ loadError }}</div>
      <div v-else-if="!plan" class="hint">{{ t('common.loading') }}</div>
      <div v-else class="preview">
        <div class="summary">
          <div class="line">
            <span>{{ t('events.remove.untagLine') }}</span>
            <span class="mono">{{ trackCount }}</span>
          </div>
          <div class="line">
            <span>{{ t('events.remove.rbDeleteLine') }}</span>
            <span class="mono" :class="{ danger: rbDeleteCount > 0 }">{{ rbDeleteCount }}</span>
          </div>
          <div class="line">
            <span>{{ t('events.remove.trashLine') }}</span>
            <span class="mono" :class="{ danger: fileCount > 0 }">{{ fileCount }}</span>
          </div>
        </div>

        <section class="categories">
          <h4>{{ t('events.remove.tracksCount', trackCount) }}</h4>
          <div v-if="!plan.tracks.length" class="empty">{{ t('events.remove.noTracks') }}</div>
          <details
            v-for="group in groupedTracks"
            :key="group.action"
            class="category"
            :data-action="group.action"
            open
          >
            <summary>
              <span>{{ t(`events.remove.action.${group.action}`) }}</span>
              <span class="count">{{ group.tracks.length }}</span>
            </summary>
            <p class="category-help">{{ t(`events.remove.actionHelp.${group.action}`) }}</p>
            <div v-for="track in group.tracks" :key="track.track_id" class="compact-track">
              <div>
                <div class="track-title">{{ track.title || t('missing.untitled') }}</div>
                <div class="track-artist">{{ track.artist || '—' }}</div>
              </div>
              <span v-if="track.file_deleted" class="trash-flag">{{
                t('events.remove.trashFlag')
              }}</span>
            </div>
          </details>
        </section>

        <!-- blocking, not advisory: the batch cannot run while one remains -->
        <section v-if="unresolved.length" class="issues">
          <h4>{{ t('events.remove.unresolved', unresolved.length) }}</h4>
          <article v-for="issue in unresolved" :key="issue.id" class="issue">
            <div class="track-title">{{ issue.title || t('missing.untitled') }}</div>
            <div class="track-artist">{{ issue.artist || '—' }}</div>
            <p>
              {{
                te(`events.remove.issue.${issue.kind}`)
                  ? t(`events.remove.issue.${issue.kind}`, {
                      tags: issue.retaining_mytags.join(', ') || '—',
                    })
                  : issue.kind
              }}
            </p>
            <ul v-if="issue.resolution_options.length" class="options">
              <li v-for="option in issue.resolution_options" :key="option">
                {{ optionLabel(option) }}
              </li>
            </ul>
          </article>
        </section>

        <details class="technical">
          <summary>{{ t('events.remove.technicalDetails') }}</summary>
          <div v-for="track in plan.tracks" :key="track.track_id" class="technical-track">
            <div class="track-title">{{ track.title || t('missing.untitled') }}</div>
            <div class="mono path-item">
              #{{ track.track_id }} · {{ track.content_id || '—' }} ·
              {{ track.source_path || '—' }}
            </div>
          </div>
          <div
            v-for="file in plan.expected_file_deletions"
            :key="file"
            class="mono path-item danger"
          >
            {{ file }}
          </div>
        </details>
      </div>

      <div class="note">
        {{ plan?.needs_rekordbox === false ? t('events.remove.noteNoRb') : t('events.remove.note') }}
      </div>
      <div v-if="error" class="error-row">{{ error }}</div>
      <div class="actions">
        <button class="btn-secondary" @click="emit('close')">{{ t('common.cancel') }}</button>
        <button
          class="confirm"
          :disabled="rbBlocked || busy || jobs.jobRunning || !plan || unresolved.length > 0"
          @click="confirm"
        >
          <template v-if="rbBlocked">{{ t('rbGuard.blocked') }}</template>
          <template v-else-if="unresolved.length">{{ t('events.remove.resolveFirst') }}</template>
          <template v-else
            >{{ t('events.remove.confirmCount', trackCount)
            }}<template v-if="fileCount">
              · {{ t('events.remove.filesCount', fileCount) }}</template
            ></template
          >
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
.category[data-action='delete_with_event'] summary,
.category[data-action='delete_with_event'] .count {
  color: var(--danger-text);
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
.trash-flag {
  color: var(--danger-text);
  font-size: 11px;
  white-space: nowrap;
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
.options {
  margin: 7px 0 0;
  padding-left: 18px;
  color: var(--text-secondary-bright);
  font-size: 12px;
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
.path-item.danger {
  color: var(--danger-text);
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
