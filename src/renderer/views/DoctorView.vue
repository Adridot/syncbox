<script setup lang="ts">
import {
  AlertTriangle,
  CheckCircle2,
  History,
  Loader2,
  RefreshCw,
  RotateCcw,
  Trash2,
  XCircle,
} from "@lucide/vue";
import { onMounted } from "vue";
import type { DiagnosticStatus } from "../lib/api";
import { useDoctorStore } from "../stores/doctor";
import { useSettingsStore } from "../stores/settings";
import { useSystemStore } from "../stores/system";

const doctor = useDoctorStore();
const settings = useSettingsStore();
const system = useSystemStore();

onMounted(() => {
  if (system.api) doctor.refresh();
});

async function saveRetention(value: number): Promise<void> {
  const n = Math.max(0, Math.floor(Number(value) || 0));
  settings.settings.backupRetention = n;
  await settings.save();
  await doctor.refresh();
}

const statusIcon: Record<DiagnosticStatus, unknown> = {
  ok: CheckCircle2,
  warn: AlertTriangle,
  error: XCircle,
};

const statusColor: Record<DiagnosticStatus, string> = {
  ok: "text-secondary",
  warn: "text-tertiary",
  error: "text-error",
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(epochSeconds: number): string {
  if (!epochSeconds) return "unknown";
  return new Date(epochSeconds * 1000).toLocaleString();
}

async function openLogs(): Promise<void> {
  await window.desktop?.openLogs();
}

async function confirmRestore(name: string): Promise<void> {
  const ok = window.confirm(
    `Restore Rekordbox database from "${name}"?\n\nThis overwrites the current collection. A safety backup of the current state is made first. Rekordbox must be closed.`
  );
  if (ok) await doctor.restore(name);
}
</script>

<template>
  <div class="h-full overflow-y-auto px-6 py-6 md:px-8">
    <div class="mx-auto flex max-w-4xl flex-col gap-6">
      <!-- Header -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <span
            v-if="doctor.report"
            class="flex h-8 items-center gap-2 rounded-full px-3 text-sm font-semibold"
            :class="statusColor[doctor.report.status]"
          >
            <component :is="statusIcon[doctor.report.status]" :size="18" aria-hidden="true" />
            {{ doctor.report.status === "ok" ? "All systems healthy" : doctor.report.status === "warn" ? "Attention needed" : "Problems found" }}
          </span>
          <span v-else class="text-sm text-on-surface-variant">Running checks…</span>
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded border border-outline bg-surface px-3 py-2 text-sm text-on-surface-variant hover:border-primary"
            @click="openLogs"
          >
            <History :size="15" aria-hidden="true" />
            Open Logs
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
            :disabled="doctor.loading"
            @click="doctor.refresh()"
          >
            <Loader2 v-if="doctor.loading" :size="15" class="animate-spin" aria-hidden="true" />
            <RefreshCw v-else :size="15" aria-hidden="true" />
            Re-run
          </button>
        </div>
      </div>

      <!-- Diagnostics checks -->
      <section class="rounded-xl border border-outline-variant bg-surface-container">
        <h2 class="border-b border-outline-variant px-5 py-3 text-sm font-bold text-on-surface">
          Diagnostics
        </h2>
        <ul>
          <li
            v-for="check in doctor.report?.checks ?? []"
            :key="check.key"
            class="flex items-start gap-3 border-b border-outline-variant px-5 py-3 last:border-b-0"
          >
            <component
              :is="statusIcon[check.status]"
              :size="18"
              class="mt-0.5 shrink-0"
              :class="statusColor[check.status]"
              aria-hidden="true"
            />
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2">
                <strong class="text-sm text-on-surface">{{ check.label }}</strong>
              </div>
              <p class="text-xs text-on-surface-variant">{{ check.detail }}</p>
              <p v-if="check.hint" class="mt-0.5 text-xs italic text-tertiary">{{ check.hint }}</p>
            </div>
          </li>
          <li
            v-if="!doctor.report && !doctor.loading"
            class="px-5 py-6 text-center text-sm text-on-surface-variant"
          >
            No diagnostics yet.
          </li>
        </ul>
      </section>

      <!-- Backups -->
      <section class="rounded-xl border border-outline-variant bg-surface-container">
        <div class="flex flex-wrap items-center gap-3 border-b border-outline-variant px-5 py-3">
          <h2 class="text-sm font-bold text-on-surface">
            Rekordbox backups
            <span class="font-normal text-on-surface-variant">— restore a previous collection state</span>
          </h2>
          <div class="ml-auto flex items-center gap-3">
            <label class="flex items-center gap-1.5 text-xs text-on-surface-variant">
              Keep last
              <input
                type="number"
                min="0"
                class="w-16 rounded border border-outline bg-surface px-2 py-1 text-xs text-on-surface"
                :value="settings.settings.backupRetention"
                @change="saveRetention(($event.target as HTMLInputElement).valueAsNumber)"
              />
              backups
            </label>
            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded border border-outline bg-surface px-3 py-1.5 text-xs font-semibold text-on-surface hover:border-error hover:text-error disabled:opacity-60"
              :disabled="doctor.pruning || !doctor.backupsReadable"
              @click="doctor.prune()"
            >
              <Loader2 v-if="doctor.pruning" :size="13" class="animate-spin" aria-hidden="true" />
              <Trash2 v-else :size="13" aria-hidden="true" />
              Clean up old backups
            </button>
          </div>
        </div>

        <p
          v-if="doctor.backups.length > 0"
          class="border-b border-outline-variant px-5 py-2 text-xs text-on-surface-variant"
        >
          {{ doctor.backups.length }} backup(s) · {{ formatBytes(doctor.backupsTotalBytes) }} total ·
          rotation keeps the {{ doctor.backupRetention || "∞" }} newest, oldest deleted automatically.
        </p>

        <div
          v-if="!doctor.backupsReadable"
          class="flex items-start gap-2 px-5 py-6 text-sm text-tertiary"
        >
          <AlertTriangle :size="18" class="mt-0.5 shrink-0" aria-hidden="true" />
          <span>
            The backups folder exists but can’t be read here — this happens in the dev build because
            macOS blocks a terminal-launched process from listing cloud-storage folders. Your backups
            are safe; the packaged Syncbox app lists and manages them normally.
          </span>
        </div>
        <div
          v-else-if="doctor.backups.length === 0"
          class="px-5 py-6 text-center text-sm text-on-surface-variant"
        >
          No backups yet. One is created automatically before every change Syncbox applies.
        </div>
        <ul v-else>
          <li
            v-for="backup in doctor.backups"
            :key="backup.name"
            class="flex items-center gap-3 border-b border-outline-variant px-5 py-3 last:border-b-0"
          >
            <History :size="16" class="shrink-0 text-on-surface-variant" aria-hidden="true" />
            <div class="min-w-0 flex-1">
              <strong class="block truncate text-sm text-on-surface">{{ backup.name }}</strong>
              <span class="text-xs text-on-surface-variant">
                {{ formatDate(backup.createdAt) }} · {{ formatBytes(backup.sizeBytes) }} · {{ backup.fileCount }} file(s)
              </span>
            </div>
            <button
              type="button"
              class="inline-flex shrink-0 items-center gap-1.5 rounded border border-outline bg-surface px-3 py-1.5 text-xs font-semibold text-on-surface hover:border-tertiary hover:text-tertiary disabled:opacity-60"
              :disabled="doctor.restoringName !== null"
              @click="confirmRestore(backup.name)"
            >
              <Loader2
                v-if="doctor.restoringName === backup.name"
                :size="13"
                class="animate-spin"
                aria-hidden="true"
              />
              <RotateCcw v-else :size="13" aria-hidden="true" />
              Restore
            </button>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
