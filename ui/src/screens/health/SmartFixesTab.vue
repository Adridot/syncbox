<script setup lang="ts">
// Smart Fixes (§5.11): the catalog is FIXED server-side — the families are
// descriptive text, not options (M4-PLAN §1.4). Strict dry-run → confirm →
// mutate; the dry-run reads the snapshot only (RB may be open), the execute
// is RB-guarded and re-asserts freshness (409 → stale banner in the modal).
// Smart Fixes are metadata-only behind an automatic backup. Ownership does
// not change the exact dry-run and confirmation flow.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../../api/client'
import type { SmartFixesDryRun } from '../../api/types'
import DryRunModal from '../../components/DryRunModal.vue'
import { useJobsStore } from '../../stores/jobs'

const { t } = useI18n()
const jobs = useJobsStore()

// This descriptive list mirrors the fixed server catalog. It is deliberately
// not configurable: ambiguous values stay unchanged.
const FAMILIES = ['cleanup', 'encoding', 'credits'] as const

const dry = ref<SmartFixesDryRun | null>(null)
const stale = ref(false)
const busy = ref(false)
const modalError = ref<string | null>(null)
const banner = ref<{ tone: 'error' | 'success'; text: string } | null>(null)

function describe(cause: unknown): string {
  return cause instanceof ApiError ? cause.message : t('common.networkError')
}

async function runDryRun() {
  banner.value = null
  busy.value = true
  modalError.value = null
  try {
    dry.value = await api.post<SmartFixesDryRun>('/api/smartfixes/dry-run', {})
    stale.value = false
  } catch (cause) {
    // B1: the dry-run click reports its failure (400 paths, network, …)
    banner.value = { tone: 'error', text: describe(cause) }
    dry.value = null
  } finally {
    busy.value = false
  }
}

async function execute() {
  if (!dry.value) return
  busy.value = true
  modalError.value = null
  try {
    const result = await api.post<{ fields_applied: number; tracks_touched: number }>(
      '/api/smartfixes/execute',
      {
        payload: dry.value.payload,
        fingerprint: dry.value.fingerprint,
      },
    )
    banner.value = {
      tone: 'success',
      text: t('smartfixes.executed', {
        fields: result.fields_applied,
        tracks: result.tracks_touched,
      }),
    }
    dry.value = null
  } catch (cause) {
    if (cause instanceof ApiError && cause.code === 'stale_snapshot') {
      stale.value = true // the modal shows "Relancer l'aperçu"
    } else {
      modalError.value = describe(cause)
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div>
    <div class="panel">
      <h3>{{ t('smartfixes.title') }}</h3>
      <i18n-t tag="p" class="lead" keypath="smartfixes.lead">
        <template #cycle>
          <b>{{ t('smartfixes.cycle') }}</b>
        </template>
      </i18n-t>

      <!-- fixed catalog: descriptive, NOT selectable (§5.11) -->
      <div class="families" role="list">
        <div v-for="family in FAMILIES" :key="family" class="family" role="listitem">
          <span class="family-tick" aria-hidden="true">✓</span>
          <span>{{ t(`smartfixes.families.${family}`) }}</span>
        </div>
      </div>
      <p class="limits-note">{{ t('smartfixes.limitsNote') }}</p>

      <div
        v-if="banner"
        class="banner"
        :data-tone="banner.tone"
        :role="banner.tone === 'error' ? 'alert' : 'status'"
      >
        <span class="banner-text">{{ banner.text }}</span>
        <button
          type="button"
          class="banner-close"
          :aria-label="t('common.close')"
          @click="banner = null"
        >
          ✕
        </button>
      </div>

      <div class="foot">
        <div class="backup-note">{{ t('smartfixes.backupNote') }}</div>
        <button
          type="button"
          class="dryrun-cta"
          :disabled="busy || jobs.jobRunning"
          @click="runDryRun()"
        >
          {{ busy && !dry ? t('common.loading') : t('smartfixes.dryRunCta') }}
        </button>
      </div>
    </div>

    <DryRunModal
      v-if="dry"
      :dry="dry"
      :stale="stale"
      :busy="busy"
      :error="modalError"
      @close="dry = null"
      @execute="execute"
      @rerun="runDryRun"
    />
  </div>
</template>

<style scoped>
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 20px;
}
h3 {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 6px;
}
.lead {
  color: var(--text-muted-bright);
  font-size: 13px;
  line-height: 1.5;
  max-width: 560px;
  margin: 0;
}
.lead b {
  color: var(--text-secondary-bright);
}
.families {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
  margin-top: 16px;
}
.family {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 10px;
  padding: 12px;
  font-size: 13px;
  color: var(--text-secondary-bright);
}
.family-tick {
  color: var(--teal);
  font-weight: 700;
}
.limits-note {
  color: var(--text-muted-bright);
  font-size: 12.5px;
  line-height: 1.5;
  margin: 12px 0 0;
}
.banner {
  display: flex;
  align-items: center;
  gap: 10px;
  border-radius: 9px;
  padding: 9px 12px;
  margin-top: 14px;
  font-size: 12.5px;
}
.banner[data-tone='error'] {
  background: var(--danger-tint);
  border: 1px solid var(--danger-border);
  color: var(--danger-text);
}
.banner[data-tone='success'] {
  background: var(--success-tint);
  border: 1px solid var(--success-border);
  color: var(--success);
}
.banner-text {
  flex: 1;
}
.banner-close {
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
}
.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 18px;
}
.backup-note {
  font-size: 12.5px;
  color: var(--text-secondary);
}
.backup-note b {
  color: var(--text-secondary-bright);
}
.dryrun-cta {
  background: var(--teal);
  border: none;
  color: #06131f;
  padding: 10px 18px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.dryrun-cta:disabled {
  opacity: 0.55;
  cursor: default;
}
</style>
