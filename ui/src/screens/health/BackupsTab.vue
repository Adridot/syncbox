<script setup lang="ts">
// Backups & logs (§5.10/F9): list / restore (RB-guarded server-side; the
// restore snapshots the CURRENT db first — reversible), rotation control,
// log tail + "Ouvrir le dossier de logs" through the opener plugin.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../../api/client'
import type {
  BackupInfo,
  SourceReconciliationPlan,
  SourceReconciliationResult,
} from '../../api/types'
import LoadingState from '../../components/LoadingState.vue'
import { useRefreshOnReturn } from '../../lib/refresh'
import { revealInFolder } from '../../shell'
import { useJobsStore } from '../../stores/jobs'
import { useSettingsStore } from '../../stores/settings'
import { useStatusStore } from '../../stores/status'

const { t } = useI18n()
const status = useStatusStore()
const jobs = useJobsStore()
const settings = useSettingsStore()

const backups = ref<BackupInfo[] | null>(null)
interface StorageMigrationPlan {
  dry_run: boolean
  plan_version: number
  fingerprint: unknown
  items: Array<{
    job_id: number
    scope: 'event' | 'library' | 'collection'
    title: string | null
    artist: string | null
    source_path: string
    destination_path: string
  }>
  cleanup_directories: Array<{
    job_id: number
    scope: 'event' | 'library' | 'collection'
    title: string | null
    artist: string | null
    directory_path: string
  }>
  ignored: Array<{
    job_id: number | null
    title: string | null
    artist: string | null
    source_path: string
    reason: string
  }>
}
const migration = ref<StorageMigrationPlan | null>(null)
const migrationBusy = ref(false)
const reconciliation = ref<SourceReconciliationPlan | null>(null)
const reconcileBusy = ref(false)
const logs = ref<{
  configured: boolean
  path?: string
  lines: string[]
} | null>(null)
const retention = ref<number>(20)
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
    migration.value = await api.get<StorageMigrationPlan>('/api/acquisition/storage-migration')
  } catch {
    migration.value = null
  }
  try {
    reconciliation.value = await api.get<SourceReconciliationPlan>(
      '/api/events/source-reconciliation',
    )
  } catch {
    reconciliation.value = null
  }
  try {
    logs.value = await api.get<{
      configured: boolean
      path?: string
      lines: string[]
    }>('/api/doctor/logs?lines=120')
    logsError.value = null
  } catch (cause) {
    logsError.value = describe(cause)
  }
  if (!settings.loaded) await settings.load().catch(() => {})
  retention.value = settings.values?.backup_retention ?? 20
}
// skeleton on first load only; keep-alive re-entries refresh silently
useRefreshOnReturn(() => void load())

async function restore(name: string) {
  banner.value = null
  try {
    const result = await api.post<{
      restored: string
      pre_restore_snapshot: string | null
    }>(`/api/doctor/backups/${name}/restore`)
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
    await api.post('/api/doctor/retention', {
      backup_retention: Number(retention.value),
    })
    banner.value = {
      tone: 'success',
      text: t('backups.retentionSaved', { n: retention.value }),
    }
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
  }
}

async function migrateStorage() {
  if (
    !migration.value ||
    (!migration.value.items.length && !migration.value.cleanup_directories.length)
  )
    return
  migrationBusy.value = true
  banner.value = null
  try {
    const result = await api.post<{ migrated_files: number; cleaned_directories: number }>(
      '/api/acquisition/storage-migration',
      {
        dry_run: false,
        plan: migration.value,
      },
    )
    banner.value = {
      tone: 'success',
      text: `${t('backups.migration.doneFiles', result.migrated_files)} · ${t(
        'backups.migration.doneDirectories',
        result.cleaned_directories,
      )}`,
    }
    await load()
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
  } finally {
    migrationBusy.value = false
  }
}

// A 428 (trash unavailable) goes through the client's consent loop and is
// re-sent with the same plan; a refusal after the Rekordbox commit comes back
// as cleanup_pending and the reloaded preview offers it as a cleanup item.
async function reconcile() {
  if (!reconciliation.value?.items.length) return
  reconcileBusy.value = true
  banner.value = null
  try {
    const result = await api.post<SourceReconciliationResult>(
      '/api/events/source-reconciliation',
      { dry_run: false, plan: reconciliation.value },
    )
    const kept = result.cleanup_pending.length
    banner.value = {
      tone: 'success',
      text:
        t('backups.reconcile.done', result.trashed_files.length) +
        (kept ? ` · ${t('backups.reconcile.kept', kept)}` : ''),
    }
    await load()
  } catch (cause) {
    banner.value = { tone: 'error', text: describe(cause) }
  } finally {
    reconcileBusy.value = false
  }
}

