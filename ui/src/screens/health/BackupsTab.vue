<script setup lang="ts">
// Backups & logs tab (SPEC-DESIGN §2/§6): backup list + restore (423-guarded,
// "restore snapshots first" note — restore is itself reversible), retention
// control, log tail + "Ouvrir le dossier de logs" (opener plugin).
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '../../api/client'
import GuardedButton from '../../components/GuardedButton.vue'
import { openExternal } from '../../shell'
import { useSettingsStore } from '../../stores/settings'

const { t } = useI18n()
const settings = useSettingsStore()

interface Backup {
  name: string
  files: string[]
  size_bytes: number
}

const backups = ref<Backup[]>([])
const logs = ref<{ configured: boolean; path?: string; lines: string[] }>({
  configured: false,
  lines: [],
})
const retention = ref(15)

onMounted(load)

async function load() {
  if (!settings.loaded) await settings.load()
  retention.value = settings.values?.backup_retention ?? 15
  const [b, l] = await Promise.all([
    api.get<{ backups: Backup[] }>('/api/doctor/backups'),
    api.get<{ configured: boolean; path?: string; lines: string[] }>('/api/doctor/logs?lines=40'),
  ])
  backups.value = b.backups
  logs.value = l
}

async function restore(name: string) {
  await api.post(`/api/doctor/backups/${name}/restore`)
  await load()
}

async function saveRetention() {
  await api.post('/api/doctor/retention', { backup_retention: retention.value })
}

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
function timestamp(name: string): string {
  const m = name.match(/(\d{8})-(\d{6})/)
  if (!m) return name
  const [, d, tm] = m
  return `${d.slice(6, 8)}/${d.slice(4, 6)}/${d.slice(0, 4)} ${tm.slice(0, 2)}:${tm.slice(2, 4)}:${tm.slice(4, 6)}`
}

const logsFolder = computed(() => {
  if (!logs.value.path) return null
  return `file://${logs.value.path.replace(/\/[^/]+$/, '')}`
})
</script>

<template>
  <div class="grid">
    <div class="panel">
      <div class="panel-head">
        <h3>{{ t('backups.title') }}</h3>
        <div class="retention">
          <span class="mono">{{ t('backups.retention') }}</span>
          <input v-model.number="retention" type="number" min="0" class="ret-input mono" @change="saveRetention" />
        </div>
      </div>
      <div v-for="backup in backups" :key="backup.name" class="brow">
        <div class="btext">
          <div class="mono bts">{{ timestamp(backup.name) }}</div>
          <div class="bnote">{{ backup.files.length }} {{ t('backups.files') }}</div>
        </div>
        <span class="mono bsize">{{ humanSize(backup.size_bytes) }}</span>
        <GuardedButton :label="t('backups.restore')" tone="primary" @click="restore(backup.name)" />
      </div>
      <div v-if="!backups.length" class="empty">{{ t('backups.empty') }}</div>
      <div class="note">{{ t('backups.restoreNote') }}</div>
    </div>

    <div class="panel">
      <div class="panel-head">
        <h3>{{ t('backups.logs') }}</h3>
      </div>
      <div v-if="logs.lines.length" class="log-tail mono">
        <div v-for="(line, i) in logs.lines" :key="i" class="log-line">{{ line }}</div>
      </div>
      <div v-else class="empty">{{ t('backups.noLogs') }}</div>
      <button v-if="logsFolder" class="btn-ghost" @click="openExternal(logsFolder)">
        {{ t('backups.openLogs') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
  gap: 16px;
}
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 13px;
  padding: 16px;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 13px;
}
h3 {
  font: var(--text-h3);
  margin: 0;
}
.retention {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11.5px;
  color: var(--text-muted);
}
.ret-input {
  width: 52px;
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 6px;
  padding: 3px 7px;
  color: var(--text-secondary-bright);
  font-size: 12px;
  outline: none;
}
.mono {
  font-family: var(--font-mono);
}
.brow {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.btext {
  flex: 1;
  min-width: 0;
}
.bts {
  font-size: 12.5px;
  color: var(--text-secondary-bright);
}
.bnote {
  font-size: 11.5px;
  color: var(--text-muted-bright);
}
.bsize {
  font-size: 11.5px;
  color: var(--text-muted);
}
.note {
  font-size: 11.5px;
  color: var(--text-muted);
  margin-top: 11px;
}
.empty {
  font-size: 12.5px;
  color: var(--text-muted);
  padding: 20px 0;
  text-align: center;
}
.log-tail {
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--text-muted-bright);
  max-height: 320px;
  overflow-y: auto;
}
.log-line {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.btn-ghost {
  background: transparent;
  border: 1px solid var(--border-2);
  color: var(--text-secondary);
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 12px;
  cursor: pointer;
  margin-top: 13px;
}
</style>
