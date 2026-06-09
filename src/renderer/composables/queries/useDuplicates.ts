import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/vue-query";
import { computed, reactive, ref } from "vue";
import type {
  DuplicateGroup,
  DuplicateResolutionItem,
  DuplicateScanResult,
} from "../../lib/api";
import { useSystemStore } from "../../stores/system";
import { useUiStore } from "../../stores/ui";

interface ScanParams {
  strategies: string[];
  fuzzyThreshold: number;
}

/**
 * Duplicate detection backed by TanStack Query (reference slice for the Pinia ->
 * vue-query migration).
 *
 * Server state (the scan result) lives in the query cache instead of a Pinia
 * store: `scan()` is a *lazy* query keyed by the chosen strategies/threshold,
 * and resolving/dismissing a group is a mutation that prunes the cached result
 * in place — so we never pay for an expensive re-scan just to drop a row. The
 * query intentionally opts out of background refetching (`staleTime: Infinity`,
 * `refetchOnWindowFocus: false`): scanning the whole collection is heavy and must
 * only happen when the user clicks Scan. The few UI-only bits (detection toggles
 * and per-group keeper/delete overrides) stay as local refs here.
 *
 * Returned as a reactive() object so the view reads `duplicates.groups`, calls
 * `duplicates.scan()`, etc. exactly like the old store.
 */
