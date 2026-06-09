import { useMutation, useQuery } from "@tanstack/vue-query";
import { computed, reactive, ref } from "vue";
import type { DiagnosticsReport, RekordboxBackup } from "../../lib/api";
import { useSystemStore } from "../../stores/system";
import { useUiStore } from "../../stores/ui";

/**
 * Doctor (diagnostics + Rekordbox backups) backed by TanStack Query (Pinia
 * store replacement). The report loads when the view opens; prune/restore are
 * mutations that refetch on success. Returned as reactive() so the view keeps
 * its `doctor.*` surface.
 */
export function useDoctor() {
  const system = useSystemStore();
  const ui = useUiStore();

  const restoringName = ref<string | null>(null);

  const query = useQuery({
    queryKey: ["doctor"],
    enabled: computed(() => !!system.api),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const api = system.api!;
      const [diagnostics, backupResult] = await Promise.all([
        api.getDiagnostics(),
        api.listBackups(),
      ]);
      return { diagnostics, backupResult };
    },
  });

  const report = computed<DiagnosticsReport | null>(() => query.data.value?.diagnostics ?? null);
  const backups = computed<RekordboxBackup[]>(() => query.data.value?.backupResult.backups ?? []);
  const backupsReadable = computed(() => query.data.value?.backupResult.readable ?? true);
  const backupRetention = computed(() => query.data.value?.backupResult.retention ?? 0);
  const backupsTotalBytes = computed(() => query.data.value?.backupResult.totalSizeBytes ?? 0);
  const loading = computed(() => query.isFetching.value);

  async function refresh(): Promise<void> {
    await query.refetch();
  }

  const pruneMutation = useMutation({
    mutationFn: () => system.api!.pruneBackups(),
    onError: (e) => ui.setMessage("error", e instanceof Error ? e.message : String(e)),
  });
  const pruning = computed(() => pruneMutation.isPending.value);

  async function prune(): Promise<void> {
    try {
      const result = await pruneMutation.mutateAsync();
      if (!result.readable) {
        ui.setMessage(
          "error",
          "Backups folder can't be read (cloud-storage permissions). Use the packaged app for backup management.",
        );
      } else if (result.removed === 0) {
        ui.pushToast("info", "Nothing to clean up — backups are within the limit.");
      } else {
        ui.setMessage(
          "success",
          `Removed ${result.removed} old backup(s), freed ${(result.freedBytes / (1024 * 1024)).toFixed(0)} MB.`,
        );
      }
      await refresh();
    } catch {
      /* handled in onError */
    }
  }

  async function restore(name: string): Promise<void> {
    restoringName.value = name;
    try {
      const result = await system.api!.restoreBackup(name);
      ui.setMessage(
        "success",
        `Restored ${result.restored} (${result.restoredFiles} file(s)). A safety backup was made.`,
      );
      await refresh();
    } catch (e) {
      ui.setMessage("error", e instanceof Error ? e.message : String(e));
    } finally {
      restoringName.value = null;
    }
  }

  return reactive({
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
  });
}
