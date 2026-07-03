<script setup lang="ts">
// Single-source health pile (SPEC-DESIGN §3.4/§6): every dot derives from
// the canonical health selector. Spotify / Rekordbox / local jobs — the
// mockup's "Téléchargements" row is deprecated (no download module in v1).
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useHealthStore } from '../stores/health'

const health = useHealthStore()
const { t } = useI18n()

const rows = computed(() => [
  {
    key: 'spotify',
    label: t('chrome.spotify'),
    tone: health.pill.spotify,
    text: health.spotifyConnected ? t('chrome.connected') : t('chrome.notConnected'),
  },
  {
    key: 'rekordbox',
    label: t('chrome.rekordbox'),
    tone: health.pill.rekordbox,
    text: health.rekordboxReady ? t('chrome.ready') : t('chrome.rbOpenShort'),
  },
  {
    key: 'jobs',
    label: t('chrome.localJobs'),
    tone: health.pill.jobs,
    text: health.jobsActive ? t('chrome.jobsActive') : t('chrome.jobsIdle'),
  },
])
</script>

<template>
  <div class="pill">
    <div class="pill-title">{{ t('chrome.systemState') }}</div>
    <div v-for="row in rows" :key="row.key" class="row" :data-tone="row.tone">
      <span class="dot" />
      <span class="label">{{ row.label }}</span>
      <span class="value">{{ row.text }}</span>
    </div>
  </div>
</template>

<style scoped>
.pill {
  background: var(--surface);
  border: 1px solid var(--border-subtle-2);
  border-radius: 12px;
  padding: 11px 12px;
}
.pill-title {
  font-size: var(--size-label);
  text-transform: uppercase;
  letter-spacing: var(--label-tracking);
  color: var(--text-muted);
  font-weight: 600;
  margin-bottom: 9px;
}
.row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding: 3.5px 0;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
  background: var(--text-muted);
}
.row[data-tone='ok'] .dot {
  background: var(--success);
}
.row[data-tone='warn'] .dot {
  background: var(--warning);
}
.label {
  color: var(--text-secondary);
  flex: 1;
}
.value {
  font-family: var(--font-mono);
  font-size: var(--size-meta);
  color: var(--text-secondary-bright);
}
.row[data-tone='warn'] .value {
  color: var(--warning-text);
}
</style>
