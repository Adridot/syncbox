import { useQuery, useQueryClient } from "@tanstack/vue-query";
import { computed, reactive, ref } from "vue";
import type { MissingFilesReport, MissingTrack, RelinkCandidate } from "../../lib/api";
import { t } from "../../i18n";
import { useSystemStore } from "../../stores/system";
import { useUiStore } from "../../stores/ui";

const MISSING_KEY = ["rekordbox", "missing"] as const;

/**
 * Missing-files scan backed by TanStack Query (Pinia store replacement).
 * The scan reads the whole collection, so like Duplicates it's a lazy query
 * (manual only — staleTime Infinity, no refetch-on-focus). Remove/relink are
 * mutations that drop the row from the cached report; re-download enqueues a job
 * and just locks the row. Returned as reactive() so the view keeps reading
 * `missing.tracks`, calling `missing.scan()`, etc. like the old store.
 */
export function useMissing() {
  const system = useSystemStore();
  const ui = useUiStore();
  const queryClient = useQueryClient();

  // Per-track transient UI state (unchanged from the store).
  const busyId = ref<string | null>(null);
  const busyAction = ref<"remove" | "redownload" | "relink" | null>(null);
  const candidates = reactive<Record<string, RelinkCandidate[]>>({});
  const candidatesLoading = ref<string | null>(null);
  // Re-download is async (a job shown in Download & Match); lock the row as
  // "queued" rather than dropping it.
  const queued = ref<Set<string>>(new Set());

  const hasScanned = ref(false);
  const query = useQuery({
    queryKey: MISSING_KEY,
    enabled: computed(() => !!system.api && hasScanned.value),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    queryFn: () => system.api!.scanMissingFiles(),
  });

  const report = computed<MissingFilesReport | undefined>(() => query.data.value);
  const tracks = computed<MissingTrack[]>(() =>
    report.value?.available ? report.value.tracks : [],
  );
  const total = computed(() => report.value?.total ?? 0);
  const unavailableReason = computed(() =>
    report.value && !report.value.available
      ? report.value.reason ?? "Rekordbox database unavailable."
      : null,
  );
  const scanned = computed(() => report.value !== undefined);
  const scanning = computed(() => query.isFetching.value);

  function scan(): void {
    if (hasScanned.value) void query.refetch();
    else hasScanned.value = true; // enabling the query auto-fetches
  }

  function drop(contentId: string): void {
    queryClient.setQueryData<MissingFilesReport>(MISSING_KEY, (old) =>
      old && old.available
        ? { ...old, tracks: old.tracks.filter((t) => t.contentId !== contentId) }
        : old,
    );
    delete candidates[contentId];
  }

  function lock(contentId: string, action: typeof busyAction.value): void {
    busyId.value = contentId;
    busyAction.value = action;
  }
  function unlock(): void {
    busyId.value = null;
    busyAction.value = null;
  }

  const remove = async (track: MissingTrack): Promise<void> => {
    lock(track.contentId, "remove");
    try {
      const r = await system.api!.removeMissingEntry(track.contentId);
      ui.setMessage("success", `${r.message} ${t("toast.backupMade")}`);
      drop(track.contentId);
    } catch (e) {
      ui.setMessage("error", e instanceof Error ? e.message : String(e));
    } finally {
      unlock();
    }
  };

  const relink = async (track: MissingTrack, filePath: string): Promise<void> => {
    lock(track.contentId, "relink");
    try {
      const r = await system.api!.relinkMissingEntry(track.contentId, filePath);
      ui.setMessage("success", `${r.message} ${t("toast.backupMade")}`);
      drop(track.contentId);
    } catch (e) {
      ui.setMessage("error", e instanceof Error ? e.message : String(e));
    } finally {
      unlock();
    }
  };

  const redownload = async (track: MissingTrack): Promise<void> => {
    lock(track.contentId, "redownload");
    try {
      const r = await system.api!.redownloadMissingEntry(track.contentId);
      ui.setMessage("success", r.message);
      queued.value = new Set(queued.value).add(track.contentId);
    } catch (e) {
      ui.setMessage("error", e instanceof Error ? e.message : String(e));
    } finally {
      unlock();
    }
  };

  async function loadCandidates(track: MissingTrack): Promise<void> {
    candidatesLoading.value = track.contentId;
    try {
      candidates[track.contentId] = await system.api!.getRelinkCandidates(track.contentId);
    } catch (e) {
      ui.setMessage("error", e instanceof Error ? e.message : String(e));
    } finally {
      candidatesLoading.value = null;
    }
  }

  return reactive({
    tracks,
    total,
    scanned,
    scanning,
    unavailableReason,
    busyId,
    busyAction,
    queued,
    candidates,
    candidatesLoading,
    scan,
    remove,
    loadCandidates,
    relink,
    redownload,
  });
}
