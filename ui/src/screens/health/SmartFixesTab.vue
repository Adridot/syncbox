<script setup lang="ts">
// Smart Fixes (§5.11): the catalog is FIXED server-side — the families are
// descriptive text, not options (M4-PLAN §1.4). Strict dry-run → confirm →
// mutate; the dry-run reads the snapshot only (RB may be open), the execute
// is RB-guarded and re-asserts freshness (409 → stale banner in the modal).
// No protected opt-in here (owner amendment 2026-07-07): Smart Fixes are
// metadata-only behind an automatic backup; the guard stays on file deletes.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../../api/client'
import type { SmartFixesDryRun } from '../../api/types'
import DryRunModal from '../../components/DryRunModal.vue'
import { useJobsStore } from '../../stores/jobs'

const { t } = useI18n()
const jobs = useJobsStore()

// Only the fixes the server actually runs (smartfixes.py CATALOG). 'extract'
// (artist/remixer from title) and 'case' (casing) are DEFERRED, not shipped:
// POC #9 excluded casing (13 legit all-caps titles clobbered) and extraction
// needs RemixerID write support + its own calibration. The ✓ list must match
// behavior — advertising a fix that never fires is worse than omitting it.
const FAMILIES = ['junkchars', 'encoding'] as const

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
      <div class="families">
        <div v-for="family in FAMILIES" :key="family" class="family">
          <span class="family-tick">✓</span>
          <span>{{ t(`smartfixes.families.${family}`) }}</span>
        </div>
      </div>

      <div v-if="banner" class="banner" :data-tone="banner.tone" role="status">
        <span class="banner-text">{{ banner.text }}</span>
        <button class="banner-close" @click="banner = null">✕</button>
      </div>

      <div class="foot">
        <div class="protected-note">{{ t('smartfixes.backupNote') }}</div>
        <button class="dryrun-cta" :disabled="busy || jobs.jobRunning" @click="runDryRun()">
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
  grid-template-columns: repeat(2, minmax(0, 1fr));
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
.protected-note {
  font-size: 12.5px;
  color: var(--text-secondary);
}
.protected-note b {
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
