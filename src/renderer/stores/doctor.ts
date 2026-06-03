import { defineStore } from "pinia";
import { ref } from "vue";
import type { DiagnosticsReport, RekordboxBackup } from "../lib/api";
import { useSystemStore } from "./system";
import { useUiStore } from "./ui";

export const useDoctorStore = defineStore("doctor", () => {
  const report = ref<DiagnosticsReport | null>(null);
  const backups = ref<RekordboxBackup[]>([]);
  const backupsReadable = ref(true);
  const backupRetention = ref(0);
  const backupsTotalBytes = ref(0);
  const loading = ref(false);
  const pruning = ref(false);
  const restoringName = ref<string | null>(null);

  async function refresh(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoadingFlag(loading, async () => {
      const [diagnostics, backupResult] = await Promise.all([
        system.api!.getDiagnostics(),
        system.api!.listBackups(),
      ]);
      report.value = diagnostics;
      backups.value = backupResult.backups;
      backupsReadable.value = backupResult.readable;
      backupRetention.value = backupResult.retention;
      backupsTotalBytes.value = backupResult.totalSizeBytes;
    });
  }

  async function prune(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoadingFlag(pruning, async () => {
      const result = await system.api!.pruneBackups();
      if (!result.readable) {
        ui.setMessage(
          "error",
          "Backups folder can't be read (cloud-storage permissions). Use the packaged app for backup management."
        );
      } else if (result.removed === 0) {
        ui.pushToast("info", "Nothing to clean up — backups are within the limit.");
      } else {
        ui.setMessage(
          "success",
          `Removed ${result.removed} old backup(s), freed ${(result.freedBytes / (1024 * 1024)).toFixed(0)} MB.`
        );
      }
      await refresh();
    });
  }

  async function restore(name: string): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withErrorToast(
      async () => {
        const result = await system.api!.restoreBackup(name);
        ui.setMessage(
          "success",
          `Restored ${result.restored} (${result.restoredFiles} file(s)). A safety backup was made.`
        );
        await refresh();
      },
      () => {
        restoringName.value = name;
        return () => {
          restoringName.value = null;
        };
      }
    );
  }

  return {
    report,
    backups,
    backupsReadable,
    backupRetention,
    backupsTotalBytes,
    loading,
    pruning,
    restoringName,
    refresh,
    restore,
    prune,
  };
});
