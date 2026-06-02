import { defineStore } from "pinia";
import { computed, reactive, ref } from "vue";
import type { DuplicateGroup, DuplicateResolutionItem } from "../lib/api";
import { useSystemStore } from "./system";
import { useUiStore } from "./ui";

export const useDuplicatesStore = defineStore("duplicates", () => {
  const groups = ref<DuplicateGroup[]>([]);
  const totalTracks = ref(0);
  const scanned = ref(false);
  const scanning = ref(false);
  const resolvingGroupId = ref<string | null>(null);
  const unavailableReason = ref<string | null>(null);

  // Detection options.
  const useIsrc = ref(true);
  const useFuzzy = ref(true);
  const fuzzyThreshold = ref(0.87);

  // Per-group user overrides (keyed by groupId).
  const keeperOverride = reactive<Record<string, string>>({});
  const deleteFiles = reactive<Record<string, boolean>>({});

  const groupCount = computed(() => groups.value.length);
  // Only high-confidence ISRC groups (titles agree) are eligible for the
  // one-click bulk action; mismatched-title ISRC groups (confidence 60) need
  // manual review and are excluded.
  const isrcGroupCount = computed(
    () => groups.value.filter((g) => g.reason === "isrc" && g.confidence >= 99).length
  );

  function keeperOf(group: DuplicateGroup): string {
    return keeperOverride[group.groupId] ?? group.keeperContentId;
  }

  function setKeeper(group: DuplicateGroup, contentId: string): void {
    keeperOverride[group.groupId] = contentId;
  }

  async function scan(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    const strategies: string[] = [];
    if (useIsrc.value) strategies.push("isrc");
    if (useFuzzy.value) strategies.push("fuzzy");
    if (strategies.length === 0) {
      ui.setMessage("error", "Select at least one detection strategy.");
      return;
    }
    scanning.value = true;
    try {
      const result = await system.api.scanDuplicates(strategies, fuzzyThreshold.value);
      if (!result.available) {
        unavailableReason.value = result.reason ?? "Rekordbox database unavailable.";
        groups.value = [];
      } else {
        unavailableReason.value = null;
        groups.value = result.groups;
        totalTracks.value = result.totalTracks;
      }
      // Reset overrides for groups that no longer exist.
      for (const key of Object.keys(keeperOverride)) {
        if (!groups.value.some((g) => g.groupId === key)) delete keeperOverride[key];
      }
      scanned.value = true;
    } catch (error) {
      ui.setMessage("error", error instanceof Error ? error.message : String(error));
    } finally {
      scanning.value = false;
    }
  }

  function buildItem(group: DuplicateGroup, dismiss = false): DuplicateResolutionItem {
    const keeper = keeperOf(group);
    return {
      groupId: group.groupId,
      keeperContentId: keeper,
      removeContentIds: group.tracks
        .map((t) => t.contentId)
        .filter((id) => id !== keeper),
      deleteFiles: Boolean(deleteFiles[group.groupId]),
      dismiss,
    };
  }

  async function resolveGroup(group: DuplicateGroup): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    resolvingGroupId.value = group.groupId;
    try {
      const result = await system.api.resolveDuplicates([buildItem(group)]);
      const parts = [`${result.removedFromRekordbox} removed from Rekordbox`];
      if (result.filesDeleted) parts.push(`${result.filesDeleted} file(s) deleted`);
      if (result.relinkedPlaylists || result.relinkedTags) {
        parts.push(
          `re-linked ${result.relinkedPlaylists} playlist + ${result.relinkedTags} tag membership(s)`
        );
      }
      if (result.skippedProtected) {
        parts.push(`${result.skippedProtected} protected file(s) kept on disk`);
      }
      ui.setMessage("success", `Resolved. ${parts.join(", ")}. A backup was made.`);
      groups.value = groups.value.filter((g) => g.groupId !== group.groupId);
    } catch (error) {
      ui.setMessage("error", error instanceof Error ? error.message : String(error));
    } finally {
      resolvingGroupId.value = null;
    }
  }

  async function dismissGroup(group: DuplicateGroup): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    resolvingGroupId.value = group.groupId;
    try {
      await system.api.resolveDuplicates([buildItem(group, true)]);
      ui.pushToast("info", "Marked as not a duplicate. It won't show up again.");
      groups.value = groups.value.filter((g) => g.groupId !== group.groupId);
    } catch (error) {
      ui.setMessage("error", error instanceof Error ? error.message : String(error));
    } finally {
      resolvingGroupId.value = null;
    }
  }

  async function resolveAllIsrc(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    const targets = groups.value.filter((g) => g.reason === "isrc" && g.confidence >= 99);
    if (targets.length === 0) return;
    scanning.value = true;
    try {
      const items = targets.map((g) => buildItem(g));
      const result = await system.api.resolveDuplicates(items);
      ui.setMessage(
        "success",
        `Auto-resolved ${targets.length} ISRC group(s): ${result.removedFromRekordbox} removed, ${result.filesDeleted} file(s) deleted. Backup made.`
      );
      const done = new Set(targets.map((g) => g.groupId));
      groups.value = groups.value.filter((g) => !done.has(g.groupId));
    } catch (error) {
      ui.setMessage("error", error instanceof Error ? error.message : String(error));
    } finally {
      scanning.value = false;
    }
  }

  return {
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
  };
});
