import { defineStore } from "pinia";
import { ref } from "vue";
import type { DiagnosticsReport, RekordboxBackup } from "../lib/api";
import { useSystemStore } from "./system";
import { useUiStore } from "./ui";

export const useDoctorStore = defineStore("doctor", () => {
  const report = ref<DiagnosticsReport | null>(null);
  const backups = ref<RekordboxBackup[]>([]);
  const loading = ref(false);
  const restoringName = ref<string | null>(null);

  async function refresh(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoadingFlag(loading, async () => {
      const [diagnostics, backupList] = await Promise.all([
        system.api!.getDiagnostics(),
        system.api!.listBackups(),
      ]);
      report.value = diagnostics;
      backups.value = backupList;
    });
  }

  async function restore(name: string): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    restoringName.value = name;
    try {
      const result = await system.api.restoreBackup(name);
      ui.setMessage(
        "success",
        `Restored ${result.restored} (${result.restoredFiles} file(s)). A safety backup was made.`
      );
      await refresh();
    } catch (error) {
      ui.setMessage("error", error instanceof Error ? error.message : String(error));
    } finally {
      restoringName.value = null;
    }
  }

  return { report, backups, loading, restoringName, refresh, restore };
});
