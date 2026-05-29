<script setup lang="ts">
import { AlertTriangle, CheckCircle2 } from "@lucide/vue";
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import AppShell from "./components/AppShell.vue";
import DashboardView from "./views/DashboardView.vue";
import DownloadMatchCenterView from "./views/DownloadMatchCenterView.vue";
import EventImportsView from "./views/EventImportsView.vue";
import LibraryView from "./views/LibraryView.vue";
import SettingsView from "./views/SettingsView.vue";
import {
  type AcquisitionJob,
  type ApiClient,
  type AppSettings,
  type DeemixStatus,
  type EventReview,
  type EventSummary,
  type EventTrackReview,
  type GlobalAcquisitionJob,
  type HealthResponse,
  type LibraryReview,
  type LibrarySource,
  type LibraryTrackReview,
  type LiveImportPackage,
  type RekordboxStatus,
  type RekordboxTag,
  type SpotifyPlaylistSummary,
  type SpotifyPlaylistsResponse,
  type StorageLayout,
  type SyncProposal,
  type TagPlaylistMapping,
  type TagRule,
  createApiClient
} from "./lib/api";
import type { MappingFormState, TagRuleFormState, ViewKey } from "./types/ui";

const api = ref<ApiClient | null>(null);
const activeView = ref<ViewKey>("dashboard");
const loading = ref(false);
const errorMessage = ref("");
const successMessage = ref("");
const searchQuery = ref("");
const health = ref<HealthResponse | null>(null);
const rekordboxStatus = ref<RekordboxStatus | null>(null);
const storage = ref<StorageLayout | null>(null);
const tagRules = ref<TagRule[]>([]);
const librarySources = ref<LibrarySource[]>([]);
const activeLibraryReview = ref<LibraryReview | null>(null);
const selectedLibraryTrackIds = ref<string[]>([]);
const tagPlaylistMappings = ref<TagPlaylistMapping[]>([]);
const proposals = ref<SyncProposal[]>([]);
const eventSummaries = ref<EventSummary[]>([]);
const activeEvent = ref<EventReview | null>(null);
const acquisitionJobs = ref<AcquisitionJob[]>([]);
const globalAcquisitionJobs = ref<GlobalAcquisitionJob[]>([]);
const deemixStatus = ref<DeemixStatus | null>(null);
const reviewFilter = ref("all");
const rekordboxTags = ref<RekordboxTag[]>([]);
const spotifyPlaylists = ref<SpotifyPlaylistSummary[]>([]);
const spotifyPlaylistPage = ref<SpotifyPlaylistsResponse | null>(null);
const spotifyPlaylistTotal = ref(0);
const liveImportPackage = ref<LiveImportPackage | null>(null);
const tagRuleTagInput = ref("");
const realtimeRefreshInFlight = ref(false);
const slowRefreshInFlight = ref(false);
const playlistRefreshInFlight = ref(false);
const reviewRefreshInFlight = ref(false);
const stagingScanInFlight = ref(false);

let realtimeRefreshTimer: number | undefined;
let slowRefreshTimer: number | undefined;
let playlistRefreshTimer: number | undefined;
let reviewRefreshTimer: number | undefined;
let stagingScanTimer: number | undefined;

const settings = reactive<AppSettings>({
  spotifyClientId: "",
  spotifyRedirectUri: "http://127.0.0.1:8765/api/spotify/callback",
  rekordboxDatabaseDir: "/Users/adriendidot/Library/Pioneer/rekordbox",
  storageRoot:
    "/Users/adriendidot/Library/CloudStorage/Dropbox-CloudOptionDJteam/Jockey Tricolore/Musique",
  apiPort: 8765
});

const importForm = reactive({
  playlistUrl: "",
  eventName: ""
});

const tagRuleForm = reactive<TagRuleFormState>({
  sourcePlaylistId: "",
  sourcePlaylistName: "",
  tags: []
});

const mappingForm = reactive<MappingFormState>({
  tagName: "",
  spotifyPlaylistId: "",
  spotifyPlaylistName: ""
});

const pageTitle = computed(() => {
  if (activeView.value === "dashboard") return "Dashboard";
  if (activeView.value === "library") return "My Library";
  if (activeView.value === "events") return "Event Imports";
  if (activeView.value === "downloadCenter") return "Download & Match Center";
  return "Settings";
});

const availableTagNames = computed(() =>
  rekordboxTags.value
    .map((tagItem) => tagItem.name)
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right))
);

const filteredEventTracks = computed(() => {
  if (!activeEvent.value) return [];
  if (reviewFilter.value === "all") return activeEvent.value.tracks;
  return activeEvent.value.tracks.filter((track) => track.status === reviewFilter.value);
});

