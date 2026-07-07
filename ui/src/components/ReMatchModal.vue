<script setup lang="ts">
// Manual re-match (SPEC-DESIGN §4/§6 — the FIRST-intention matching tool):
// G2 scored candidates with confidence/duration/bitrate, radio selection,
// confirm = manual match; "Marquer comme manquant" is the escape when none
// fits. Every backend failure is surfaced (B1).
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../api/client'
import type { LibraryTrack, MatchCandidate } from '../api/types'
import { confTone, formatDuration } from '../lib/library'
import { useSettingsStore } from '../stores/settings'
import ModalShell from './ModalShell.vue'

const props = defineProps<{ track: LibraryTrack }>()
const emit = defineEmits<{ close: []; updated: [track: LibraryTrack] }>()
const { t } = useI18n()
const settings = useSettingsStore()

const candidates = ref<MatchCandidate[] | null>(null)
const selected = ref<string | null>(null)
const loadError = ref<string | null>(null)
const actionError = ref<string | null>(null)
const busy = ref(false)

const threshold = computed(() => settings.values?.match_confidence_threshold ?? 82)

onMounted(async () => {
  try {
    const body = await api.get<{ candidates: MatchCandidate[] }>(
      `/api/library/tracks/${props.track.id}/candidates`,
    )
    candidates.value = body.candidates
    selected.value = body.candidates[0]?.content_id ?? null
  } catch (cause) {
    loadError.value = cause instanceof ApiError ? cause.message : t('common.networkError')
    candidates.value = []
  }
})

async function act(request: () => Promise<LibraryTrack>) {
  busy.value = true
  actionError.value = null
  try {
    emit('updated', await request())
  } catch (cause) {
    actionError.value = cause instanceof ApiError ? cause.message : t('common.networkError')
  } finally {
    busy.value = false
  }
}

const confirm = () =>
  act(() =>
    api.post<LibraryTrack>(`/api/library/tracks/${props.track.id}/match`, {
      content_id: selected.value,
    }),
  )
const markMissing = () => act(() => api.post<LibraryTrack>(`/api/library/tracks/${props.track.id}/missing`))
</script>

<template>
  <ModalShell width="560px" @close="emit('close')">
    <div class="body">
      <h3>{{ t('library.rematch.title') }}</h3>
      <i18n-t tag="p" class="sub" keypath="library.rematch.sub">
        <template #track>
          <b>{{ track.title }} — {{ track.artist }}</b>
        </template>
      </i18n-t>

      <div v-if="candidates === null" class="hint">{{ t('common.loading') }}</div>
      <div v-else-if="loadError" class="error-row">{{ loadError }}</div>
      <div v-else-if="!candidates.length" class="hint">{{ t('library.rematch.noCandidates') }}</div>
      <div v-else class="candidates">
        <label
          v-for="candidate in candidates"
          :key="candidate.content_id"
          class="candidate"
          :data-active="selected === candidate.content_id"
        >
          <input v-model="selected" type="radio" name="rematch" :value="candidate.content_id" />
          <span class="cand-text">
            <span class="cand-title">{{ candidate.title }}</span>
            <span class="cand-meta"
              >{{ candidate.artist }} · <span class="mono">{{ formatDuration(candidate.duration_ms) }}</span>
              <template v-if="candidate.bit_rate">
                · <span class="mono">{{ candidate.bit_rate }} kbps</span></template
              ></span
            >
          </span>
          <span class="conf mono" :data-tone="confTone(candidate.confidence, threshold)"
            >{{ candidate.confidence }}</span
          >
        </label>
      </div>

      <div v-if="actionError" class="error-row">{{ actionError }}</div>

      <div class="actions">
        <button class="escape" :disabled="busy" @click="markMissing">
          {{ t('library.rematch.markMissing') }}
        </button>
        <div class="actions-right">
          <button class="btn-secondary" @click="emit('close')">{{ t('common.cancel') }}</button>
          <button class="btn-primary" :disabled="busy || !selected" @click="confirm">
            {{ t('library.rematch.confirm') }}
          </button>
        </div>
      </div>
    </div>
  </ModalShell>
</template>

<style scoped>
.body {
  padding: 22px;
}
h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}
.sub {
  color: var(--text-muted-bright);
  font-size: 13px;
  margin: 5px 0 0;
}
.sub b {
  color: var(--text-secondary-bright);
  font-weight: 600;
}
.hint {
  color: var(--text-muted);
  font-size: 12.5px;
  margin-top: 16px;
}
.candidates {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.candidate {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--surface);
  cursor: pointer;
}
.candidate[data-active='true'] {
  border-color: var(--accent-border);
  background: rgba(77, 163, 255, 0.06);
}
.candidate input {
  accent-color: var(--accent);
  margin-top: 2px;
}
.cand-text {
  flex: 1;
  min-width: 0;
}
.cand-title {
  display: block;
  font-size: 13px;
  font-weight: 500;
}
.cand-meta {
  display: block;
  font-size: 12px;
  color: var(--text-muted-bright);
  margin-top: 1px;
}
.conf {
  font-size: 13px;
}
.conf[data-tone='success'] {
  color: var(--success);
}
.conf[data-tone='accent'] {
  color: var(--accent);
}
.conf[data-tone='warning'] {
  color: var(--warning);
}
.mono {
  font-family: var(--font-mono);
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
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-top: 18px;
}
.escape {
  background: transparent;
  border: none;
  color: var(--text-muted-bright);
  font-size: 12.5px;
  cursor: pointer;
  padding: 0;
}
.escape:hover {
  color: var(--danger-text);
}
.actions-right {
  display: flex;
  gap: 10px;
}
</style>
