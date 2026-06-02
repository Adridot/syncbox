import { defineStore } from "pinia";
import { reactive, ref } from "vue";
import type { MissingTrack, RelinkCandidate } from "../lib/api";
import { useSystemStore } from "./system";
import { useUiStore } from "./ui";

export const useMissingStore = defineStore("missing", () => {
  const tracks = ref<MissingTrack[]>([]);
  const total = ref(0);
  const scanned = ref(false);
  const scanning = ref(false);
  const unavailableReason = ref<string | null>(null);

  // Per-content transient state.
  const busyId = ref<string | null>(null);
  const busyAction = ref<"remove" | "redownload" | "relink" | null>(null);
  const candidates = reactive<Record<string, RelinkCandidate[]>>({});
  const candidatesLoading = ref<string | null>(null);

  async function scan(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    scanning.value = true;
    try {
      const report = await system.api.scanMissingFiles();
      if (!report.available) {
        unavailableReason.value = report.reason ?? "Rekordbox database unavailable.";
        tracks.value = [];
      } else {
        unavailableReason.value = null;
        tracks.value = report.tracks;
        total.value = report.total;
      }
      scanned.value = true;
    } catch (error) {
      ui.setMessage("error", error instanceof Error ? error.message : String(error));
    } finally {
      scanning.value = false;
    }
  }

  function drop(contentId: string): void {
    tracks.value = tracks.value.filter((t) => t.contentId !== contentId);
    delete candidates[contentId];
  }

  async function remove(track: MissingTrack): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    busyId.value = track.contentId;
    busyAction.value = "remove";
    try {
      const result = await system.api.removeMissingEntry(track.contentId);
      ui.setMessage("success", result.message + " A backup was made.");
      drop(track.contentId);
    } catch (error) {
      ui.setMessage("error", error instanceof Error ? error.message : String(error));
    } finally {
      busyId.value = null;
      busyAction.value = null;
    }
  }

  async function loadCandidates(track: MissingTrack): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    candidatesLoading.value = track.contentId;
    try {
      candidates[track.contentId] = await system.api.getRelinkCandidates(track.contentId);
    } catch (error) {
      ui.setMessage("error", error instanceof Error ? error.message : String(error));
    } finally {
      candidatesLoading.value = null;
    }
  }

  async function relink(track: MissingTrack, filePath: string): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    busyId.value = track.contentId;
    busyAction.value = "relink";
    try {
      const result = await system.api.relinkMissingEntry(track.contentId, filePath);
      ui.setMessage("success", result.message + " A backup was made.");
      drop(track.contentId);
    } catch (error) {
      ui.setMessage("error", error instanceof Error ? error.message : String(error));
    } finally {
      busyId.value = null;
      busyAction.value = null;
    }
  }

  async function redownload(track: MissingTrack): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    busyId.value = track.contentId;
    busyAction.value = "redownload";
    try {
      const result = await system.api.redownloadMissingEntry(track.contentId);
      ui.setMessage("success", result.message + " A backup was made.");
      drop(track.contentId);
    } catch (error) {
      ui.setMessage("error", error instanceof Error ? error.message : String(error));
    } finally {
      busyId.value = null;
      busyAction.value = null;
    }
  }

  return {
    tracks,
    total,
    scanned,
    scanning,
    unavailableReason,
    busyId,
    busyAction,
    candidates,
    candidatesLoading,
    scan,
    remove,
    loadCandidates,
    relink,
    redownload,
  };
});