const readyToApply = computed(() => {
  if (!activeEvent.value) return false;
  return activeEvent.value.matchedTracks + activeEvent.value.readyTracks > 0;
});

const selectedLibraryTracks = computed(() => {
  if (!activeLibraryReview.value) return [];
  const selected = new Set(selectedLibraryTrackIds.value);
  return activeLibraryReview.value.tracks.filter((track) =>
    selected.has(track.spotifyTrackId)
  );
});

const libraryReadyToApply = computed(() => {
  if (!activeLibraryReview.value) return false;
  return activeLibraryReview.value.matchedTracks + activeLibraryReview.value.readyTracks > 0;
});

const acquisitionCounts = computed(() => {
  const counts = {
    queued: 0,
    downloading: 0,
    downloaded: 0,
    ready: 0,
    failed: 0,
    ambiguous: 0
  };
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

function setMessage(kind: "success" | "error", message: string): void {
  successMessage.value = kind === "success" ? message : "";
  errorMessage.value = kind === "error" ? message : "";
}

async function withLoading(task: () => Promise<void>): Promise<void> {
  loading.value = true;
  errorMessage.value = "";
  successMessage.value = "";
  try {
    await task();
  } catch (error) {
    setMessage("error", error instanceof Error ? error.message : String(error));
  } finally {
    loading.value = false;
  }
}

async function runBackgroundTask(task: () => Promise<void>): Promise<void> {
  try {
    await task();
  } catch (error) {
    if (!document.hidden) {
      console.warn(error);
    }
  }
}

async function refreshAll(): Promise<void> {
  if (!api.value) return;
  await withLoading(async () => {
    const [
      nextHealth,
      nextStatus,
      nextDeemixStatus,
      nextSettings,
      nextRules,
      nextLibrarySources,
      nextProposals,
      nextEvents,
      nextMappings,
      nextRekordboxTags,
      nextGlobalAcquisitionJobs,
      nextSpotifyPlaylists
    ] = await Promise.all([
      api.value!.getHealth(),
      api.value!.getRekordboxStatus(),
      api.value!.getDeemixStatus().catch(() => deemixStatus.value),
      api.value!.getSettings(),
      api.value!.listTagRules(),
      api.value!.listLibrarySources(),
      api.value!.listProposals(),
      api.value!.listEvents(),
      api.value!.listTagPlaylistMappings(),
      api.value!.listRekordboxTags().catch(() => rekordboxTags.value),
      api.value!.listGlobalAcquisitionJobs(),
      fetchAllSpotifyPlaylists().catch(() => ({
        items: spotifyPlaylists.value,
        total: spotifyPlaylistTotal.value
      }))
    ]);
    health.value = nextHealth;
    rekordboxStatus.value = nextStatus;
    deemixStatus.value = nextDeemixStatus;
    Object.assign(settings, nextSettings);
    tagRules.value = nextRules;
    librarySources.value = nextLibrarySources;
    proposals.value = nextProposals;
    eventSummaries.value = nextEvents;
    tagPlaylistMappings.value = nextMappings;
    rekordboxTags.value = nextRekordboxTags;
    globalAcquisitionJobs.value = nextGlobalAcquisitionJobs;
    spotifyPlaylists.value = nextSpotifyPlaylists.items;
    spotifyPlaylistTotal.value = nextSpotifyPlaylists.total;
    spotifyPlaylistPage.value = {
      items: nextSpotifyPlaylists.items,
      total: nextSpotifyPlaylists.total,
      limit: nextSpotifyPlaylists.items.length,
      offset: 0,
      nextOffset: null
    };
  });
}

async function refreshRealtimeState(): Promise<void> {
  if (!api.value || realtimeRefreshInFlight.value || document.hidden) return;
  realtimeRefreshInFlight.value = true;
  await runBackgroundTask(async () => {
    const [nextHealth, nextStatus, nextDeemixStatus] = await Promise.all([
      api.value!.getHealth(),
      api.value!.getRekordboxStatus(),
      api.value!.getDeemixStatus().catch(() => deemixStatus.value)
    ]);
    health.value = nextHealth;
    rekordboxStatus.value = nextStatus;
    deemixStatus.value = nextDeemixStatus;
    if (activeView.value === "library" && activeLibraryReview.value) {
      activeLibraryReview.value = await api.value!.getLibraryReview(
        activeLibraryReview.value.source.id
      );
      librarySources.value = await api.value!.listLibrarySources();
      globalAcquisitionJobs.value = await api.value!.listGlobalAcquisitionJobs({
        scope: "library"
      });
    }
    if (activeView.value === "events" || activeView.value === "downloadCenter") {
      eventSummaries.value = await api.value!.listEvents();
      globalAcquisitionJobs.value = await api.value!.listGlobalAcquisitionJobs();
    }
  });
  realtimeRefreshInFlight.value = false;
}

async function refreshSlowState(): Promise<void> {
  if (!api.value || slowRefreshInFlight.value || document.hidden) return;
  slowRefreshInFlight.value = true;
  await runBackgroundTask(async () => {
    const [
      nextRules,
      nextLibrarySources,
      nextProposals,
      nextEvents,
      nextMappings,
      nextTags,
      nextGlobalJobs
    ] =
      await Promise.all([
        api.value!.listTagRules(),
        api.value!.listLibrarySources(),
        api.value!.listProposals(),
        api.value!.listEvents(),
        api.value!.listTagPlaylistMappings(),
        api.value!.listRekordboxTags().catch(() => rekordboxTags.value),
        api.value!.listGlobalAcquisitionJobs()
      ]);
    tagRules.value = nextRules;
    librarySources.value = nextLibrarySources;
    proposals.value = nextProposals;
    eventSummaries.value = nextEvents;
    tagPlaylistMappings.value = nextMappings;
    rekordboxTags.value = nextTags;
    globalAcquisitionJobs.value = nextGlobalJobs;
  });
  slowRefreshInFlight.value = false;
}

async function refreshVisibleSpotifyPlaylists(): Promise<void> {
  if (
    !api.value ||
    playlistRefreshInFlight.value ||
    document.hidden ||
    !["library", "events"].includes(activeView.value)
  ) {
    return;
  }
  playlistRefreshInFlight.value = true;
  await runBackgroundTask(async () => {
    const page = await fetchAllSpotifyPlaylists();
    applySpotifyPlaylists(page);
  });
  playlistRefreshInFlight.value = false;
}

async function refreshVisibleRekordboxTags(): Promise<void> {
  if (!api.value || document.hidden || !["library", "events"].includes(activeView.value)) {
    return;
  }
  await runBackgroundTask(async () => {
    rekordboxTags.value = await api.value!.listRekordboxTags();
  });
}

async function refreshActiveEventState(): Promise<void> {
  if (!api.value || !activeEvent.value || reviewRefreshInFlight.value || document.hidden) {
    return;
  }
  reviewRefreshInFlight.value = true;
  await runBackgroundTask(async () => {
    const eventId = activeEvent.value!.id;
    acquisitionJobs.value = await api.value!.listAcquisitionJobs(eventId);
    activeEvent.value = await api.value!.getEventReview(eventId);
    eventSummaries.value = await api.value!.listEvents();
    globalAcquisitionJobs.value = await api.value!.listGlobalAcquisitionJobs();
  });
  reviewRefreshInFlight.value = false;
}

async function scanActiveEventStaging(): Promise<void> {
  if (
    !api.value ||
    !activeEvent.value ||
    !["events", "downloadCenter"].includes(activeView.value) ||
    stagingScanInFlight.value ||
    document.hidden
  ) {
    return;
  }
  stagingScanInFlight.value = true;
  await runBackgroundTask(async () => {
    const eventId = activeEvent.value!.id;
    activeEvent.value = await api.value!.scanEventStaging(eventId);
    acquisitionJobs.value = await api.value!.listAcquisitionJobs(eventId);
    eventSummaries.value = await api.value!.listEvents();
    globalAcquisitionJobs.value = await api.value!.listGlobalAcquisitionJobs();
  });
  stagingScanInFlight.value = false;
}

function applySpotifyPlaylists(page: {
  items: SpotifyPlaylistSummary[];
  total: number;
}): void {
  spotifyPlaylists.value = page.items;
  spotifyPlaylistTotal.value = page.total;
  spotifyPlaylistPage.value = {
    items: page.items,
    total: page.total,
    limit: page.items.length,
    offset: 0,
    nextOffset: null
  };
}

function startAutoRefresh(): void {
  window.rekordboxSyncStudioStopAutoRefresh?.();
  stopAutoRefresh();
  realtimeRefreshTimer = window.setInterval(() => void refreshRealtimeState(), 5000);
  slowRefreshTimer = window.setInterval(() => void refreshSlowState(), 30000);
  playlistRefreshTimer = window.setInterval(
    () => void refreshVisibleSpotifyPlaylists(),
    60000
  );
  reviewRefreshTimer = window.setInterval(() => void refreshActiveEventState(), 5000);
  stagingScanTimer = window.setInterval(() => void scanActiveEventStaging(), 15000);
  document.addEventListener("visibilitychange", handleVisibilityChange);
  window.rekordboxSyncStudioStopAutoRefresh = stopAutoRefresh;
}

function stopAutoRefresh(): void {
  for (const timer of [
    realtimeRefreshTimer,
    slowRefreshTimer,
    playlistRefreshTimer,
    reviewRefreshTimer,
    stagingScanTimer
  ]) {
    if (timer !== undefined) window.clearInterval(timer);
  }
  realtimeRefreshTimer = undefined;
  slowRefreshTimer = undefined;
  playlistRefreshTimer = undefined;
  reviewRefreshTimer = undefined;
  stagingScanTimer = undefined;
  document.removeEventListener("visibilitychange", handleVisibilityChange);
  if (window.rekordboxSyncStudioStopAutoRefresh === stopAutoRefresh) {
    window.rekordboxSyncStudioStopAutoRefresh = undefined;
  }
}

function handleVisibilityChange(): void {
  if (document.hidden) return;
  void refreshRealtimeState();
  void refreshSlowState();
  void refreshVisibleSpotifyPlaylists();
  void refreshVisibleRekordboxTags();
  void refreshActiveEventState();
  void scanActiveEventStaging();
}

async function saveSettings(): Promise<void> {
  if (!api.value) return;
  await withLoading(async () => {
    Object.assign(settings, await api.value!.saveSettings(settings));
    setMessage("success", "Settings saved.");
  });
}

async function ensureStorage(): Promise<void> {
  if (!api.value) return;
  await withLoading(async () => {
    storage.value = await api.value!.ensureStorage();
    setMessage("success", "Storage folders are ready.");
  });
}

async function openSpotifyAuth(): Promise<void> {
  if (!api.value) return;
  await withLoading(async () => {
    const response = await api.value!.getSpotifyAuthUrl(
      settings.spotifyClientId,
      settings.spotifyRedirectUri
    );
    if (window.desktop) {
      await window.desktop.openExternal(response.authorizationUrl);
    } else {
      window.open(response.authorizationUrl, "_blank", "noopener,noreferrer");
    }
    setMessage("success", "Spotify authorization opened in the browser.");
  });
}

async function fetchAllSpotifyPlaylists(): Promise<{
  items: SpotifyPlaylistSummary[];
  total: number;
}> {
  if (!api.value) return { items: [], total: 0 };
  const items: SpotifyPlaylistSummary[] = [];
  let offset = 0;
  let total = 0;
  while (true) {
    const page = await api.value.listSpotifyPlaylists(offset);
    items.push(...page.items);
    total = page.total;
    if (page.nextOffset == null || page.items.length === 0) {
      break;
    }
    offset = page.nextOffset;
  }
  return { items, total };
}

function selectSpotifyPlaylist(playlist: SpotifyPlaylistSummary): void {
  importForm.playlistUrl = playlist.url;
  if (!importForm.eventName.trim()) {
    importForm.eventName = playlist.name;
  }
  liveImportPackage.value = null;
  activeView.value = "events";
  setMessage("success", `"${playlist.name}" selected.`);
}

function selectTagRulePlaylist(playlistId: string): void {
  const playlist = spotifyPlaylists.value.find((item) => item.id === playlistId);
  tagRuleForm.sourcePlaylistId = playlist?.id ?? "";
  tagRuleForm.sourcePlaylistName = playlist?.name ?? "";
}

function selectMappingPlaylist(playlistId: string): void {
  const playlist = spotifyPlaylists.value.find((item) => item.id === playlistId);
  mappingForm.spotifyPlaylistId = playlist?.id ?? "";
  mappingForm.spotifyPlaylistName = playlist?.name ?? "";
}

function updateTagRuleTagInput(value: string): void {
  tagRuleTagInput.value = value;
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
  tagRuleForm.tags = tagRuleForm.tags.filter((item) => item !== tagName);
}

async function analyzeImport(): Promise<void> {
  if (!api.value) return;
  await withLoading(async () => {
    activeEvent.value = await api.value!.analyzeSpotifyEvent(importForm);
    acquisitionJobs.value = await api.value!.listAcquisitionJobs(activeEvent.value.id);
    eventSummaries.value = await api.value!.listEvents();
    activeView.value = "events";
    setMessage("success", `${activeEvent.value.totalTracks} Spotify tracks analyzed.`);
  });
}

async function createLiveImportPackage(): Promise<void> {
  if (!api.value) return;
  const eventName = importForm.eventName.trim();
  if (!eventName) {
    setMessage("error", "Event name is required for live import.");
    return;
  }
  await withLoading(async () => {
    const nextPackage = await api.value!.createLiveImport({ eventName });
    liveImportPackage.value = nextPackage;
    setMessage("success", `Live import ready with ${nextPackage.trackCount} audio file(s).`);
  });
}

async function openDesktopPath(path: string): Promise<void> {
  if (!window.desktop) {
    setMessage("success", `Open this path in Finder: ${path}`);
    return;
  }
  try {
    await window.desktop.openPath(path);
  } catch (error) {
    setMessage("error", error instanceof Error ? error.message : String(error));
  }
}

async function saveTagRule(): Promise<void> {
  if (!api.value) return;
  if (!tagRuleForm.sourcePlaylistId || tagRuleForm.tags.length === 0) {
    setMessage("error", "Select a source playlist and at least one tag.");
    return;
  }
  await withLoading(async () => {
    const playlist = spotifyPlaylists.value.find(
      (item) => item.id === tagRuleForm.sourcePlaylistId
    );
    const source = await api.value!.saveLibrarySource({
      spotifyPlaylistId: tagRuleForm.sourcePlaylistId.trim(),
      spotifyPlaylistName: tagRuleForm.sourcePlaylistName.trim(),
      spotifySnapshotId: playlist?.snapshotId ?? null,
      imageUrl: playlist?.imageUrl ?? null,
      trackCount: playlist?.trackCount ?? 0,
      tags: tagRuleForm.tags,
      enabled: true
    });
    tagRuleForm.sourcePlaylistId = "";
    tagRuleForm.sourcePlaylistName = "";
    tagRuleForm.tags = [];
    librarySources.value = await api.value!.listLibrarySources();
    activeLibraryReview.value = await api.value!.syncLibrarySource(source.id);
    selectedLibraryTrackIds.value = [];
    setMessage("success", "Permanent playlist source saved and synced.");
  });
}

async function openLibrarySource(source: LibrarySource): Promise<void> {
  if (!api.value) return;
  await withLoading(async () => {
    activeLibraryReview.value = await api.value!.getLibraryReview(source.id);
    selectedLibraryTrackIds.value = [];
    activeView.value = "library";
    setMessage("success", `"${source.spotifyPlaylistName}" loaded.`);
  });
}

async function syncLibrarySource(source: LibrarySource): Promise<void> {
  if (!api.value) return;
  await withLoading(async () => {
    activeLibraryReview.value = await api.value!.syncLibrarySource(source.id);
    librarySources.value = await api.value!.listLibrarySources();
    proposals.value = await api.value!.listProposals();
    selectedLibraryTrackIds.value = [];
    setMessage("success", `"${source.spotifyPlaylistName}" synced.`);
  });
}

function toggleLibraryTrack(track: LibraryTrackReview, selected: boolean): void {
  const current = new Set(selectedLibraryTrackIds.value);
  if (selected) {
    current.add(track.spotifyTrackId);
  } else {
    current.delete(track.spotifyTrackId);
  }
  selectedLibraryTrackIds.value = [...current];
}

function toggleAllLibraryTracks(tracks: LibraryTrackReview[], selected: boolean): void {
  if (!selected) {
    selectedLibraryTrackIds.value = [];
    return;
  }
  selectedLibraryTrackIds.value = tracks.map((track) => track.spotifyTrackId);
}

async function updateSelectedLibraryTags(tags: string[]): Promise<void> {
  if (!api.value || !activeLibraryReview.value || selectedLibraryTrackIds.value.length === 0) {
    return;
  }
  await withLoading(async () => {
    activeLibraryReview.value = await api.value!.updateLibraryTracks({
      sourceId: activeLibraryReview.value!.source.id,
      spotifyTrackIds: selectedLibraryTrackIds.value,
      tags
    });
    librarySources.value = await api.value!.listLibrarySources();
    setMessage("success", "Selected track tags updated.");
  });
}

async function updateLibraryTrackTags(track: LibraryTrackReview, value: string): Promise<void> {
  if (!api.value || !activeLibraryReview.value) return;
  const tags = value
    .split(",")
    .map((tagName) => tagName.trim())
    .filter(Boolean);
  await withLoading(async () => {
    activeLibraryReview.value = await api.value!.updateLibraryTracks({
      sourceId: activeLibraryReview.value!.source.id,
      spotifyTrackIds: [track.spotifyTrackId],
      tags
    });
    librarySources.value = await api.value!.listLibrarySources();
    setMessage("success", "Track tags updated.");
  });
}

async function downloadSelectedLibraryTracks(): Promise<void> {
  if (!api.value || !activeLibraryReview.value) return;
  await withLoading(async () => {
    const result = await api.value!.downloadLibraryTracks({
      sourceId: activeLibraryReview.value!.source.id,
      spotifyTrackIds:
        selectedLibraryTrackIds.value.length > 0 ? selectedLibraryTrackIds.value : null
    });
    activeLibraryReview.value = result.review;
    librarySources.value = await api.value!.listLibrarySources();
    globalAcquisitionJobs.value = await api.value!.listGlobalAcquisitionJobs();
    const action =
      result.created === 0 && result.ready > 0
        ? "Download state refreshed"
        : "Download started";
    setMessage(
      "success",
      `${action}. Queued ${result.queued}, ready ${result.ready}, failed ${result.failed}, ambiguous ${result.ambiguous}.`
    );
  });
}

async function applyActiveLibrarySource(): Promise<void> {
  if (!api.value || !activeLibraryReview.value) return;
  await withLoading(async () => {
    const sourceId = activeLibraryReview.value!.source.id;
    const result = await api.value!.applyLibrarySource(sourceId);
    activeLibraryReview.value = await api.value!.getLibraryReview(sourceId);
    librarySources.value = await api.value!.listLibrarySources();
    globalAcquisitionJobs.value = await api.value!.listGlobalAcquisitionJobs();
    selectedLibraryTrackIds.value = [];
    setMessage(
      result.warnings.length > 0 ? "error" : "success",
      `Library imported. Imported ${result.imported}, tagged ${result.tagged}, Spotify additions ${result.spotifyAdded}. ${result.warnings.join(" ")}`
    );
  });
}

async function saveTagPlaylistMapping(): Promise<void> {
  if (!api.value) return;
  if (!mappingForm.tagName.trim() || !mappingForm.spotifyPlaylistId.trim()) {
    setMessage("error", "Select a MyTag and a Spotify playlist.");
    return;
  }
  await withLoading(async () => {
    await api.value!.saveTagPlaylistMapping({
      tagName: mappingForm.tagName.trim(),
      spotifyPlaylistId: mappingForm.spotifyPlaylistId.trim(),
      spotifyPlaylistName: mappingForm.spotifyPlaylistName.trim(),
      enabled: true
    });
    mappingForm.tagName = "";
    mappingForm.spotifyPlaylistId = "";
    mappingForm.spotifyPlaylistName = "";
    tagPlaylistMappings.value = await api.value!.listTagPlaylistMappings();
    setMessage("success", "Tag to Spotify playlist mapping saved.");
  });
}

async function openEvent(summary: EventSummary): Promise<void> {
  if (!api.value) return;
  await withLoading(async () => {
    activeEvent.value = await api.value!.getEventReview(summary.id);
    acquisitionJobs.value = await api.value!.listAcquisitionJobs(summary.id);
    setMessage("success", `"${activeEvent.value.eventName}" loaded.`);
  });
}

async function refreshEventFolder(): Promise<void> {
  if (!api.value || !activeEvent.value) return;
  await withLoading(async () => {
    const eventId = activeEvent.value!.id;
    activeEvent.value = await api.value!.scanEventStaging(eventId);
    acquisitionJobs.value = await api.value!.listAcquisitionJobs(eventId);
    eventSummaries.value = await api.value!.listEvents();
    setMessage(
      "success",
      `Folder refreshed. ${activeEvent.value.stagingFiles.length} staged file(s) found.`
    );
  });
}

async function downloadMissingTracks(): Promise<void> {
  if (!api.value || !activeEvent.value) return;
  await withLoading(async () => {
    const result = await api.value!.runAutoAcquisition(activeEvent.value!.id);
    activeEvent.value = result.review;
    acquisitionJobs.value = result.jobs;
    eventSummaries.value = await api.value!.listEvents();
    globalAcquisitionJobs.value = await api.value!.listGlobalAcquisitionJobs();
    setMessage(
      "success",
      `Download started. Queued ${result.queued}, failed ${result.failed}, ambiguous ${result.ambiguous}.`
    );
  });
}

async function updatePermanent(track: EventTrackReview, permanent: boolean): Promise<void> {
  if (!api.value || !activeEvent.value) return;
  await withLoading(async () => {
    activeEvent.value = await api.value!.updateEventTrack(activeEvent.value!.id, {
      spotifyTrackId: track.spotifyTrackId,
      permanent
    });
  });
}

async function updateTrackTags(track: EventTrackReview, value: string): Promise<void> {
  if (!api.value || !activeEvent.value) return;
  const tags = value
    .split(",")
    .map((tagName) => tagName.trim())
    .filter(Boolean);
  await withLoading(async () => {
    activeEvent.value = await api.value!.updateEventTrack(activeEvent.value!.id, {
      spotifyTrackId: track.spotifyTrackId,
      tags
    });
    setMessage("success", "Track tags updated.");
  });
}

async function assignStagingFile(track: EventTrackReview, value: string): Promise<void> {
  if (!api.value || !activeEvent.value || !value) return;
  await withLoading(async () => {
    activeEvent.value = await api.value!.updateEventTrack(activeEvent.value!.id, {
      spotifyTrackId: track.spotifyTrackId,
      stagingFilePath: value,
      status: "ready"
    });
    setMessage("success", "Staged file assigned.");
  });
}

async function acceptSuggestedMatch(track: EventTrackReview): Promise<void> {
  if (!api.value || !activeEvent.value || !track.rekordboxContentId) return;
  await withLoading(async () => {
    activeEvent.value = await api.value!.updateEventTrack(activeEvent.value!.id, {
      spotifyTrackId: track.spotifyTrackId,
      rekordboxContentId: track.rekordboxContentId,
      status: "matched"
    });
    setMessage("success", "Suggested Rekordbox match accepted.");
  });
}

async function applyActiveEvent(): Promise<void> {
  if (!api.value || !activeEvent.value) return;
  await withLoading(async () => {
    const result = await api.value!.applyEvent(activeEvent.value!.id);
    activeEvent.value = await api.value!.getEventReview(activeEvent.value!.id);
    acquisitionJobs.value = await api.value!.listAcquisitionJobs(activeEvent.value.id);
    eventSummaries.value = await api.value!.listEvents();
    setMessage(
      result.warnings.length > 0 ? "error" : "success",
      `Event applied. Imported ${result.imported}, tagged ${result.tagged}, Spotify additions ${result.spotifyAdded}. ${result.warnings.join(" ")}`
    );
  });
}

async function deleteActiveEvent(): Promise<void> {
  if (!api.value || !activeEvent.value) return;
  await withLoading(async () => {
    const eventId = activeEvent.value!.id;
    const preview = await api.value!.previewEventDelete(eventId);
    const details = preview.localOnly
      ? "This event matches a permanent playlist source. Only the temporary event entry will be removed from the app."
      : `This will remove ${preview.willRemoveEventTag} event tag link(s) and remove ${preview.willDeleteFromRekordbox} track(s) from the Rekordbox collection. ${preview.protectedTracks} track(s) will be kept because they have other tags or are stored as permanent/manual tracks.`;
    const confirmed = window.confirm(
      `Delete temporary event "${preview.eventName}"?\n\n${details}\n\nAudio files on disk will not be deleted.`
    );
    if (!confirmed) return;

    const result = await api.value!.deleteEvent(eventId);
    activeEvent.value = null;
    acquisitionJobs.value = [];
    eventSummaries.value = await api.value!.listEvents();
    globalAcquisitionJobs.value = await api.value!.listGlobalAcquisitionJobs();
    setMessage(
      "success",
      `Event deleted. Rekordbox tracks removed ${result.deletedFromRekordbox}, event tags removed ${result.removedEventTags}, protected ${result.protectedTracks}.`
    );
  });
}

async function resolveProposal(proposalId: number, status: string): Promise<void> {
  if (!api.value) return;
  await withLoading(async () => {
    await api.value!.resolveProposal(proposalId, status);
    proposals.value = await api.value!.listProposals();
    setMessage("success", "Sync proposal updated.");
  });
}

watch(activeView, (view) => {
  if (view === "library" || view === "events") {
    void refreshVisibleSpotifyPlaylists();
    void refreshVisibleRekordboxTags();
  }
  if (view === "library" && api.value) {
    void runBackgroundTask(async () => {
      librarySources.value = await api.value!.listLibrarySources();
      if (activeLibraryReview.value) {
        activeLibraryReview.value = await api.value!.getLibraryReview(
          activeLibraryReview.value.source.id
        );
      }
    });
  }
  if (view === "events" || view === "downloadCenter") {
    void refreshActiveEventState();
    void scanActiveEventStaging();
  }
});

watch(
  () => activeEvent.value?.id,
  (eventId) => {
    if (eventId) {
      void refreshActiveEventState();
    }
  }
);

onMounted(async () => {
  api.value = await createApiClient();
  await refreshAll();
  startAutoRefresh();
});

onUnmounted(() => {
  stopAutoRefresh();
});
</script>

<template>
  <AppShell
    :active-view="activeView"
    :health="health"
    :rekordbox-status="rekordboxStatus"
    :deemix-status="deemixStatus"
    :search-query="searchQuery"
    :title="pageTitle"
    @change-view="activeView = $event"
    @update-search-query="searchQuery = $event"
  >
    <div
      v-if="errorMessage"
      class="absolute bottom-4 right-4 z-50 flex min-h-11 max-w-xl items-center gap-3 rounded border border-error/30 bg-error-container px-4 text-sm text-on-error-container shadow-xl"
    >
      <AlertTriangle :size="18" aria-hidden="true" />
      <span>{{ errorMessage }}</span>
    </div>
    <div
      v-if="successMessage"
      class="absolute bottom-4 right-4 z-50 flex min-h-11 max-w-xl items-center gap-3 rounded border border-secondary/30 bg-secondary/10 px-4 text-sm text-secondary shadow-xl"
    >
      <CheckCircle2 :size="18" aria-hidden="true" />
      <span>{{ successMessage }}</span>
    </div>

    <DashboardView
      v-if="activeView === 'dashboard'"
      :health="health"
      :rekordbox-status="rekordboxStatus"
      :deemix-status="deemixStatus"
      :event-summaries="eventSummaries"
      :proposals="proposals"
      :library-sources="librarySources"
      :spotify-playlists="spotifyPlaylists"
      :global-acquisition-jobs="globalAcquisitionJobs"
      @change-view="activeView = $event"
    />

    <LibraryView
      v-else-if="activeView === 'library'"
      :spotify-playlists="spotifyPlaylists"
      :spotify-playlist-total="spotifyPlaylistTotal"
      :library-sources="librarySources"
      :active-review="activeLibraryReview"
      :selected-track-ids="selectedLibraryTrackIds"
      :selected-tracks="selectedLibraryTracks"
      :tag-playlist-mappings="tagPlaylistMappings"
      :rekordbox-tags="rekordboxTags"
      :proposals="proposals"
      :tag-rule-form="tagRuleForm"
      :mapping-form="mappingForm"
      :tag-rule-tag-input="tagRuleTagInput"
      :available-tag-names="availableTagNames"
      :search-query="searchQuery"
      :ready-to-apply="libraryReadyToApply"
      :rekordbox-status="rekordboxStatus"
      :loading="loading"
      @select-tag-rule-playlist="selectTagRulePlaylist"
      @select-mapping-playlist="selectMappingPlaylist"
      @save-tag-rule="saveTagRule"
      @save-tag-playlist-mapping="saveTagPlaylistMapping"
      @open-source="openLibrarySource"
      @sync-source="syncLibrarySource"
      @toggle-track="toggleLibraryTrack"
      @toggle-all-tracks="toggleAllLibraryTracks"
      @update-selected-tags="updateSelectedLibraryTags"
      @update-track-tags="updateLibraryTrackTags"
      @download-selected="downloadSelectedLibraryTracks"
      @apply-source="applyActiveLibrarySource"
      @add-tag-rule-tag="addTagRuleTag"
      @remove-tag-rule-tag="removeTagRuleTag"
      @update-tag-rule-tag-input="updateTagRuleTagInput"
    />

    <EventImportsView
      v-else-if="activeView === 'events'"
      :import-form="importForm"
      :spotify-playlists="spotifyPlaylists"
      :event-summaries="eventSummaries"
      :active-event="activeEvent"
      :acquisition-jobs="acquisitionJobs"
      :acquisition-counts="acquisitionCounts"
      :deemix-status="deemixStatus"
      :review-filter="reviewFilter"
      :filtered-event-tracks="filteredEventTracks"
      :ready-to-apply="readyToApply"
      :rekordbox-status="rekordboxStatus"
      :rekordbox-tags="rekordboxTags"
      :live-import-package="liveImportPackage"
      :loading="loading"
      :search-query="searchQuery"
      @analyze-import="analyzeImport"
      @create-live-import-package="createLiveImportPackage"
      @select-spotify-playlist="selectSpotifyPlaylist"
      @open-event="openEvent"
      @open-desktop-path="openDesktopPath"
      @refresh-event-folder="refreshEventFolder"
      @download-missing-tracks="downloadMissingTracks"
      @apply-active-event="applyActiveEvent"
      @delete-active-event="deleteActiveEvent"
      @update-review-filter="reviewFilter = $event"
      @accept-suggested-match="acceptSuggestedMatch"
      @assign-staging-file="assignStagingFile"
      @update-permanent="updatePermanent"
      @update-track-tags="updateTrackTags"
    />

    <DownloadMatchCenterView
      v-else-if="activeView === 'downloadCenter'"
      :active-event="activeEvent"
      :active-library-review="activeLibraryReview"
      :event-summaries="eventSummaries"
      :acquisition-jobs="globalAcquisitionJobs"
      :deemix-status="deemixStatus"
      :proposals="proposals"
      @change-view="activeView = $event"
      @open-event="openEvent"
      @download-missing-tracks="downloadMissingTracks"
      @refresh-event-folder="refreshEventFolder"
      @accept-suggested-match="acceptSuggestedMatch"
      @resolve-proposal="resolveProposal"
    />

    <SettingsView
      v-else
      :settings="settings"
      :storage="storage"
      @save-settings="saveSettings"
      @open-spotify-auth="openSpotifyAuth"
      @ensure-storage="ensureStorage"
    />
  </AppShell>
</template>