function reconcileCount(action: 'rematch' | 'replace' | 'cleanup'): number {
  return reconciliation.value?.items.filter((item) => item.action === action).length ?? 0
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

function reasonLabel(reason?: string | null): string {
  const known = new Set([
    'rekordbox_mutation',
    'event_apply',
    'event_reapply',
    'event_delete',
    'library_apply',
    'collection_relink',
    'missing_remove',
    'duplicate_resolve',
    'untagged_remove',
    'smart_fixes',
    'acquisition_storage_migration',
    'event_source_reconciliation',
    'legacy_metadata_backfill',
    'pre_restore',
  ])
  return t(`backups.reason.${reason && known.has(reason) ? reason : 'legacy'}`)
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
      <div
        v-if="
          migration &&
          (migration.items.length ||
            migration.cleanup_directories.length ||
            migration.ignored.length)
        "
        class="card full"
      >
        <div class="card-head">
          <div>
            <h3>{{ t('backups.migration.title') }}</h3>
            <p class="migration-lead">{{ t('backups.migration.lead') }}</p>
          </div>
          <button
            class="restore"
            :disabled="
              status.rbOpen ||
              jobs.jobRunning ||
              migrationBusy ||
              (!migration.items.length && !migration.cleanup_directories.length)
            "
            @click="migrateStorage"
          >
            {{
              t(
                'backups.migration.confirm',
                migration.items.length + migration.cleanup_directories.length,
              )
            }}
          </button>
        </div>
        <div class="migration-counts">
          <span>{{
            t(
              'backups.migration.event',
              migration.items.filter((item) => item.scope === 'event').length,
            )
          }}</span>
          <span v-if="migration.cleanup_directories.length">
            {{ t('backups.migration.cleanup', migration.cleanup_directories.length) }}
          </span>
          <span>{{
            t(
              'backups.migration.collection',
              migration.items.filter((item) => item.scope !== 'event').length,
            )
          }}</span>
          <span v-if="migration.ignored.length" class="warning">
            {{ t('backups.migration.ignored', migration.ignored.length) }}
          </span>
        </div>
        <details v-if="migration.items.length">
          <summary>{{ t('backups.migration.readyDetails') }}</summary>
          <div v-for="item in migration.items" :key="item.job_id" class="migration-item">
            <b>{{ item.title || t('missing.untitled') }}</b> —
            {{ item.artist || '—' }}
            <div class="mono path">{{ item.source_path }} → {{ item.destination_path }}</div>
          </div>
        </details>
        <details v-if="migration.cleanup_directories.length">
          <summary>{{ t('backups.migration.cleanupDetails') }}</summary>
          <div
            v-for="item in migration.cleanup_directories"
            :key="`cleanup-${item.job_id}`"
            class="migration-item"
          >
            <b>{{ item.title || t('missing.untitled') }}</b> —
            {{ item.artist || '—' }}
            <div class="mono path">{{ item.directory_path }}</div>
          </div>
        </details>
        <details v-if="migration.ignored.length" open>
          <summary>{{ t('backups.migration.ignoredDetails') }}</summary>
          <div
            v-for="item in migration.ignored"
            :key="`${item.job_id}-${item.source_path}`"
            class="migration-item warning"
          >
            <b>{{ item.title || t('missing.untitled') }}</b> —
            {{ t(`backups.migration.reason.${item.reason}`) }}
            <div class="mono path">{{ item.source_path }}</div>
          </div>
        </details>
      </div>
      <div
        v-if="
          reconciliation?.items &&
          (reconciliation.items.length ||
            reconciliation.isrc_coverage.downloads_without_isrc.length)
        "
        class="card full reconcile"
      >
        <div class="card-head">
          <div>
            <h3>{{ t('backups.reconcile.title') }}</h3>
            <p class="migration-lead">{{ t('backups.reconcile.lead') }}</p>
          </div>
          <button
            class="restore"
            :disabled="
              (status.rbOpen && reconcileCount('replace') > 0) ||
              jobs.jobRunning ||
              reconcileBusy ||
              !reconciliation.items.length
            "
            @click="reconcile"
          >
            {{ t('backups.reconcile.confirm', reconciliation.items.length) }}
          </button>
        </div>
        <div class="migration-counts">
          <span>{{ t('backups.reconcile.rematch', reconcileCount('rematch')) }}</span>
          <span>{{ t('backups.reconcile.replace', reconcileCount('replace')) }}</span>
          <span v-if="reconcileCount('cleanup')">
            {{ t('backups.reconcile.cleanup', reconcileCount('cleanup')) }}
          </span>
          <span v-if="reconciliation.skipped.length" class="warning">
            {{ t('backups.migration.ignored', reconciliation.skipped.length) }}
          </span>
        </div>
        <div class="migration-counts coverage">
          <span>{{
            t('backups.reconcile.coverage', {
              with: reconciliation.isrc_coverage.rows_with_isrc,
              without: reconciliation.isrc_coverage.rows_without_isrc,
              found: reconciliation.isrc_coverage.rows_with_candidate,
            })
          }}</span>
          <span
            v-if="reconciliation.isrc_coverage.downloads_without_isrc.length"
            class="warning"
          >
            {{
              t(
                'backups.reconcile.downloadsWithoutIsrc',
                reconciliation.isrc_coverage.downloads_without_isrc.length,
              )
            }}
          </span>
          <span v-if="reconciliation.isrc_coverage.non_alphanumeric_isrcs" class="warning">
            {{
              t(
                'backups.reconcile.oddIsrcs',
                reconciliation.isrc_coverage.non_alphanumeric_isrcs,
              )
            }}
          </span>
        </div>
        <details v-if="reconciliation.items.length">
          <summary>{{ t('backups.reconcile.readyDetails') }}</summary>
          <div
            v-for="item in reconciliation.items"
            :key="item.track_id"
            class="migration-item"
          >
            <b>{{ item.title || t('missing.untitled') }}</b> — {{ item.artist || '—' }} ·
            {{ item.event_name }} · {{ t(`backups.reconcile.action.${item.action}`) }}
            <div class="mono path">{{ item.file.path }}</div>
          </div>
        </details>
        <details v-if="reconciliation.isrc_coverage.downloads_without_isrc.length" open>
          <summary>{{ t('backups.reconcile.downloadsWithoutIsrcDetails') }}</summary>
          <div
            v-for="item in reconciliation.isrc_coverage.downloads_without_isrc"
            :key="item.content_id"
            class="migration-item warning"
          >
            <b>{{ item.title || t('missing.untitled') }}</b>
            <div class="mono path">{{ item.path }}</div>
          </div>
        </details>
        <details v-if="reconciliation.skipped.length">
          <summary>{{ t('backups.migration.ignoredDetails') }}</summary>
          <div
            v-for="item in reconciliation.skipped"
            :key="`skipped-${item.track_id}`"
            class="migration-item"
          >
            <b>{{ item.title || t('missing.untitled') }}</b> — {{ item.event_name }} ·
            {{ t(`backups.reconcile.reason.${item.reason}`) }}
          </div>
        </details>
      </div>
      <div class="card">
        <div class="card-head">
          <h3>{{ t('backups.title') }}</h3>
          <div class="retention">
            <label class="retention-label" for="retention">{{ t('backups.recent') }}</label>
            <input id="retention" v-model.number="retention" type="number" min="0" max="99" />
            <button class="btn-secondary small" @click="saveRetention">
              {{ t('backups.save') }}
            </button>
          </div>
        </div>
        <div class="policy-note">
          {{ t('backups.policy', { n: retention }) }}
        </div>
        <div v-for="backup in backups" :key="backup.name" class="backup-row">
          <div class="backup-text">
            <div class="backup-ts mono">{{ tsLabel(backup.name) }}</div>
            <div class="backup-name">{{ backup.name }}</div>
            <div class="backup-meta">
              {{ reasonLabel(backup.reason) }} ·
              {{ backup.verified ? t('backups.verified') : t('backups.legacy') }}
              ·
              {{ backup.coherent ? t('backups.coherent') : t('backups.rekordboxOnly') }}
              <span v-if="backup.pinned"> · {{ t('backups.pinned') }}</span>
            </div>
          </div>
          <span class="backup-size mono">{{ sizeLabel(backup.size_bytes) }}</span>
          <button
            class="restore"
            :disabled="status.rbOpen || jobs.jobRunning || !backup.coherent"
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
          <button class="btn-secondary small" @click="load">
            {{ t('common.retry') }}
          </button>
        </div>
        <div v-if="logsError" class="empty">{{ logsError }}</div>
        <div v-else-if="logs && !logs.configured" class="empty">
          {{ t('backups.logsUnconfigured') }}
        </div>
        <div v-else-if="logs" class="log-tail mono">
          <div v-for="(line, index) in logs.lines" :key="index" class="log-line">
            {{ line }}
          </div>
          <div v-if="!logs.lines.length" class="empty">
            {{ t('backups.logsEmpty') }}
          </div>
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
.full {
  grid-column: 1 / -1;
}
.migration-lead {
  color: var(--text-muted-bright);
  font-size: 12px;
  margin: 5px 0 0;
}
.migration-counts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 12px;
  margin: 12px 0;
}
.migration-counts span {
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 5px 8px;
}
.warning {
  color: var(--warning);
}
.migration-item {
  padding: 8px 0;
  color: var(--text-secondary);
  font-size: 12px;
}
.path {
  overflow-wrap: anywhere;
  margin-top: 3px;
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
.policy-note {
  color: var(--text-muted);
  font-size: 11.5px;
  margin: 8px 0 12px;
}
.backup-meta {
  color: var(--text-muted);
  font-size: 11px;
  margin-top: 2px;
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
