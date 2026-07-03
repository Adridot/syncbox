<script setup lang="ts">
// ReMatchModal (SPEC-DESIGN §6, G2): shows the matcher's scored Rekordbox
// candidates (a candidate LIST, never a blind re-run) with confidence /
// duration / bitrate, plus a "mark as missing" escape. Confirming a
// candidate posts to /match (manual, confidence 100).
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '../api/client'
import type { LibraryTrack } from '../stores/library'
import ModalShell from './ModalShell.vue'

const { t } = useI18n()
const props = defineProps<{ track: LibraryTrack }>()
const emit = defineEmits<{ close: []; matched: [LibraryTrack]; missing: [LibraryTrack] }>()

interface Candidate {
  content_id: string
  title: string
  artist: string
  duration_ms: number | null
  bit_rate: number | null
  confidence: number
}

const candidates = ref<Candidate[]>([])
const selected = ref<string | null>(null)
const loading = ref(true)
const submitting = ref(false)

onMounted(async () => {
  const body = await api.get<{ candidates: Candidate[] }>(
    `/api/library/tracks/${props.track.id}/candidates`,
  )
  candidates.value = body.candidates
  selected.value = body.candidates[0]?.content_id ?? null
  loading.value = false
})

function duration(ms: number | null): string {
  if (!ms) return '—'
  const total = Math.round(ms / 1000)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

function confColor(confidence: number): string {
  if (confidence >= 82) return 'var(--accent)'
  if (confidence >= 60) return 'var(--warning-text)'
  return 'var(--text-muted-bright)'
}

async function confirm() {
  if (!selected.value) return
  submitting.value = true
  try {
    const updated = await api.post<LibraryTrack>(
      `/api/library/tracks/${props.track.id}/match`,
      { content_id: selected.value },
    )
    emit('matched', updated)
    emit('close')
  } finally {
    submitting.value = false
  }
}

async function markMissing() {
  // "Marquer comme manquant" — the escape hatch when no candidate fits.
  const updated = await api.post<LibraryTrack>(
    `/api/library/tracks/${props.track.id}/rematch`,
  )
  emit('matched', updated)
  emit('missing', updated)
  emit('close')
}

const title = computed(() => `${props.track.title} — ${props.track.artist}`)
</script>

<template>
  <ModalShell width="540px" @close="emit('close')">
    <div class="body">
      <h3>{{ t('library.rematch.title') }}</h3>
      <p class="lede">
        Spotify: <b>{{ title }}</b>. {{ t('library.rematch.lede') }}
      </p>

      <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
      <div v-else-if="!candidates.length" class="empty">{{ t('library.rematch.noCandidates') }}</div>

      <div v-else class="candidates">
        <label
          v-for="candidate in candidates"
          :key="candidate.content_id"
          class="candidate"
          :data-selected="selected === candidate.content_id"
        >
          <input v-model="selected" type="radio" :value="candidate.content_id" />
          <div class="cand-text">
            <div class="cand-title">{{ candidate.title }}</div>
            <div class="cand-meta">
              {{ candidate.artist }} · <span class="mono">{{ duration(candidate.duration_ms) }}</span>
              <template v-if="candidate.bit_rate">
                · <span class="mono">{{ candidate.bit_rate }} kbps</span></template
              >
            </div>
          </div>
          <span class="mono conf" :style="{ color: confColor(candidate.confidence) }">{{
            candidate.confidence
          }}</span>
        </label>
      </div>

      <div class="actions">
        <button class="btn-link" @click="markMissing">{{ t('library.rematch.markMissing') }}</button>
        <div class="right">
          <button class="btn-ghost" @click="emit('close')">{{ t('common.cancel') }}</button>
          <button class="btn-primary" :disabled="!selected || submitting" @click="confirm">
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
.lede {
  color: var(--text-muted-bright);
  font-size: 13px;
  margin: 5px 0 0;
}
.lede b {
  color: var(--text-secondary-bright);
}
.loading,
.empty {
  color: var(--text-muted-bright);
  font-size: 13px;
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
  align-items: center;
  gap: 10px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 11px 13px;
  cursor: pointer;
}
.candidate[data-selected='true'] {
  border-color: var(--accent-border);
  background: var(--accent-tint);
}
.cand-text {
  flex: 1;
  min-width: 0;
}
.cand-title {
  font-size: 13px;
  font-weight: 500;
}
.cand-meta {
  font-size: 12px;
  color: var(--text-muted-bright);
  margin-top: 2px;
}
.mono {
  font-family: var(--font-mono);
}
.conf {
  font-size: 13px;
  flex: none;
}
.actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-top: 18px;
}
.right {
  display: flex;
  gap: 10px;
}
.btn-link {
  background: transparent;
  border: none;
  color: var(--text-muted-bright);
  font-size: 12.5px;
  cursor: pointer;
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
.btn-primary {
  background: var(--accent);
  border: none;
  color: #06131f;
  padding: 9px 18px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.btn-primary:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
