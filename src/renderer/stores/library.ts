import { defineStore } from "pinia";
import { computed, reactive, ref } from "vue";
import type {
  GlobalAcquisitionJob,
  LibraryReview,
  LibrarySource,
  LibraryTrackReview,
  TagPlaylistMapping,
  TagRule,
} from "../lib/api";
import type { MappingFormState, TagRuleFormState } from "../types/ui";
import { useSystemStore } from "./system";
import { useUiStore } from "./ui";
import { useSpotifyStore } from "./spotify";
import { useProposalsStore } from "./proposals";

export const useLibraryStore = defineStore("library", () => {
  const sources = ref<LibrarySource[]>([]);
  const activeReview = ref<LibraryReview | null>(null);
  const selectedTrackIds = ref<string[]>([]);
  const tagRules = ref<TagRule[]>([]);
  const tagPlaylistMappings = ref<TagPlaylistMapping[]>([]);
  const globalAcquisitionJobs = ref<GlobalAcquisitionJob[]>([]);
  const tagRuleTagInput = ref("");

  const tagRuleForm = reactive<TagRuleFormState>({
    sourcePlaylistId: "",
    sourcePlaylistName: "",
    tags: [],
  });

  const mappingForm = reactive<MappingFormState>({
    tagName: "",
    spotifyPlaylistId: "",
    spotifyPlaylistName: "",
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

  async function refreshMappings(): Promise<void> {
    const system = useSystemStore();
    if (!system.api) return;
    tagPlaylistMappings.value = await system.api.listTagPlaylistMappings();
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

  async function syncSource(source: LibrarySource): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    const proposals = useProposalsStore();
    if (!system.api) return;
    await ui.withLoading(async () => {
      activeReview.value = await system.api!.syncLibrarySource(source.id);
      sources.value = await system.api!.listLibrarySources();
      await proposals.refresh();
      selectedTrackIds.value = [];
      ui.setMessage("success", `"${source.spotifyPlaylistName}" synced.`);
    });
  }

  async function saveTagRule(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    const spotify = useSpotifyStore();
    if (!system.api) return;
    if (!tagRuleForm.sourcePlaylistId || tagRuleForm.tags.length === 0) {
      ui.setMessage("error", "Select a source playlist and at least one tag.");
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
    });
  }

  async function saveTagPlaylistMapping(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    if (!mappingForm.tagName.trim() || !mappingForm.spotifyPlaylistId.trim()) {
      ui.setMessage("error", "Select a MyTag and a Spotify playlist.");
      return;
    }
    await ui.withLoading(async () => {
      await system.api!.saveTagPlaylistMapping({
        tagName: mappingForm.tagName.trim(),
        spotifyPlaylistId: mappingForm.spotifyPlaylistId.trim(),
        spotifyPlaylistName: mappingForm.spotifyPlaylistName.trim(),
        enabled: true,
      });
      mappingForm.tagName = "";
      mappingForm.spotifyPlaylistId = "";
      mappingForm.spotifyPlaylistName = "";
      tagPlaylistMappings.value = await system.api!.listTagPlaylistMappings();
      ui.setMessage("success", "Tag to Spotify playlist mapping saved.");
    });
  }

  function toggleTrack(track: LibraryTrackReview, selected: boolean): void {
    const current = new Set(selectedTrackIds.value);
    if (selected) current.add(track.spotifyTrackId);
    else current.delete(track.spotifyTrackId);
    selectedTrackIds.value = [...current];
  }

  function toggleAllTracks(tracks: LibraryTrackReview[], selected: boolean): void {
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

  async function downloadSelected(): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api || !activeReview.value) return;
    await ui.withLoading(async () => {
      const result = await system.api!.downloadLibraryTracks({
        sourceId: activeReview.value!.source.id,
        spotifyTrackIds: selectedTrackIds.value.length > 0 ? selectedTrackIds.value : null,
      });
      activeReview.value = result.review;
      sources.value = await system.api!.listLibrarySources();
      globalAcquisitionJobs.value = await system.api!.listGlobalAcquisitionJobs();
      const action = result.created === 0 && result.ready > 0 ? "Download state refreshed" : "Download started";
      ui.setMessage("success", `${action}. Queued ${result.queued}, ready ${result.ready}, failed ${result.failed}, ambiguous ${result.ambiguous}.`);
    });
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
        `Library imported. Imported ${result.imported}, tagged ${result.tagged}, Spotify additions ${result.spotifyAdded}. ${result.warnings.join(" ")}`
      );
    });
  }

  function selectTagRulePlaylist(playlistId: string): void {
    const spotify = useSpotifyStore();
    const playlist = spotify.playlists.find((p) => p.id === playlistId);
    tagRuleForm.sourcePlaylistId = playlist?.id ?? "";
    tagRuleForm.sourcePlaylistName = playlist?.name ?? "";
  }

  function selectMappingPlaylist(playlistId: string): void {
    const spotify = useSpotifyStore();
    const playlist = spotify.playlists.find((p) => p.id === playlistId);
    mappingForm.spotifyPlaylistId = playlist?.id ?? "";
    mappingForm.spotifyPlaylistName = playlist?.name ?? "";
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

  return {
    sources,
    activeReview,
    selectedTrackIds,
    tagRules,
    tagPlaylistMappings,
    globalAcquisitionJobs,
    tagRuleTagInput,
    tagRuleForm,
    mappingForm,
    selectedTracks,
    readyToApply,
    refreshSources,
    refreshTagRules,
    refreshMappings,
    refreshGlobalJobs,
    refreshActiveReview,
    openSource,
    syncSource,
    saveTagRule,
    saveTagPlaylistMapping,
    toggleTrack,
    toggleAllTracks,
    updateSelectedTags,
    updateTrackTags,
    downloadSelected,
    applySource,
    selectTagRulePlaylist,
    selectMappingPlaylist,
    addTagRuleTag,
    removeTagRuleTag,
  };
});
