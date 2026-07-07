<script setup lang="ts">
// Duplicates (§5.4/§5.12): EXPLICIT scan CTA (never auto-run — it locks the
// whole API) with real SSE progress; per-group confirm (D5); resolve echoes
// the scan fingerprint verbatim (409 stale → re-scan invite); the 428
// permanent-delete consent flows through the global broker and the retry is
// re-entrant server-side. B1: the scan click NEVER fails silently.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../../api/client'
import type { DuplicateScan } from '../../api/types'
import DuplicateGroupCard from '../../components/DuplicateGroupCard.vue'
import EmptyState from '../../components/EmptyState.vue'
import JobRow from '../../components/JobRow.vue'
import { useHealthStore } from '../../stores/health'
import { useJobsStore } from '../../stores/jobs'

const { t } = useI18n()
const health = useHealthStore()
const jobs = useJobsStore()

const scanning = ref(false)
const banner = ref<{ tone: 'error' | 'success'; text: string; rescan?: boolean } | null>(null)

function describe(cause: unknown): string {
  return cause instanceof ApiError ? cause.message : t('common.networkError')
}

async function scan() {
  scanning.value = true
  banner.value = null
  try {
    const result = await api.post<DuplicateScan>('/api/duplicates/scan')
    health.setDuplicateScan(result)
    banner.value = { tone: 'success', text: t('duplicates.scanDone', result.groups.length) }
  } catch (cause) {
    // B1 — the exact bug class this redo exists to prevent
    banner.value = { tone: 'error', text: describe(cause) }
  } finally {
    scanning.value = false
  }
}

async function resolve(groupKey: string, keeper: string, losers: string[]) {
  banner.value = null
  try {
    const result = await api.post<{ files: Array<{ result: string }> }>(
      '/api/duplicates/resolve',
      {
        keeper_content_id: keeper,
        loser_content_ids: losers,
        fingerprint: health.duplicateScan?.fingerprint,
      },
    )
    dropGroup(groupKey)
    // the resolve invalidated the snapshot: the remaining groups' fingerprint
    // is now stale — say so and offer the re-scan instead of a surprise 409
    banner.value = {
      tone: 'success',
      text:
        t('duplicates.resolved', { n: losers.length, files: result.files.length }) +
        (health.duplicateScan?.groups.length ? ' ' + t('duplicates.rescanHint') : ''),
      rescan: (health.duplicateScan?.groups.length ?? 0) > 0,
    }
  } catch (cause) {
    if (cause instanceof ApiError && cause.code === 'stale_snapshot') {
      banner.value = { tone: 'error', text: t('duplicates.stale'), rescan: true }
    } else {
      banner.value = { tone: 'error', text: describe(cause) }
    }
  }
}

async function dismiss(groupKey: string) {
  banner.value = null
  try {
    await api.post('/api/duplicates/dismiss', { group_key: groupKey })
    dropGroup(groupKey)
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
  }
}

function dropGroup(groupKey: string) {
  const scanState = health.duplicateScan
  if (!scanState) return
  health.setDuplicateScan({
    ...scanState,
    groups: scanState.groups.filter((group) => group.key !== groupKey),
  })
}
</script>

<template>
  <div>
    <div class="intro-row">
      <i18n-t tag="p" class="intro" keypath="duplicates.intro">
        <template #keep>
          <b class="keep">{{ t('duplicates.keepWord') }}</b>
        </template>
      </i18n-t>
      <button class="btn-primary scan" :disabled="scanning || jobs.jobRunning" @click="scan">
        <span class="btn-icon">↻</span>
        {{ scanning ? t('duplicates.scanning') : t('duplicates.scanCta') }}
      </button>
    </div>

    <JobRow kind="duplicates.scan" :label="t('duplicates.scanJob')" />

    <div v-if="banner" class="banner" :data-tone="banner.tone" role="status">
      <span class="banner-text">{{ banner.text }}</span>
      <button v-if="banner.rescan" class="btn-secondary small" @click="scan">
        {{ t('duplicates.rescan') }}
      </button>
      <button class="banner-close" @click="banner = null">✕</button>
    </div>

    <EmptyState
      v-if="health.duplicateScan === null"
      icon="⧉"
      :title="t('duplicates.notScannedTitle')"
      :body="t('duplicates.notScannedBody')"
    />
    <EmptyState
      v-else-if="!health.duplicateScan.groups.length"
      icon="✓"
      :title="t('duplicates.cleanTitle')"
      :body="t('duplicates.cleanBody', { n: health.duplicateScan.scanned })"
    />
    <div v-else class="groups">
      <DuplicateGroupCard
        v-for="(group, index) in health.duplicateScan.groups"
        :key="group.key"
        :group="group"
        :index="index"
        @resolve="(keeper, losers) => resolve(group.key, keeper, losers)"
        @dismiss="dismiss(group.key)"
      />
      <div class="per-group-note">
        <i18n-t keypath="duplicates.perGroupNote">
          <template #perGroup>
            <b>{{ t('duplicates.perGroupWord') }}</b>
          </template>
        </i18n-t>
      </div>
    </div>
  </div>
</template>

<style scoped>
.intro-row {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 14px;
}
.intro {
  flex: 1;
  font-size: 12.5px;
  color: var(--text-muted-bright);
  margin: 0;
  line-height: 1.5;
}
.keep {
  color: #5fe0b0;
}
.scan {
  flex: none;
}
.banner {
  display: flex;
  align-items: center;
  gap: 10px;
  border-radius: 9px;
  padding: 9px 12px;
  margin-bottom: 12px;
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
.btn-secondary.small {
  padding: 5px 10px;
  font-size: 12px;
}
.groups {
  display: flex;
  flex-direction: column;
  gap: 22px;
}
.per-group-note {
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
  padding: 2px;
}
.per-group-note b {
  color: var(--text-secondary);
}
</style>
