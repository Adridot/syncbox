<script setup lang="ts">
// Manual relink (SPEC-DESIGN §6 / §5.5): local candidates with score,
// duration and format metadata, plus the explicit "none of these" escape.
// The caller performs the actual write (collection relink 428-ANLZ flows
// through the global consent broker) or the §5.5 status transition.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { MissingEntry } from '../api/types'
import { useStatusStore } from '../stores/status'
import ModalShell from './ModalShell.vue'

const props = defineProps<{ entry: MissingEntry; busy?: boolean; error?: string | null }>()
const emit = defineEmits<{ close: []; pick: [path: string]; none: [] }>()
const { t } = useI18n()
const status = useStatusStore()

const selected = ref<string | null>(props.entry.relink_candidates[0]?.path ?? null)
// a COLLECTION relink writes master.db (FolderPath re-association) — the
// CTA reflects the RB guard like every mutation CTA (§8); app-scope
// transitions are app-DB only and stay available
const rbBlocked = computed(() => props.entry.scope === 'collection' && status.rbOpen)

function formatDuration(seconds?: number): string {
  if (!seconds) return ''
  const total = Math.round(seconds)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}
</script>

<template>
  <ModalShell width="600px" @close="emit('close')">
    <div class="body">
      <h3>{{ t('relink.title') }}</h3>
      <i18n-t tag="p" class="sub" keypath="relink.sub">
        <template #track>
          <b>{{ entry.title }}<template v-if="entry.artist"> — {{ entry.artist }}</template></b>
        </template>
      </i18n-t>

      <div v-if="!entry.relink_candidates.length" class="hint">
        {{ t('relink.noCandidates') }}
      </div>
      <div v-else class="candidates">
        <label
          v-for="candidate in entry.relink_candidates"
          :key="candidate.path"
          class="candidate"
          :data-active="selected === candidate.path"
        >
          <input v-model="selected" type="radio" name="relink" :value="candidate.path" />
          <span class="cand-text">
            <span class="cand-path mono">{{ candidate.path }}</span>
            <span class="cand-meta">
              <span class="mono">{{ candidate.format.toUpperCase() }}</span>
              <template v-if="candidate.duration_s">
                · <span class="mono">{{ formatDuration(candidate.duration_s) }}</span>
              </template>
            </span>
          </span>
          <span class="score mono">{{ candidate.score }}</span>
        </label>
      </div>

      <div v-if="error" class="error-row">{{ error }}</div>

      <div class="actions">
        <button class="escape" @click="emit('none')">{{ t('relink.none') }}</button>
        <div class="actions-right">
          <button class="btn-secondary" @click="emit('close')">{{ t('common.cancel') }}</button>
          <button
            class="btn-primary"
            :disabled="busy || !selected || rbBlocked"
            @click="selected && emit('pick', selected)"
          >
            {{ rbBlocked ? t('rbGuard.blocked') : busy ? t('relink.linking') : t('relink.confirm') }}
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
}
.hint {
  color: var(--text-muted);
  font-size: 12.5px;
  margin-top: 16px;
  line-height: 1.5;
}
.candidates {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 280px;
  overflow-y: auto;
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
.cand-text,
.score {
  -webkit-user-select: text;
  user-select: text;
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
.cand-path {
  display: block;
  font-size: 12px;
  color: var(--text-secondary-bright);
  word-break: break-all;
}
.cand-meta {
  display: block;
  font-size: var(--size-meta);
  color: var(--text-muted);
  margin-top: 2px;
}
.score {
  font-size: 13px;
  color: var(--accent);
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
  color: var(--accent-hover);
}
.actions-right {
  display: flex;
  gap: 10px;
}
</style>
