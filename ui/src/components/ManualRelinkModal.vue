<script setup lang="ts">
// ManualRelinkModal (SPEC-DESIGN §6, SPEC-UNIFIED §5.5): relink a missing
// COLLECTION track to a local file the user already lawfully owns. Shows
// scored candidates with duration/format metadata + "none of these". Relink
// replaces a file association, so cues/beatgrid may desync -> the sidecar
// returns 428 anlz_consent, handled by the global ConsentModal. RB-guarded.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../api/client'

const { t } = useI18n()
const props = defineProps<{
  contentId: string
  title: string
  candidates: Array<{ path: string; score: number; format: string; duration_s?: number }>
}>()
const emit = defineEmits<{ close: []; relinked: [] }>()

const selected = ref<string | null>(props.candidates[0]?.path ?? null)
const manualPath = ref('')
const submitting = ref(false)
const error = ref<string | null>(null)

async function relink() {
  const path = manualPath.value.trim() || selected.value
  if (!path) return
  submitting.value = true
  error.value = null
  try {
    // 428 anlz_consent is intercepted + re-called by the api client broker.
    await api.post(`/api/missing/collection/${props.contentId}/relink`, { path })
    emit('relinked')
    emit('close')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('missing.relink.failed')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div>
    <h3>{{ t('missing.relink.title') }}</h3>
    <p class="lede">{{ t('missing.relink.lede', { title }) }}</p>

    <div v-if="candidates.length" class="candidates">
      <label
        v-for="candidate in candidates"
        :key="candidate.path"
        class="candidate"
        :data-selected="selected === candidate.path"
      >
        <input v-model="selected" type="radio" :value="candidate.path" />
        <div class="cand-text">
          <div class="cand-path mono">{{ candidate.path }}</div>
          <div class="cand-meta">
            <span class="mono">{{ candidate.format }}</span>
            <template v-if="candidate.duration_s">
              · <span class="mono">{{ Math.round(candidate.duration_s) }}s</span></template
            >
          </div>
        </div>
        <span class="mono score">{{ candidate.score }}</span>
      </label>
    </div>
    <p v-else class="no-cand">{{ t('missing.relink.noCandidates') }}</p>

    <div class="manual">
      <div class="manual-label">{{ t('missing.relink.manualPath') }}</div>
      <input v-model="manualPath" class="input mono" :placeholder="t('missing.relink.pathPlaceholder')" />
    </div>

    <label class="none-of-these">
      <input type="radio" :checked="selected === null && !manualPath" @change="selected = null" />
      <span>{{ t('missing.relink.none') }}</span>
    </label>

    <div v-if="error" class="error-line">{{ error }}</div>

    <div class="actions">
      <button class="btn-ghost" @click="emit('close')">{{ t('common.cancel') }}</button>
      <button
        class="btn-primary"
        :disabled="submitting || (!selected && !manualPath.trim())"
        @click="relink"
      >
        {{ t('missing.relink.confirm') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}
.lede {
  color: var(--text-muted-bright);
  font-size: 13px;
  margin: 5px 0 0;
  line-height: 1.5;
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
.cand-path {
  font-size: 12px;
  color: var(--text-secondary-bright);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cand-meta {
  font-size: 11.5px;
  color: var(--text-muted-bright);
  margin-top: 2px;
}
.mono {
  font-family: var(--font-mono);
}
.score {
  font-size: 13px;
  color: var(--accent);
  flex: none;
}
.no-cand {
  color: var(--text-muted-bright);
  font-size: 13px;
  margin-top: 16px;
}
.manual {
  margin-top: 14px;
}
.manual-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.input {
  width: 100%;
  background: var(--surface-raised);
  border: 1px solid #2a3140;
  border-radius: 8px;
  padding: 9px 12px;
  color: var(--text-secondary-bright);
  font-size: 12.5px;
  outline: none;
}
.none-of-these {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-top: 12px;
  font-size: 12.5px;
  color: var(--text-muted-bright);
  cursor: pointer;
}
.error-line {
  color: var(--danger-text);
  font-size: 12.5px;
  margin-top: 12px;
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
