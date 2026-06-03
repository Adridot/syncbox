import { defineStore } from "pinia";
import { computed, ref } from "vue";
import type { RekordboxTag, UntaggedSuggestion, UntaggedTrack } from "../lib/api";
import { useApiAction } from "../composables/useApiAction";

export const useUntaggedStore = defineStore("untagged", () => {
  const tracks = ref<UntaggedTrack[]>([]);
  const tags = ref<RekordboxTag[]>([]);
  const total = ref(0);
  const untaggedCount = ref(0);
  const scanned = ref(false);
  const loading = ref(false);
  const busy = ref(false);
  const unavailableReason = ref<string | null>(null);

  // Selection + filters.
  const selectedIds = ref<Set<string>>(new Set());
  const search = ref("");
  const suggestionFilter = ref<UntaggedSuggestion | "all">("all");

  const { run } = useApiAction();

  const tagNames = computed(() =>
    [...new Set(tags.value.map((t) => t.name).filter(Boolean))].sort((a, b) =>
      a.localeCompare(b)
    )
  );

  const filteredTracks = computed(() => {
    const query = search.value.trim().toLowerCase();
    return tracks.value.filter((t) => {
      if (suggestionFilter.value !== "all" && t.suggestion !== suggestionFilter.value) {
        return false;
      }
      if (!query) return true;
      return (
        t.title.toLowerCase().includes(query) || t.artist.toLowerCase().includes(query)
      );
    });
  });

  const counts = computed(() => {
    const by: Record<string, number> = { junk: 0, dup_of_tagged: 0, alt_version: 0, review: 0 };
    for (const t of tracks.value) by[t.suggestion] = (by[t.suggestion] ?? 0) + 1;
    return by;
  });

  const selectedTracks = computed(() =>
    tracks.value.filter((t) => selectedIds.value.has(t.contentId))
  );

  const allFilteredSelected = computed(
    () =>
      filteredTracks.value.length > 0 &&
      filteredTracks.value.every((t) => selectedIds.value.has(t.contentId))
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

  function drop(ids: Set<string>): void {
    tracks.value = tracks.value.filter((t) => !ids.has(t.contentId));
    untaggedCount.value = tracks.value.length;
    const next = new Set(selectedIds.value);
    for (const id of ids) next.delete(id);
    selectedIds.value = next;
  }

  async function load(): Promise<void> {
    loading.value = true;
    await run((api) => api.getUntaggedTracks(), {
      onSuccess: (report) => {
        if (!report.available) {
          unavailableReason.value = report.reason ?? "Rekordbox database unavailable.";
          tracks.value = [];
          tags.value = [];
        } else {
          unavailableReason.value = null;
          tracks.value = report.tracks;
          tags.value = report.tags;
          total.value = report.total;
          untaggedCount.value = report.untagged;
        }
        scanned.value = true;
        clearSelection();
      },
    });
    loading.value = false;
  }

  async function applyTag(tagName: string): Promise<void> {
    const name = tagName.trim();
    const ids = [...selectedIds.value];
    if (!name || ids.length === 0) return;
    await run((api) => api.tagUntaggedTracks(ids, name), {
      busy: () => {
        busy.value = true;
        return () => (busy.value = false);
      },
      success: (r) =>
        `Tagged ${r.tagged} track(s) with “${r.tagName}”${
          r.createdTag ? " (new tag created)" : ""
        }. A backup was made.`,
      onSuccess: () => drop(new Set(ids)),
    });
  }

  async function deleteSelected(): Promise<void> {
    const ids = [...selectedIds.value];
    if (ids.length === 0) return;
    await run((api) => api.deleteUntaggedTracks(ids), {
      busy: () => {
        busy.value = true;
        return () => (busy.value = false);
      },
      success: (r) => `Removed ${r.removed} track(s) from the collection. A backup was made.`,
      onSuccess: () => drop(new Set(ids)),
    });
  }

  return {
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
  };
});
