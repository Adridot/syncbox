<script setup lang="ts">
// Backups & logs (§5.10/F9): list / restore (RB-guarded server-side; the
// restore snapshots the CURRENT db first — reversible), rotation control,
// log tail + "Ouvrir le dossier de logs" through the opener plugin.
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../../api/client'
import type { BackupInfo } from '../../api/types'
import LoadingState from '../../components/LoadingState.vue'
import { revealInFolder } from '../../shell'
import { useJobsStore } from '../../stores/jobs'
import { useSettingsStore } from '../../stores/settings'
import { useStatusStore } from '../../stores/status'

const { t } = useI18n()
const status = useStatusStore()
const jobs = useJobsStore()
const settings = useSettingsStore()

const backups = ref<BackupInfo[] | null>(null)
const logs = ref<{ configured: boolean; path?: string; lines: string[] } | null>(null)
const retention = ref<number>(15)
const banner = ref<{ tone: 'error' | 'success'; text: string } | null>(null)
const logsError = ref<string | null>(null)

function describe(cause: unknown): string {
  return cause instanceof ApiError ? cause.message : t('common.networkError')
}

async function load() {
  try {
    backups.value = (await api.get<{ backups: BackupInfo[] }>('/api/doctor/backups')).backups
  } catch (cause) {
    backups.value = []
    banner.value = { tone: 'error', text: describe(cause) }
  }
  try {
    logs.value = await api.get<{ configured: boolean; path?: string; lines: string[] }>(
      '/api/doctor/logs?lines=120',
    )
    logsError.value = null
  } catch (cause) {
    logsError.value = describe(cause)
  }
  if (!settings.loaded) await settings.load().catch(() => {})
  retention.value = settings.values?.backup_retention ?? 15
}
onMounted(() => void load())

async function restore(name: string) {
  banner.value = null
  try {
    const result = await api.post<{ restored: string; pre_restore_snapshot: string | null }>(
      `/api/doctor/backups/${name}/restore`,
    )
    banner.value = {
      tone: 'success',
      text: t('backups.restored', {
        name: result.restored,
        snapshot: result.pre_restore_snapshot ?? '—',
      }),
    }
    await load()
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
  }
}

async function saveRetention() {
  banner.value = null
  try {
    await api.post('/api/doctor/retention', { backup_retention: Number(retention.value) })
    banner.value = { tone: 'success', text: t('backups.retentionSaved', { n: retention.value }) }
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
  }
}

function sizeLabel(bytes: number): string {
  if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(1)} GB`
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`
  return `${Math.round(bytes / 1000)} kB`
}

function tsLabel(name: string): string {
  const match = name.match(/(\d{8})-(\d{6})/)
  if (!match) return name
  const [, day, time] = match
  return `${day.slice(6, 8)}/${day.slice(4, 6)}/${day.slice(0, 4)} ${time.slice(0, 2)}:${time.slice(2, 4)}:${time.slice(4, 6)}`
}
</script>

<template>
  <div>
    <div v-if="banner" class="banner" :data-tone="banner.tone" role="status">
      <span class="banner-text">{{ banner.text }}</span>
      <button class="banner-close" @click="banner = null">✕</button>
    </div>

    <LoadingState v-if="backups === null" :rows="4" />
    <div v-else class="grid">
      <div class="card">
        <div class="card-head">
          <h3>{{ t('backups.title') }}</h3>
          <div class="retention">
            <label class="retention-label" for="retention">{{ t('backups.rotation') }}</label>
            <input id="retention" v-model.number="retention" type="number" min="0" max="99" />
            <button class="btn-secondary small" @click="saveRetention">
              {{ t('backups.save') }}
            </button>
          </div>
        </div>
        <div v-for="backup in backups" :key="backup.name" class="backup-row">
          <div class="backup-text">
            <div class="backup-ts mono">{{ tsLabel(backup.name) }}</div>
            <div class="backup-name">{{ backup.name }}</div>
          </div>
          <span class="backup-size mono">{{ sizeLabel(backup.size_bytes) }}</span>
          <button
            class="restore"
            :disabled="status.rbOpen || jobs.jobRunning"
            @click="restore(backup.name)"
          >
            {{ status.rbOpen ? t('rbGuard.blocked') : t('backups.restore') }}
          </button>
        </div>
        <div v-if="!backups.length" class="empty">{{ t('backups.empty') }}</div>
        <div class="note">{{ t('backups.restoreNote') }}</div>
      </div>

      <div class="card">
        <div class="card-head">
          <h3>{{ t('backups.logsTitle') }}</h3>
          <button class="btn-secondary small" @click="load">{{ t('common.retry') }}</button>
        </div>
        <div v-if="logsError" class="empty">{{ logsError }}</div>
        <div v-else-if="logs && !logs.configured" class="empty">
          {{ t('backups.logsUnconfigured') }}
        </div>
        <div v-else-if="logs" class="log-tail mono">
          <div v-for="(line, index) in logs.lines" :key="index" class="log-line">{{ line }}</div>
          <div v-if="!logs.lines.length" class="empty">{{ t('backups.logsEmpty') }}</div>
        </div>
        <button
          v-if="logs?.configured && logs.path"
          class="btn-secondary small open-logs"
          @click="revealInFolder(logs.path!)"
        >
          {{ t('backups.openLogsFolder') }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
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
.grid {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 16px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 13px;
}
h3 {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
}
.retention {
  display: flex;
  align-items: center;
  gap: 7px;
}
.retention-label {
  font-size: 11.5px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}
.retention input {
  width: 52px;
  background: var(--surface-raised);
  border: 1px solid #2a3140;
  border-radius: 7px;
  padding: 4px 8px;
  color: var(--text-secondary-bright);
  font-family: var(--font-mono);
  font-size: 12px;
  outline: none;
}
.btn-secondary.small {
  padding: 5px 10px;
  font-size: 12px;
}
.backup-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.backup-text {
  flex: 1;
  min-width: 0;
}
.backup-ts {
  font-size: 12.5px;
  color: var(--text-secondary-bright);
}
.backup-name {
  font-size: 11.5px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.backup-size {
  font-size: 11.5px;
  color: var(--text-muted);
}
.restore {
  background: transparent;
  border: 1px solid #2a3140;
  color: var(--text-secondary);
  padding: 5px 11px;
  border-radius: 7px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.restore:disabled {
  opacity: 0.55;
  cursor: default;
}
.mono {
  font-family: var(--font-mono);
}
.empty {
  font-size: 12.5px;
  color: var(--text-muted);
  padding: 12px 0;
}
.note {
  font-size: 11.5px;
  color: var(--text-muted);
  margin-top: 11px;
  line-height: 1.5;
}
.log-tail {
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--text-muted-bright);
  max-height: 320px;
  overflow-y: auto;
  overflow-x: hidden;
}
.log-line {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.open-logs {
  margin-top: 13px;
}
</style>
