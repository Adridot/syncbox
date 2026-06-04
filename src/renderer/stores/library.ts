import { defineStore } from "pinia";
import { computed, reactive, ref } from "vue";
import type {
  DeezerSearchResult,
  GlobalAcquisitionJob,
  LibraryDownloadResponse,
  LibraryReview,
  LibrarySource,
  LibraryTrackReview,
  TagRule,
  TrackReview,
} from "../lib/api";
import type { TagRuleFormState } from "../types/ui";
import { useSystemStore } from "./system";
import { useUiStore } from "./ui";
import { useSpotifyStore } from "./spotify";

export const useLibraryStore = defineStore("library", () => {
  const sources = ref<LibrarySource[]>([]);
  const activeReview = ref<LibraryReview | null>(null);
  const selectedTrackIds = ref<string[]>([]);
  const tagRules = ref<TagRule[]>([]);
  const globalAcquisitionJobs = ref<GlobalAcquisitionJob[]>([]);
  const tagRuleTagInput = ref("");

  // Deezer search panel state
  const deezerSearchTrack = ref<TrackReview | null>(null);
  const deezerSearchQuery = ref("");
  const deezerSearchResults = ref<DeezerSearchResult[]>([]);
  const deezerSearchLoading = ref(false);

  const tagRuleForm = reactive<TagRuleFormState>({
    sourcePlaylistId: "",
    sourcePlaylistName: "",
    tags: [],
  });

  const selectedTracks = computed(() => {
    if (!activeReview.value) return [];
    const selected = new Set(selectedTrackIds.value);
    return activeReview.value.tracks.filter((t) => selected.has(t.spotifyTrackId));
  });

  const readyToApply = computed(() => {
    if (!activeReview.value) return false;
    return activeReview.value.matchedTracks + activeReview.value.readyTracks > 0;
  });

  async function refreshSources(): Promise<void> {
    const system = useSystemStore();
    if (!system.api) return;
    sources.value = await system.api.listLibrarySources();
  }

  async function refreshTagRules(): Promise<void> {
    const system = useSystemStore();
    if (!system.api) return;
    tagRules.value = await system.api.listTagRules();
  }

  async function refreshGlobalJobs(): Promise<void> {
    const system = useSystemStore();
    if (!system.api) return;
    globalAcquisitionJobs.value = await system.api.listGlobalAcquisitionJobs({ scope: "library" });
  }

  async function refreshActiveReview(): Promise<void> {
    const system = useSystemStore();
    if (!system.api || !activeReview.value) return;
    activeReview.value = await system.api.getLibraryReview(activeReview.value.source.id);
  }

  async function openSource(source: LibrarySource): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoading(async () => {
      activeReview.value = await system.api!.getLibraryReview(source.id);
      selectedTrackIds.value = [];
      ui.navigateTo("library");
      ui.setMessage("success", `"${source.spotifyPlaylistName}" loaded.`);
    });
  }

  async function syncAllSources(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoading(async () => {
      const reviews = await system.api!.syncAllLibrarySources();
      sources.value = await system.api!.listLibrarySources();
      if (activeReview.value) {
        const updated = reviews.find((r) => r.source.id === activeReview.value!.source.id);
        if (updated) activeReview.value = updated;
      }
      ui.setMessage("success", `${reviews.length} source(s) synced.`);
      // Auto-download the open source's missing tracks (bounded to the active one).
      if (activeReview.value) await autoDownloadSource(activeReview.value.source.id);
    });
  }

  async function syncSource(source: LibrarySource): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoading(async () => {
      activeReview.value = await system.api!.syncLibrarySource(source.id);
      sources.value = await system.api!.listLibrarySources();
      selectedTrackIds.value = [];
      ui.setMessage("success", `"${source.spotifyPlaylistName}" synced.`);
      // Missing tracks are fetched automatically; only failures are surfaced.
      await autoDownloadSource(source.id);
    });
  }

  async function saveTagRule(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    const spotify = useSpotifyStore();
    if (!system.api) return;
    if (!tagRuleForm.sourcePlaylistId) {
      ui.setMessage("error", "Select a source playlist.");
      return;
    }
    await ui.withLoading(async () => {
      const playlist = spotify.playlists.find((p) => p.id === tagRuleForm.sourcePlaylistId);
      const source = await system.api!.saveLibrarySource({
        spotifyPlaylistId: tagRuleForm.sourcePlaylistId.trim(),
        spotifyPlaylistName: tagRuleForm.sourcePlaylistName.trim(),
        spotifySnapshotId: playlist?.snapshotId ?? null,
        imageUrl: playlist?.imageUrl ?? null,
        trackCount: playlist?.trackCount ?? 0,
        tags: tagRuleForm.tags,
        enabled: true,
      });
      tagRuleForm.sourcePlaylistId = "";
      tagRuleForm.sourcePlaylistName = "";
      tagRuleForm.tags = [];
      sources.value = await system.api!.listLibrarySources();
      activeReview.value = await system.api!.syncLibrarySource(source.id);
      selectedTrackIds.value = [];
      ui.setMessage("success", "Permanent playlist source saved and synced.");
      await autoDownloadSource(source.id);
    });
  }

  function toggleTrack(track: { spotifyTrackId: string }, selected: boolean): void {
    const current = new Set(selectedTrackIds.value);
    if (selected) current.add(track.spotifyTrackId);
    else current.delete(track.spotifyTrackId);
    selectedTrackIds.value = [...current];
  }

  function toggleAllTracks(tracks: { spotifyTrackId: string }[], selected: boolean): void {
    selectedTrackIds.value = selected ? tracks.map((t) => t.spotifyTrackId) : [];
  }

  async function updateSelectedTags(tags: string[]): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeReview.value || selectedTrackIds.value.length === 0) return;
    await ui.withLoading(async () => {
      activeReview.value = await system.api!.updateLibraryTracks({
        sourceId: activeReview.value!.source.id,
        spotifyTrackIds: selectedTrackIds.value,
        tags,
      });
      sources.value = await system.api!.listLibrarySources();
      ui.setMessage("success", "Selected track tags updated.");
    });
  }

  async function updateTrackTags(track: LibraryTrackReview, value: string): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeReview.value) return;
    const tags = value.split(",").map((t) => t.trim()).filter(Boolean);
    await ui.withLoading(async () => {
      activeReview.value = await system.api!.updateLibraryTracks({
        sourceId: activeReview.value!.source.id,
        spotifyTrackIds: [track.spotifyTrackId],
        tags,
      });
      sources.value = await system.api!.listLibrarySources();
      ui.setMessage("success", "Track tags updated.");
    });
  }

  // Tracks that genuinely failed to acquire: a failed job AND still unacquired.
  // A failed job left over on a track that is now matched/imported is ignored.
  function unresolvedFailures(result: LibraryDownloadResponse): string[] {
    const failedIds = new Set(
      result.jobs.filter((job) => job.status === "acquisition_failed").map((job) => job.spotifyTrackId)
    );
    return result.review.tracks
      .filter(
        (track) =>
          failedIds.has(track.spotifyTrackId) &&
          (track.status === "new" || track.status === "missing")
      )
      .map((track) => track.title);
  }

  // Auto-acquire missing tracks for a source. Downloads happen silently; the
  // only message shown is a warning listing tracks not found on Deemix.
  async function autoDownloadSource(sourceId: number): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    const result = await system.api.downloadLibraryTracks({ sourceId, spotifyTrackIds: null });
    activeReview.value = result.review;
    sources.value = await system.api.listLibrarySources();
    globalAcquisitionJobs.value = await system.api.listGlobalAcquisitionJobs();
    const failures = unresolvedFailures(result);
    if (failures.length > 0) {
      const shown = failures.slice(0, 6).join(", ") + (failures.length > 6 ? "…" : "");
      ui.setMessage("error", `${failures.length} titre(s) introuvable(s) sur Deemix : ${shown}`);
    }
  }

  async function applySource(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeReview.value) return;
    await ui.withLoading(async () => {
      const sourceId = activeReview.value!.source.id;
      const result = await system.api!.applyLibrarySource(sourceId);
      activeReview.value = await system.api!.getLibraryReview(sourceId);
      sources.value = await system.api!.listLibrarySources();
      globalAcquisitionJobs.value = await system.api!.listGlobalAcquisitionJobs();
      selectedTrackIds.value = [];
      ui.setMessage(
        result.warnings.length > 0 ? "error" : "success",
        `Library imported. Imported ${result.imported}, tagged ${result.tagged}.${result.warnings.length ? " " + result.warnings.join(" ") : ""}`
      );
    });
  }

  function selectTagRulePlaylist(playlistId: string): void {
    const spotify = useSpotifyStore();
    const playlist = spotify.playlists.find((p) => p.id === playlistId);
    tagRuleForm.sourcePlaylistId = playlist?.id ?? "";
    tagRuleForm.sourcePlaylistName = playlist?.name ?? "";
  }

  function addTagRuleTag(value = tagRuleTagInput.value): void {
    const tagName = value.trim();
    if (!tagName || tagRuleForm.tags.includes(tagName)) {
      tagRuleTagInput.value = "";
      return;
    }
    tagRuleForm.tags.push(tagName);
    tagRuleTagInput.value = "";
  }

  function removeTagRuleTag(tagName: string): void {
    tagRuleForm.tags = tagRuleForm.tags.filter((t) => t !== tagName);
  }

  function openDeezerSearch(track: TrackReview): void {
    deezerSearchTrack.value = track;
    deezerSearchQuery.value = [track.title, ...track.artists].join(" ");
    deezerSearchResults.value = [];
  }

  function closeDeezerSearch(): void {
    deezerSearchTrack.value = null;
    deezerSearchResults.value = [];
    deezerSearchQuery.value = "";
  }

  async function runDeezerSearch(): Promise<void> {
    const system = useSystemStore();
    if (!system.api || !deezerSearchQuery.value.trim()) return;
    deezerSearchLoading.value = true;
    try {
      deezerSearchResults.value = await system.api.searchDeezer(deezerSearchQuery.value.trim());
    } catch {
      deezerSearchResults.value = [];
    } finally {
      deezerSearchLoading.value = false;
    }
  }

  async function queueDeezerTrack(deezerTrackId: string): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeReview.value || !deezerSearchTrack.value) return;
    await ui.withLoading(async () => {
      await system.api!.queueDeezerTrack(
        activeReview.value!.source.id,
        deezerSearchTrack.value!.spotifyTrackId,
        deezerTrackId
      );
      activeReview.value = await system.api!.getLibraryReview(activeReview.value!.source.id);
      sources.value = await system.api!.listLibrarySources();
      ui.setMessage("success", "Track queued for download.");
      closeDeezerSearch();
    });
  }

  async function ignoreTrack(track: TrackReview): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeReview.value) return;
    await ui.withLoading(async () => {
      activeReview.value = await system.api!.updateLibraryTracks({
        sourceId: activeReview.value!.source.id,
        spotifyTrackIds: [track.spotifyTrackId],
        status: "ignored",
      });
      sources.value = await system.api!.listLibrarySources();
      ui.setMessage("success", "Track ignored.");
    });
  }

  async function unignoreTrack(track: TrackReview): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeReview.value) return;
    await ui.withLoading(async () => {
      activeReview.value = await system.api!.updateLibraryTracks({
        sourceId: activeReview.value!.source.id,
        spotifyTrackIds: [track.spotifyTrackId],
        status: "new",
      });
      sources.value = await system.api!.listLibrarySources();
      ui.setMessage("success", "Track restored.");
    });
  }

  return {
    sources,
    activeReview,
    selectedTrackIds,
    tagRules,
    globalAcquisitionJobs,
    tagRuleTagInput,
    tagRuleForm,
    selectedTracks,
    readyToApply,
    deezerSearchTrack,
    deezerSearchQuery,
    deezerSearchResults,
    deezerSearchLoading,
    refreshSources,
    syncAllSources,
    refreshTagRules,
    refreshGlobalJobs,
    refreshActiveReview,
    openSource,
    syncSource,
    saveTagRule,
    toggleTrack,
    toggleAllTracks,
    updateSelectedTags,
    updateTrackTags,
    applySource,
    selectTagRulePlaylist,
    addTagRuleTag,
    removeTagRuleTag,
    openDeezerSearch,
    closeDeezerSearch,
    runDeezerSearch,
    queueDeezerTrack,
    ignoreTrack,
    unignoreTrack,
  };
});
