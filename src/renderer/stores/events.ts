import { defineStore } from "pinia";
import { computed, reactive, ref } from "vue";
import type {
  AcquisitionJob,
  DeezerSearchResult,
  EventAcquisitionResponse,
  EventReview,
  EventSummary,
  EventTrackReview,
  GlobalAcquisitionJob,
  LiveImportPackage,
  TrackReview,
} from "../lib/api";
import type { ImportFormState } from "../types/ui";
import { useSystemStore } from "./system";
import { useUiStore } from "./ui";
import { useProposalsStore } from "./proposals";

export const useEventsStore = defineStore("events", () => {
  const summaries = ref<EventSummary[]>([]);
  const activeEvent = ref<EventReview | null>(null);
  // The event the user last asked to view. Async loads/refreshes only apply
  // their result if it still matches, so rapid switching between events can't
  // be flipped back by a slow, out-of-order response.
  const requestedEventId = ref<number | null>(null);
  const acquisitionJobs = ref<AcquisitionJob[]>([]);
  const globalAcquisitionJobs = ref<GlobalAcquisitionJob[]>([]);
  const deezerSearchTrack = ref<TrackReview | null>(null);
  const deezerSearchQuery = ref("");
  const deezerSearchResults = ref<DeezerSearchResult[]>([]);
  const deezerSearchLoading = ref(false);
  const liveImportPackage = ref<LiveImportPackage | null>(null);
  const importForm = reactive<ImportFormState>({
    playlistUrl: "",
    eventName: "",
  });

  const readyToApply = computed(() => {
    if (!activeEvent.value) return false;
    return activeEvent.value.matchedTracks + activeEvent.value.readyTracks > 0;
  });

  // App-wide download activity, surfaced in the sidebar.
  const globalJobStats = computed(() => {
    const stats = { inProgress: 0, failed: 0, total: 0 };
    for (const job of globalAcquisitionJobs.value) {
      stats.total += 1;
      if (job.status === "queued" || job.status === "downloading") stats.inProgress += 1;
      if (job.status === "acquisition_failed") stats.failed += 1;
    }
    return stats;
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
    const [review, jobs, sums, globals] = await Promise.all([
      system.api.getEventReview(eventId),
      system.api.listAcquisitionJobs(eventId),
      system.api.listEvents(),
      system.api.listGlobalAcquisitionJobs(),
    ]);
    summaries.value = sums;
    globalAcquisitionJobs.value = globals;
    // Drop the result if the user navigated to another event meanwhile.
    if (requestedEventId.value !== eventId) return;
    activeEvent.value = review;
    acquisitionJobs.value = jobs;
  }

  async function scanStaging(): Promise<void> {
    const system = useSystemStore();
    if (!system.api || !activeEvent.value) return;
    const eventId = activeEvent.value.id;
    const [review, jobs, sums, globals] = await Promise.all([
      system.api.scanEventStaging(eventId),
      system.api.listAcquisitionJobs(eventId),
      system.api.listEvents(),
      system.api.listGlobalAcquisitionJobs(),
    ]);
    summaries.value = sums;
    globalAcquisitionJobs.value = globals;
    if (requestedEventId.value !== eventId) return;
    activeEvent.value = review;
    acquisitionJobs.value = jobs;
  }

  async function openEvent(summary: EventSummary): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    requestedEventId.value = summary.id;
    await ui.withLoading(async () => {
      const [review, jobs] = await Promise.all([
        system.api!.getEventReview(summary.id),
        system.api!.listAcquisitionJobs(summary.id),
      ]);
      // A newer click superseded this load — discard the stale result.
      if (requestedEventId.value !== summary.id) return;
      activeEvent.value = review;
      acquisitionJobs.value = jobs;
      ui.setMessage("success", `"${review.eventName}" loaded.`);
    });
  }

  // Deselect the active event to return to the creation screen.
  function closeActiveEvent(): void {
    requestedEventId.value = null;
    activeEvent.value = null;
    acquisitionJobs.value = [];
  }

  async function analyzeImport(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoading(async () => {
      const review = await system.api!.analyzeSpotifyEvent(importForm);
      requestedEventId.value = review.id;
      activeEvent.value = review;
      summaries.value = await system.api!.listEvents();
      ui.navigateTo("events");
      ui.setMessage("success", `${review.totalTracks} Spotify tracks analyzed.`);
      await autoDownload(review.id);
    });
  }

  async function createManualEvent(eventName: string): Promise<EventReview | null> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return null;
    const name = eventName.trim();
    if (!name) {
      ui.setMessage("error", "Event name is required.");
      return null;
    }
    const review = await ui.withLoading(async () => {
      const created = await system.api!.createManualEvent({ eventName: name });
      requestedEventId.value = created.id;
      activeEvent.value = created;
      acquisitionJobs.value = await system.api!.listAcquisitionJobs(created.id);
      summaries.value = await system.api!.listEvents();
      ui.navigateTo("events");
      ui.setMessage("success", `Event "${created.eventName}" created.`);
      return created;
    });
    return review ?? null;
  }

  async function addSpotifyTrack(eventId: number, trackUrl: string): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    requestedEventId.value = eventId;
    await ui.withLoading(async () => {
      activeEvent.value = await system.api!.addEventSpotifyTrack(eventId, trackUrl.trim());
      summaries.value = await system.api!.listEvents();
      ui.setMessage("success", "Track added to the event.");
      // Missing tracks are fetched automatically; only failures are surfaced.
      await autoDownload(eventId);
    });
  }

  async function addTrackToEvent(input: {
    url: string;
    targetEventId?: number | null;
    newEventName?: string;
  }): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    const url = input.url.trim();
    if (!url) {
      ui.setMessage("error", "Paste a Spotify track link first.");
      return;
    }
    const newName = input.newEventName?.trim();
    let eventId = input.targetEventId ?? null;
    if (newName) {
      const review = await createManualEvent(newName);
      if (!review) return;
      eventId = review.id;
    }
    if (!eventId) {
      ui.setMessage("error", "Choose a target event or create a new one.");
      return;
    }
    await addSpotifyTrack(eventId, url);
  }

  async function createLiveImportPackage(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    // Prefer the event currently open in the workspace; fall back to the
    // create-form name when preparing a standalone live import.
    const eventName = (activeEvent.value?.eventName ?? importForm.eventName).trim();
    if (!eventName) {
      ui.setMessage("error", "Open an event or enter a name for the live import.");
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
      const [review, jobs, sums] = await Promise.all([
        system.api!.scanEventStaging(eventId),
        system.api!.listAcquisitionJobs(eventId),
        system.api!.listEvents(),
      ]);
      summaries.value = sums;
      if (requestedEventId.value !== eventId) return;
      activeEvent.value = review;
      acquisitionJobs.value = jobs;
      ui.setMessage("success", `Folder refreshed. ${review.stagingFiles.length} staged file(s) found.`);
    });
  }

  // Tracks that genuinely failed to acquire: a failed job AND still missing.
  // A failed job left over on a track that is now matched/ready is ignored.
  function unresolvedFailures(result: EventAcquisitionResponse): string[] {
    const failedIds = new Set(
      result.jobs.filter((job) => job.status === "acquisition_failed").map((job) => job.spotifyTrackId)
    );
    return result.review.tracks
      .filter((track) => failedIds.has(track.spotifyTrackId) && track.status === "missing")
      .map((track) => track.title);
  }

  // Auto-acquire missing tracks for an event. Downloads happen silently; the
  // only message shown is a warning listing tracks not found on Deemix.
  async function autoDownload(eventId: number): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    const result = await system.api.runAutoAcquisition(eventId);
    summaries.value = await system.api.listEvents();
    globalAcquisitionJobs.value = await system.api.listGlobalAcquisitionJobs();
    if (requestedEventId.value !== eventId) return;
    activeEvent.value = result.review;
    acquisitionJobs.value = result.jobs;
    const failures = unresolvedFailures(result);
    if (failures.length > 0) {
      const shown = failures.slice(0, 6).join(", ") + (failures.length > 6 ? "…" : "");
      ui.setMessage("error", `${failures.length} titre(s) introuvable(s) sur Deemix : ${shown}`);
    }
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
      requestedEventId.value = null;
      activeEvent.value = null;
      acquisitionJobs.value = [];
      summaries.value = await system.api!.listEvents();
      globalAcquisitionJobs.value = await system.api!.listGlobalAcquisitionJobs();
      ui.setMessage("success", `Event deleted. Rekordbox tracks removed ${result.deletedFromRekordbox}, event tags removed ${result.removedEventTags}, protected ${result.protectedTracks}.`);
    });
  }

  async function assignStagingFile(track: TrackReview, value: string): Promise<void> {
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

  async function clearDownloads(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoading(async () => {
      const result = await system.api!.clearAcquisitionJobs();
      globalAcquisitionJobs.value = await system.api!.listGlobalAcquisitionJobs();
      if (activeEvent.value) {
        acquisitionJobs.value = await system.api!.listAcquisitionJobs(activeEvent.value.id);
      }
      ui.setMessage("success", `${result.cleared} download job(s) cleared.`);
    });
  }

  async function acceptSuggestedMatch(track: TrackReview): Promise<void> {
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

  function openDeezerSearch(track: TrackReview): void {
    deezerSearchTrack.value = track;
    deezerSearchQuery.value = `${track.artists[0] ?? ""} ${track.title}`.trim();
    deezerSearchResults.value = [];
  }

  function closeDeezerSearch(): void {
    deezerSearchTrack.value = null;
    deezerSearchQuery.value = "";
    deezerSearchResults.value = [];
  }

  async function runDeezerSearch(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeEvent.value || !deezerSearchQuery.value.trim()) return;
    await ui.withLoadingFlag(deezerSearchLoading, async () => {
      deezerSearchResults.value = await system.api!.searchEventDeezer(
        activeEvent.value!.id,
        deezerSearchQuery.value.trim()
      );
    });
  }

  async function queueDeezerTrack(deezerTrackId: string): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeEvent.value || !deezerSearchTrack.value) return;
    await ui.withLoading(async () => {
      const result = await system.api!.queueEventDeezerTrack(
        activeEvent.value!.id,
        deezerSearchTrack.value!.spotifyTrackId,
        deezerTrackId
      );
      closeDeezerSearch();
      await refreshActiveEvent();
      ui.setMessage("success", `Queued: ${result.title}`);
    });
  }

  async function ignoreTrack(track: TrackReview): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeEvent.value) return;
    await ui.withLoading(async () => {
      activeEvent.value = await system.api!.updateEventTrack(activeEvent.value!.id, {
        spotifyTrackId: track.spotifyTrackId,
        status: "ignored",
      });
      ui.setMessage("success", "Track ignored.");
    });
  }

  async function unignoreTrack(track: TrackReview): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeEvent.value) return;
    await ui.withLoading(async () => {
      activeEvent.value = await system.api!.updateEventTrack(activeEvent.value!.id, {
        spotifyTrackId: track.spotifyTrackId,
        status: "missing",
      });
      ui.setMessage("success", "Track restored.");
    });
  }

  return {
    summaries,
    activeEvent,
    acquisitionJobs,
    globalAcquisitionJobs,
    liveImportPackage,
    importForm,
    deezerSearchTrack,
    deezerSearchQuery,
    deezerSearchResults,
    deezerSearchLoading,
    readyToApply,
    acquisitionCounts,
    globalJobStats,
    refreshSummaries,
    refreshGlobalJobs,
    refreshActiveEvent,
    scanStaging,
    openEvent,
    closeActiveEvent,
    analyzeImport,
    createManualEvent,
    addSpotifyTrack,
    addTrackToEvent,
    createLiveImportPackage,
    refreshEventFolder,
    applyActiveEvent,
    deleteActiveEvent,
    assignStagingFile,
    acceptSuggestedMatch,
    clearDownloads,
    openDeezerSearch,
    closeDeezerSearch,
    runDeezerSearch,
    queueDeezerTrack,
    ignoreTrack,
    unignoreTrack,
  };
});