export function useDuplicates() {
  const system = useSystemStore();
  const ui = useUiStore();
  const queryClient = useQueryClient();

  // --- UI-only state -------------------------------------------------------
  const useIsrc = ref(true);
  const useFuzzy = ref(true);
  const fuzzyThreshold = ref(0.87);
  const keeperOverride = reactive<Record<string, string>>({});
  const deleteFiles = reactive<Record<string, boolean>>({});
  // Which group is mid-resolve, for the per-row spinner.
  const resolvingGroupId = ref<string | null>(null);

  // --- Scan query (lazy) ---------------------------------------------------
  // Params of the last scan the user launched, kept separate from the live
  // toggles so flipping a checkbox doesn't refetch until they click Scan again.
  const scanParams = ref<ScanParams | null>(null);
  const queryKey = computed(() => ["duplicates", scanParams.value] as const);

  const query = useQuery({
    queryKey,
    enabled: computed(() => !!system.api && scanParams.value !== null),
    // keepPreviousData keeps the old groups on screen while a re-scan runs,
    // matching the old store (which only cleared results on success).
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    queryFn: () =>
      system.api!.scanDuplicates(
        scanParams.value!.strategies,
        scanParams.value!.fuzzyThreshold,
      ),
  });

  const result = computed<DuplicateScanResult | undefined>(() => query.data.value);
  const groups = computed<DuplicateGroup[]>(() =>
    result.value?.available ? result.value.groups : [],
  );
  const totalTracks = computed(() => result.value?.totalTracks ?? 0);
  const unavailableReason = computed(() =>
    result.value && !result.value.available
      ? result.value.reason ?? "Rekordbox database unavailable."
      : null,
  );
  const scanned = computed(() => result.value !== undefined);
  const scanning = computed(() => query.isFetching.value);

  const groupCount = computed(() => groups.value.length);
  // Only high-confidence ISRC groups (titles agree) are eligible for the
  // one-click bulk action; mismatched-title ISRC groups (confidence 60) need
  // manual review and are excluded.
  const isrcGroupCount = computed(
    () => groups.value.filter((g) => g.reason === "isrc" && g.confidence >= 99).length,
  );

  function scan(): void {
    const strategies: string[] = [];
    if (useIsrc.value) strategies.push("isrc");
    if (useFuzzy.value) strategies.push("fuzzy");
    if (strategies.length === 0) {
      ui.setMessage("error", "Select at least one detection strategy.");
      return;
    }
    const next: ScanParams = { strategies, fuzzyThreshold: fuzzyThreshold.value };
    // Query keys are hashed by value, so re-scanning with identical options
    // reuses the (Infinity-stale) cache instead of refetching — force it.
    const sameKey =
      scanParams.value !== null &&
      JSON.stringify(scanParams.value) === JSON.stringify(next);
    scanParams.value = next;
    // Drop overrides from a previous scan; surviving groups re-seed on demand.
    for (const key of Object.keys(keeperOverride)) delete keeperOverride[key];
    if (sameKey) void query.refetch();
  }

  // --- Keeper selection ----------------------------------------------------
  function keeperOf(group: DuplicateGroup): string {
    return keeperOverride[group.groupId] ?? group.keeperContentId;
  }
  function setKeeper(group: DuplicateGroup, contentId: string): void {
    keeperOverride[group.groupId] = contentId;
  }

  function buildItem(group: DuplicateGroup, dismiss = false): DuplicateResolutionItem {
    const keeper = keeperOf(group);
    return {
      groupId: group.groupId,
      keeperContentId: keeper,
      removeContentIds: group.tracks.map((t) => t.contentId).filter((id) => id !== keeper),
      deleteFiles: Boolean(deleteFiles[group.groupId]),
      dismiss,
    };
  }

  // Prune resolved/dismissed groups from the cached scan result so the UI
  // updates instantly without re-running the (heavy) scan.
  function dropGroupsFromCache(ids: Set<string>): void {
    queryClient.setQueryData<DuplicateScanResult>(queryKey.value, (old) =>
      old && old.available
        ? { ...old, groups: old.groups.filter((g) => !ids.has(g.groupId)) }
        : old,
    );
  }

  // --- Resolution mutation -------------------------------------------------
  const resolveMutation = useMutation({
    mutationFn: (items: DuplicateResolutionItem[]) =>
      system.api!.resolveDuplicates(items),
    onError: (error) =>
      ui.setMessage("error", error instanceof Error ? error.message : String(error)),
  });

  async function resolveGroup(group: DuplicateGroup): Promise<void> {
    resolvingGroupId.value = group.groupId;
    try {
      const r = await resolveMutation.mutateAsync([buildItem(group)]);
      const parts = [`${r.removedFromRekordbox} removed from Rekordbox`];
      if (r.filesDeleted) parts.push(`${r.filesDeleted} file(s) deleted`);
      if (r.relinkedPlaylists || r.relinkedTags) {
        parts.push(
          `re-linked ${r.relinkedPlaylists} playlist + ${r.relinkedTags} tag membership(s)`,
        );
      }
      if (r.skippedProtected) parts.push(`${r.skippedProtected} protected file(s) kept on disk`);
      ui.setMessage("success", `Resolved. ${parts.join(", ")}. A backup was made.`);
      dropGroupsFromCache(new Set([group.groupId]));
    } catch {
      /* error toast handled in the mutation's onError */
    } finally {
      resolvingGroupId.value = null;
    }
  }

  async function dismissGroup(group: DuplicateGroup): Promise<void> {
    resolvingGroupId.value = group.groupId;
    try {
      await resolveMutation.mutateAsync([buildItem(group, true)]);
      ui.pushToast("info", "Marked as not a duplicate. It won't show up again.");
      dropGroupsFromCache(new Set([group.groupId]));
    } catch {
      /* handled in onError */
    } finally {
      resolvingGroupId.value = null;
    }
  }

  async function resolveAllIsrc(): Promise<void> {
    const targets = groups.value.filter((g) => g.reason === "isrc" && g.confidence >= 99);
    if (targets.length === 0) return;
    try {
      const r = await resolveMutation.mutateAsync(targets.map((g) => buildItem(g)));
      ui.setMessage(
        "success",
        `Auto-resolved ${targets.length} ISRC group(s): ${r.removedFromRekordbox} removed, ${r.filesDeleted} file(s) deleted. Backup made.`,
      );
      dropGroupsFromCache(new Set(targets.map((g) => g.groupId)));
    } catch {
      /* handled in onError */
    }
  }

  return reactive({
    groups,
    totalTracks,
    scanned,
    scanning,
    resolvingGroupId,
    unavailableReason,
    useIsrc,
    useFuzzy,
    fuzzyThreshold,
    deleteFiles,
    groupCount,
    isrcGroupCount,
    keeperOf,
    setKeeper,
    scan,
    resolveGroup,
    dismissGroup,
    resolveAllIsrc,
  });
}
