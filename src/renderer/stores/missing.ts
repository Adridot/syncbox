import { defineStore } from "pinia";
import { reactive, ref } from "vue";
import type { MissingTrack, RelinkCandidate } from "../lib/api";
import { useApiAction } from "../composables/useApiAction";

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
  // Re-download is async (it enqueues an acquisition job visible in Download &
  // Match); we lock the row as "queued" rather than dropping it.
  const queued = ref<Set<string>>(new Set());

  const { run } = useApiAction();

  /** Busy-flag cleanup for a per-track action. */
  function lock(contentId: string, action: typeof busyAction.value) {
    return () => {
      busyId.value = contentId;
      busyAction.value = action;
      return () => {
        busyId.value = null;
        busyAction.value = null;
      };
    };
  }

  function drop(contentId: string): void {
    tracks.value = tracks.value.filter((t) => t.contentId !== contentId);
    delete candidates[contentId];
  }

  async function scan(): Promise<void> {
    scanning.value = true;
    await run((api) => api.scanMissingFiles(), {
      onSuccess: (report) => {
        if (!report.available) {
          unavailableReason.value = report.reason ?? "Rekordbox database unavailable.";
          tracks.value = [];
        } else {
          unavailableReason.value = null;
          tracks.value = report.tracks;
          total.value = report.total;
        }
        scanned.value = true;
      },
    });
    scanning.value = false;
  }

  async function remove(track: MissingTrack): Promise<void> {
    await run((api) => api.removeMissingEntry(track.contentId), {
      busy: lock(track.contentId, "remove"),
      success: (r) => `${r.message} A backup was made.`,
      onSuccess: () => drop(track.contentId),
    });
  }

  async function loadCandidates(track: MissingTrack): Promise<void> {
    candidatesLoading.value = track.contentId;
    await run((api) => api.getRelinkCandidates(track.contentId), {
      onSuccess: (list) => {
        candidates[track.contentId] = list;
      },
    });
    candidatesLoading.value = null;
  }

  async function relink(track: MissingTrack, filePath: string): Promise<void> {
    await run((api) => api.relinkMissingEntry(track.contentId, filePath), {
      busy: lock(track.contentId, "relink"),
      success: (r) => `${r.message} A backup was made.`,
      onSuccess: () => drop(track.contentId),
    });
  }

  async function redownload(track: MissingTrack): Promise<void> {
    await run((api) => api.redownloadMissingEntry(track.contentId), {
      busy: lock(track.contentId, "redownload"),
      success: (r) => r.message,
      onSuccess: () => {
        queued.value = new Set(queued.value).add(track.contentId);
      },
    });
  }

  return {
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
  };
});
