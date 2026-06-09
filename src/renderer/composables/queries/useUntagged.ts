import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { computed, reactive, ref } from "vue";
import type {
  RekordboxTag,
  UntaggedReport,
  UntaggedSuggestion,
  UntaggedTrack,
} from "../../lib/api";
import { t } from "../../i18n";
import { useSystemStore } from "../../stores/system";
import { useUiStore } from "../../stores/ui";

const UNTAGGED_KEY = ["rekordbox", "untagged"] as const;

/**
 * Untagged-tracks review backed by TanStack Query (Pinia store replacement).
 * The report is loaded once when the view opens (enabled on api, staleTime
 * Infinity — reading the collection is heavy; the Refresh button refetches).
 * Tagging/deleting are mutations that prune the cached rows. Selection, search
 * and the suggestion filter are local UI state. Returned as reactive() so the
 * view keeps its `untagged.*` surface.
 */
export function useUntagged() {
  const system = useSystemStore();
  const ui = useUiStore();
  const queryClient = useQueryClient();

  // UI-only state.
  const selectedIds = ref<Set<string>>(new Set());
  const search = ref("");
  const suggestionFilter = ref<UntaggedSuggestion | "all">("all");

  const query = useQuery({
    queryKey: UNTAGGED_KEY,
    enabled: computed(() => !!system.api),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    queryFn: () => system.api!.getUntaggedTracks(),
  });

  const report = computed<UntaggedReport | undefined>(() => query.data.value);
  const tracks = computed<UntaggedTrack[]>(() =>
    report.value?.available ? report.value.tracks : [],
  );
  const tags = computed<RekordboxTag[]>(() =>
    report.value?.available ? report.value.tags : [],
  );
  const total = computed(() => report.value?.total ?? 0);
  const untaggedCount = computed(() => tracks.value.length);
  const unavailableReason = computed(() =>
    report.value && !report.value.available
      ? report.value.reason ?? "Rekordbox database unavailable."
      : null,
  );
  const scanned = computed(() => report.value !== undefined);
  const loading = computed(() => query.isFetching.value);

  const tagNames = computed(() =>
    [...new Set(tags.value.map((t) => t.name).filter(Boolean))].sort((a, b) =>
      a.localeCompare(b),
    ),
  );

  const filteredTracks = computed(() => {
    const q = search.value.trim().toLowerCase();
    return tracks.value.filter((t) => {
      if (suggestionFilter.value !== "all" && t.suggestion !== suggestionFilter.value) return false;
      if (!q) return true;
      return t.title.toLowerCase().includes(q) || t.artist.toLowerCase().includes(q);
    });
  });

  const counts = computed(() => {
    const by: Record<string, number> = { junk: 0, dup_of_tagged: 0, alt_version: 0, review: 0 };
    for (const t of tracks.value) by[t.suggestion] = (by[t.suggestion] ?? 0) + 1;
    return by;
  });

  const selectedTracks = computed(() =>
    tracks.value.filter((t) => selectedIds.value.has(t.contentId)),
  );
  const allFilteredSelected = computed(
    () =>
      filteredTracks.value.length > 0 &&
      filteredTracks.value.every((t) => selectedIds.value.has(t.contentId)),
  );

  function isSelected(contentId: string): boolean {
    return selectedIds.value.has(contentId);
  }
  function toggle(contentId: string, checked: boolean): void {
    const next = new Set(selectedIds.value);
    if (checked) next.add(contentId);
    else next.delete(contentId);
    selectedIds.value = next;
  }
  function toggleAllFiltered(checked: boolean): void {
    const next = new Set(selectedIds.value);
    for (const t of filteredTracks.value) {
      if (checked) next.add(t.contentId);
      else next.delete(t.contentId);
    }
    selectedIds.value = next;
  }
  function clearSelection(): void {
    selectedIds.value = new Set();
  }

  function dropFromCache(ids: Set<string>): void {
    queryClient.setQueryData<UntaggedReport>(UNTAGGED_KEY, (old) =>
      old && old.available
        ? { ...old, tracks: old.tracks.filter((t) => !ids.has(t.contentId)) }
        : old,
    );
    const next = new Set(selectedIds.value);
    for (const id of ids) next.delete(id);
    selectedIds.value = next;
  }

  const tagMutation = useMutation({
    mutationFn: (vars: { ids: string[]; name: string }) =>
      system.api!.tagUntaggedTracks(vars.ids, vars.name),
    onError: (e) => ui.setMessage("error", e instanceof Error ? e.message : String(e)),
  });
  const deleteMutation = useMutation({
    mutationFn: (ids: string[]) => system.api!.deleteUntaggedTracks(ids),
    onError: (e) => ui.setMessage("error", e instanceof Error ? e.message : String(e)),
  });
  const busy = computed(() => tagMutation.isPending.value || deleteMutation.isPending.value);

  async function load(): Promise<void> {
    await query.refetch();
  }

  async function applyTag(tagName: string): Promise<void> {
    const name = tagName.trim();
    const ids = [...selectedIds.value];
    if (!name || ids.length === 0) return;
    try {
      const r = await tagMutation.mutateAsync({ ids, name });
      ui.setMessage(
        "success",
        t("toast.untagged.tagged", {
          count: r.tagged,
          name: r.tagName,
          created: r.createdTag ? t("toast.untagged.tagCreated") : "",
        }),
      );
      dropFromCache(new Set(ids));
    } catch {
      /* handled in onError */
    }
  }

  async function deleteSelected(): Promise<void> {
    const ids = [...selectedIds.value];
    if (ids.length === 0) return;
    try {
      const r = await deleteMutation.mutateAsync(ids);
      ui.setMessage("success", t("toast.untagged.removed", { count: r.removed }));
      dropFromCache(new Set(ids));
    } catch {
      /* handled in onError */
    }
  }

  return reactive({
    tracks,
    tags,
    tagNames,
    total,
    untaggedCount,
    scanned,
    loading,
    busy,
    unavailableReason,
    selectedIds,
    selectedTracks,
    search,
    suggestionFilter,
    filteredTracks,
    counts,
    allFilteredSelected,
    isSelected,
    toggle,
    toggleAllFiltered,
    clearSelection,
    load,
    applyTag,
    deleteSelected,
  });
}
