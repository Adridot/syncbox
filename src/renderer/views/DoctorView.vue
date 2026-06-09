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
import type { DiagnosticStatus } from "../lib/api";
import { formatBytes, formatDate } from "../lib/format";
import { t } from "../i18n";
import { useDoctor } from "../composables/queries/useDoctor";
import { useSettingsStore } from "../stores/settings";

const doctor = useDoctor();
const settings = useSettingsStore();

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

async function openLogs(): Promise<void> {
  await window.desktop?.openLogs();
}

async function confirmRestore(name: string): Promise<void> {
  const ok = window.confirm(t("doctor.confirmRestore", { name }));
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
            {{ doctor.report.status === "ok" ? $t("doctor.allHealthy") : doctor.report.status === "warn" ? $t("doctor.attentionNeeded") : $t("doctor.problemsFound") }}
          </span>
          <span v-else class="text-sm text-on-surface-variant">{{ $t("doctor.runningChecks") }}</span>
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded border border-outline bg-surface px-3 py-2 text-sm text-on-surface-variant hover:border-primary"
            @click="openLogs"
          >
            <History :size="15" aria-hidden="true" />
            {{ $t("doctor.openLogs") }}
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
            :disabled="doctor.loading"
            @click="doctor.refresh()"
          >
            <Loader2 v-if="doctor.loading" :size="15" class="animate-spin" aria-hidden="true" />
            <RefreshCw v-else :size="15" aria-hidden="true" />
            {{ $t("doctor.rerun") }}
          </button>
        </div>
      </div>

      <!-- Diagnostics checks -->
      <section class="rounded-xl border border-outline-variant bg-surface-container">
        <h2 class="border-b border-outline-variant px-5 py-3 text-sm font-bold text-on-surface">
          {{ $t("doctor.diagnostics") }}
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
            {{ $t("doctor.noDiagnostics") }}
          </li>
        </ul>
      </section>

      <!-- Backups -->
      <section class="rounded-xl border border-outline-variant bg-surface-container">
        <div class="flex flex-wrap items-center gap-3 border-b border-outline-variant px-5 py-3">
          <h2 class="text-sm font-bold text-on-surface">
            {{ $t("doctor.backups") }}
            <span class="font-normal text-on-surface-variant">{{ $t("doctor.backupsSubtitle") }}</span>
          </h2>
          <div class="ml-auto flex items-center gap-3">
            <label class="flex items-center gap-1.5 text-xs text-on-surface-variant">
              {{ $t("doctor.keepLast") }}
              <input
                type="number"
                min="0"
                class="w-16 rounded border border-outline bg-surface px-2 py-1 text-xs text-on-surface"
                :value="settings.settings.backupRetention"
                @change="saveRetention(($event.target as HTMLInputElement).valueAsNumber)"
              />
              {{ $t("doctor.backupsWord") }}
            </label>
            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded border border-outline bg-surface px-3 py-1.5 text-xs font-semibold text-on-surface hover:border-error hover:text-error disabled:opacity-60"
              :disabled="doctor.pruning || !doctor.backupsReadable"
              @click="doctor.prune()"
            >
              <Loader2 v-if="doctor.pruning" :size="13" class="animate-spin" aria-hidden="true" />
              <Trash2 v-else :size="13" aria-hidden="true" />
              {{ $t("doctor.cleanupOld") }}
            </button>
          </div>
        </div>

        <p
          v-if="doctor.backups.length > 0"
          class="border-b border-outline-variant px-5 py-2 text-xs text-on-surface-variant"
        >
          {{ $t("doctor.backupsSummary", { count: doctor.backups.length, size: formatBytes(doctor.backupsTotalBytes), keep: doctor.backupRetention || "∞" }) }}
        </p>

        <div
          v-if="!doctor.backupsReadable"
          class="flex items-start gap-2 px-5 py-6 text-sm text-tertiary"
        >
          <AlertTriangle :size="18" class="mt-0.5 shrink-0" aria-hidden="true" />
          <span>
            {{ $t("doctor.backupsUnreadable") }}
          </span>
        </div>
        <div
          v-else-if="doctor.backups.length === 0"
          class="px-5 py-6 text-center text-sm text-on-surface-variant"
        >
          {{ $t("doctor.noBackups") }}
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
                {{ $t("doctor.backupMeta", { date: formatDate(backup.createdAt), size: formatBytes(backup.sizeBytes), count: backup.fileCount }) }}
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
              {{ $t("doctor.restore") }}
            </button>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
