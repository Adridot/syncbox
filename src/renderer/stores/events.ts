import { defineStore } from "pinia";
import { computed, reactive, ref } from "vue";
import type {
  AcquisitionJob,
  EventReview,
  EventSummary,
  EventTrackReview,
  GlobalAcquisitionJob,
  LiveImportPackage,
} from "../lib/api";
import type { ImportFormState } from "../types/ui";
import { useSystemStore } from "./system";
import { useUiStore } from "./ui";
import { useProposalsStore } from "./proposals";

export const useEventsStore = defineStore("events", () => {
  const summaries = ref<EventSummary[]>([]);
  const activeEvent = ref<EventReview | null>(null);
  const acquisitionJobs = ref<AcquisitionJob[]>([]);
  const globalAcquisitionJobs = ref<GlobalAcquisitionJob[]>([]);
  const liveImportPackage = ref<LiveImportPackage | null>(null);
  const reviewFilter = ref("all");

  const importForm = reactive<ImportFormState>({
    playlistUrl: "",
    eventName: "",
  });

  const filteredTracks = computed(() => {
    if (!activeEvent.value) return [];
    if (reviewFilter.value === "all") return activeEvent.value.tracks;
    return activeEvent.value.tracks.filter((t) => t.status === reviewFilter.value);
  });

  const readyToApply = computed(() => {
    if (!activeEvent.value) return false;
    return activeEvent.value.matchedTracks + activeEvent.value.readyTracks > 0;
  });

  const acquisitionCounts = computed(() => {
    const counts = { queued: 0, downloading: 0, downloaded: 0, ready: 0, failed: 0, ambiguous: 0 };
    for (const job of acquisitionJobs.value) {
      if (job.status === "queued") counts.queued += 1;
      if (job.status === "downloading") counts.downloading += 1;
      if (job.status === "downloaded") counts.downloaded += 1;
      if (job.status === "ready") counts.ready += 1;
      if (job.status === "acquisition_failed") counts.failed += 1;
      if (job.status === "acquisition_ambiguous") counts.ambiguous += 1;
    }
    return counts;
  });

  async function refreshSummaries(): Promise<void> {
    const system = useSystemStore();
    if (!system.api) return;
    summaries.value = await system.api.listEvents();
  }

  async function refreshGlobalJobs(scope?: string): Promise<void> {
    const system = useSystemStore();
    if (!system.api) return;
    globalAcquisitionJobs.value = await system.api.listGlobalAcquisitionJobs(
      scope ? { scope } : undefined
    );
  }

  async function refreshActiveEvent(): Promise<void> {
    const system = useSystemStore();
    if (!system.api || !activeEvent.value) return;
    const eventId = activeEvent.value.id;
    [activeEvent.value, acquisitionJobs.value, summaries.value, globalAcquisitionJobs.value] =
      await Promise.all([
        system.api.getEventReview(eventId),
        system.api.listAcquisitionJobs(eventId),
        system.api.listEvents(),
        system.api.listGlobalAcquisitionJobs(),
      ]);
  }

  async function scanStaging(): Promise<void> {
    const system = useSystemStore();
    if (!system.api || !activeEvent.value) return;
    const eventId = activeEvent.value.id;
    [activeEvent.value, acquisitionJobs.value, summaries.value, globalAcquisitionJobs.value] =
      await Promise.all([
        system.api.scanEventStaging(eventId),
        system.api.listAcquisitionJobs(eventId),
        system.api.listEvents(),
        system.api.listGlobalAcquisitionJobs(),
      ]);
  }

  async function openEvent(summary: EventSummary): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoading(async () => {
      activeEvent.value = await system.api!.getEventReview(summary.id);
      acquisitionJobs.value = await system.api!.listAcquisitionJobs(summary.id);
      ui.setMessage("success", `"${activeEvent.value!.eventName}" loaded.`);
    });
  }

  async function analyzeImport(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoading(async () => {
      activeEvent.value = await system.api!.analyzeSpotifyEvent(importForm);
      acquisitionJobs.value = await system.api!.listAcquisitionJobs(activeEvent.value!.id);
      summaries.value = await system.api!.listEvents();
      ui.navigateTo("events");
      ui.setMessage("success", `${activeEvent.value!.totalTracks} Spotify tracks analyzed.`);
    });
  }

  async function createLiveImportPackage(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    const eventName = importForm.eventName.trim();
    if (!eventName) {
      ui.setMessage("error", "Event name is required for live import.");
      return;
    }
    await ui.withLoading(async () => {
      liveImportPackage.value = await system.api!.createLiveImport({ eventName });
      ui.setMessage("success", `Live import ready with ${liveImportPackage.value!.trackCount} audio file(s).`);
    });
  }

  async function refreshEventFolder(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeEvent.value) return;
    await ui.withLoading(async () => {
      const eventId = activeEvent.value!.id;
      activeEvent.value = await system.api!.scanEventStaging(eventId);
      acquisitionJobs.value = await system.api!.listAcquisitionJobs(eventId);
      summaries.value = await system.api!.listEvents();
      ui.setMessage("success", `Folder refreshed. ${activeEvent.value!.stagingFiles.length} staged file(s) found.`);
    });
  }

  async function downloadMissingTracks(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeEvent.value) return;
    await ui.withLoading(async () => {
      const result = await system.api!.runAutoAcquisition(activeEvent.value!.id);
      activeEvent.value = result.review;
      acquisitionJobs.value = result.jobs;
      summaries.value = await system.api!.listEvents();
      globalAcquisitionJobs.value = await system.api!.listGlobalAcquisitionJobs();
      ui.setMessage("success", `Download started. Queued ${result.queued}, failed ${result.failed}, ambiguous ${result.ambiguous}.`);
    });
  }

  async function applyActiveEvent(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeEvent.value) return;
    await ui.withLoading(async () => {
      const result = await system.api!.applyEvent(activeEvent.value!.id);
      activeEvent.value = await system.api!.getEventReview(activeEvent.value!.id);
      acquisitionJobs.value = await system.api!.listAcquisitionJobs(activeEvent.value!.id);
      summaries.value = await system.api!.listEvents();
      ui.setMessage(
        result.warnings.length > 0 ? "error" : "success",
        `Event applied. Imported ${result.imported}, tagged ${result.tagged}, Spotify additions ${result.spotifyAdded}. ${result.warnings.join(" ")}`
      );
    });
  }

  async function deleteActiveEvent(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeEvent.value) return;
    await ui.withLoading(async () => {
      const eventId = activeEvent.value!.id;
      const preview = await system.api!.previewEventDelete(eventId);
      const details = preview.localOnly
        ? "This event matches a permanent playlist source. Only the temporary event entry will be removed from the app."
        : `This will remove ${preview.willRemoveEventTag} event tag link(s) and remove ${preview.willDeleteFromRekordbox} track(s) from the Rekordbox collection. ${preview.protectedTracks} track(s) will be kept because they have other tags or are stored as permanent/manual tracks.`;
      const confirmed = window.confirm(
        `Delete temporary event "${preview.eventName}"?\n\n${details}\n\nAudio files on disk will not be deleted.`
      );
      if (!confirmed) return;
      const result = await system.api!.deleteEvent(eventId);
      activeEvent.value = null;
      acquisitionJobs.value = [];
      summaries.value = await system.api!.listEvents();
      globalAcquisitionJobs.value = await system.api!.listGlobalAcquisitionJobs();
      ui.setMessage("success", `Event deleted. Rekordbox tracks removed ${result.deletedFromRekordbox}, event tags removed ${result.removedEventTags}, protected ${result.protectedTracks}.`);
    });
  }

  async function updatePermanent(track: EventTrackReview, permanent: boolean): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeEvent.value) return;
    await ui.withLoading(async () => {
      activeEvent.value = await system.api!.updateEventTrack(activeEvent.value!.id, {
        spotifyTrackId: track.spotifyTrackId,
        permanent,
      });
    });
  }

  async function updateTrackTags(track: EventTrackReview, value: string): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeEvent.value) return;
    const tags = value.split(",").map((t) => t.trim()).filter(Boolean);
    await ui.withLoading(async () => {
      activeEvent.value = await system.api!.updateEventTrack(activeEvent.value!.id, {
        spotifyTrackId: track.spotifyTrackId,
        tags,
      });
      ui.setMessage("success", "Track tags updated.");
    });
  }

  async function assignStagingFile(track: EventTrackReview, value: string): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeEvent.value || !value) return;
    await ui.withLoading(async () => {
      activeEvent.value = await system.api!.updateEventTrack(activeEvent.value!.id, {
        spotifyTrackId: track.spotifyTrackId,
        stagingFilePath: value,
        status: "ready",
      });
      ui.setMessage("success", "Staged file assigned.");
    });
  }

  async function acceptSuggestedMatch(track: EventTrackReview): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeEvent.value || !track.rekordboxContentId) return;
    await ui.withLoading(async () => {
      activeEvent.value = await system.api!.updateEventTrack(activeEvent.value!.id, {
        spotifyTrackId: track.spotifyTrackId,
        rekordboxContentId: track.rekordboxContentId,
        status: "matched",
      });
      ui.setMessage("success", "Suggested Rekordbox match accepted.");
    });
  }

  function selectSpotifyPlaylist(playlist: { url: string; name: string }): void {
    const ui = useUiStore();
    importForm.playlistUrl = playlist.url;
    if (!importForm.eventName.trim()) {
      importForm.eventName = playlist.name;
    }
    liveImportPackage.value = null;
    ui.navigateTo("events");
    ui.setMessage("success", `"${playlist.name}" selected.`);
  }

  return {
    summaries,
    activeEvent,
    acquisitionJobs,
    globalAcquisitionJobs,
    liveImportPackage,
    reviewFilter,
    importForm,
    filteredTracks,
    readyToApply,
    acquisitionCounts,
    refreshSummaries,
    refreshGlobalJobs,
    refreshActiveEvent,
    scanStaging,
    openEvent,
    analyzeImport,
    createLiveImportPackage,
    refreshEventFolder,
    downloadMissingTracks,
    applyActiveEvent,
    deleteActiveEvent,
    updatePermanent,
    updateTrackTags,
    assignStagingFile,
    acceptSuggestedMatch,
    selectSpotifyPlaylist,
  };
});
