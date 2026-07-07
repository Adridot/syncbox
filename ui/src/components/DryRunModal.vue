<script setup lang="ts">
// Smart Fixes dry-run preview (§5.11): exact field-by-field before → after,
// composed final result, no no-op rows server-side — so an identical-looking
// row ALWAYS hides an invisible change: suspect whitespace is highlighted
// git-diff style with a legend (B4). The CTA carries the exact payload count
// (B10) and the RB guard; a 409 stale_snapshot flips the stale banner
// ("Relancer l'aperçu").
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { SmartFixesDryRun } from '../api/types'
import { dots, invisibleOnlyChange, markInvisible } from '../lib/whitespace'
import { useJobsStore } from '../stores/jobs'
import { useStatusStore } from '../stores/status'
import ModalShell from './ModalShell.vue'

const props = defineProps<{
  dry: SmartFixesDryRun
  stale: boolean
  busy: boolean
  error: string | null
}>()
const emit = defineEmits<{
  close: []
  execute: []
  rerun: []
}>()
const { t } = useI18n()
const status = useStatusStore()
const jobs = useJobsStore()

const hasInvisible = computed(() =>
  props.dry.payload.some((change) => invisibleOnlyChange(change.before, change.after)),
)
</script>

<template>
  <ModalShell width="640px" @close="emit('close')">
    <div class="body">
      <div class="head">
        <span class="dryrun-chip mono">DRY-RUN</span>
        <h3>{{ t('smartfixes.dryrun.title') }}</h3>
      </div>
      <i18n-t tag="p" class="lead" keypath="smartfixes.dryrun.lead">
        <template #exactly>
          <b>{{ t('smartfixes.dryrun.exactly') }}</b>
        </template>
      </i18n-t>

      <div class="rows">
        <div v-for="(change, index) in dry.payload" :key="index" class="change">
          <div class="change-head">
            <span class="field mono">{{ change.field }}</span>
          </div>
          <div class="diff">
            <span class="before mono">
              <template v-for="(segment, si) in markInvisible(change.before)" :key="si">
                <span v-if="segment.mark" class="ws-mark">{{ dots(segment.text) }}</span>
                <template v-else>{{ segment.text }}</template>
              </template>
            </span>
            <span class="arrow">→</span>
            <span class="after mono">
              <template v-for="(segment, si) in markInvisible(change.after)" :key="si">
                <span v-if="segment.mark" class="ws-mark">{{ dots(segment.text) }}</span>
                <template v-else>{{ segment.text }}</template>
              </template>
            </span>
          </div>
        </div>
        <div v-if="!dry.payload.length" class="rows-empty">
          {{ t('smartfixes.dryrun.nothing') }}
        </div>
      </div>

      <!-- B4 legend: the red dots ARE the change -->
      <div v-if="hasInvisible" class="ws-legend">
        <span class="ws-mark">·</span> {{ t('smartfixes.dryrun.wsLegend') }}
      </div>

      <div v-if="stale" class="stale">
        <span class="stale-glyph">⚠</span>
        <div class="stale-text">{{ t('smartfixes.dryrun.stale') }}</div>
        <button class="btn-secondary small" @click="emit('rerun')">
          {{ t('smartfixes.dryrun.rerun') }}
        </button>
      </div>

      <div v-if="error" class="error-row">{{ error }}</div>

      <div class="foot">
        <span class="summary mono">{{
          t('smartfixes.dryrun.summary', { n: dry.payload.length })
        }}</span>
        <div class="foot-actions">
          <button class="btn-secondary" @click="emit('close')">{{ t('common.cancel') }}</button>
          <button
            class="confirm"
            :disabled="status.rbOpen || busy || stale || jobs.jobRunning || !dry.payload.length"
            @click="emit('execute')"
          >
            {{
              status.rbOpen
                ? t('rbGuard.blocked')
                : t('smartfixes.dryrun.confirm', dry.payload.length)
            }}
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
.head {
  display: flex;
  align-items: center;
  gap: 9px;
}
.dryrun-chip {
  font-size: var(--size-meta);
  background: var(--teal-tint);
  color: var(--teal);
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid rgba(45, 212, 191, 0.25);
}
h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}
.lead {
  color: var(--text-muted-bright);
  font-size: 13px;
  margin: 7px 0 0;
  line-height: 1.5;
}
.lead b {
  color: var(--text-secondary-bright);
}
.rows {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-inner);
  margin-top: 15px;
  overflow: clip;
  max-height: 320px;
  overflow-y: auto;
}
.change {
  padding: 11px 14px;
  border-bottom: 1px solid var(--border-subtle);
}
.change-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.field {
  font-size: var(--size-label);
  color: var(--text-muted-bright);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.diff {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  flex-wrap: wrap;
}
.before {
  color: var(--danger-text);
  text-decoration: line-through;
  opacity: 0.85;
}
.arrow {
  color: var(--text-muted);
}
.after {
  color: #5fe0b0;
}
.mono {
  font-family: var(--font-mono);
}
.ws-mark {
  background: rgba(247, 110, 110, 0.35);
  color: #ffd7d7;
  border-radius: 3px;
  padding: 0 1px;
  text-decoration: none;
}
.rows-empty {
  padding: 22px;
  text-align: center;
  font-size: 12.5px;
  color: var(--text-muted);
}
.ws-legend {
  margin-top: 10px;
  font-size: var(--size-meta);
  color: var(--text-muted-bright);
}
.stale {
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(245, 181, 68, 0.09);
  border: 1px solid rgba(245, 181, 68, 0.3);
  border-radius: var(--radius-inner);
  padding: 12px 14px;
  margin-top: 14px;
}
.stale-glyph {
  font-size: 15px;
  color: var(--warning);
}
.stale-text {
  flex: 1;
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.5;
}
.btn-secondary.small {
  padding: 5px 10px;
  font-size: 12px;
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
.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 18px;
}
.summary {
  font-size: 12px;
  color: var(--text-muted-bright);
}
.foot-actions {
  display: flex;
  gap: 10px;
}
.confirm {
  background: var(--teal);
  border: none;
  color: #06131f;
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
