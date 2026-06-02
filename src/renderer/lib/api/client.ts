import type {
  AcquisitionJob,
  AppSettings,
  AuthUrlResponse,
  BackupPruneResponse,
  BackupRestoreResponse,
  DeemixStatus,
  DeezerSearchResult,
  DiagnosticsReport,
  DuplicateResolutionItem,
  DuplicateResolutionResponse,
  DuplicateScanResult,
  EventAcquisitionResponse,
  EventApplyResponse,
  EventDeletePreview,
  EventDeleteResponse,
  EventReview,
  EventSummary,
  GlobalAcquisitionJob,
  HealthResponse,
  LibraryApplyResponse,
  LibraryDownloadResponse,
  LibraryReview,
  LibrarySource,
  LiveImportPackage,
  PathValidation,
  RekordboxBackupsResponse,
  RekordboxCollectionStats,
  RekordboxPlaylist,
  RekordboxStatus,
  RekordboxTag,
  SpotifyPlaylistsResponse,
  StorageLayout,
  SyncProposal,
  TagPlaylistMapping,
  TagRule,
} from "./types";

export class ApiClient {
  constructor(private readonly baseUrl: string) {}

  async getHealth(): Promise<HealthResponse> {
    return this.get("/api/health");
  }

  async getRekordboxStatus(): Promise<RekordboxStatus> {
    return this.get("/api/rekordbox/status");
  }

  async getRekordboxCollectionStats(): Promise<RekordboxCollectionStats> {
    return this.get("/api/rekordbox/collection-stats");
  }

  async getDiagnostics(): Promise<DiagnosticsReport> {
    return this.get("/api/diagnostics");
  }

  async listBackups(): Promise<RekordboxBackupsResponse> {
    return this.get("/api/rekordbox/backups");
  }

  async pruneBackups(): Promise<BackupPruneResponse> {
    return this.post("/api/rekordbox/backups/prune", {});
  }

  async restoreBackup(name: string): Promise<BackupRestoreResponse> {
    return this.post(`/api/rekordbox/backups/${encodeURIComponent(name)}/restore`, {});
  }

  async scanDuplicates(
    strategies: string[],
    fuzzyThreshold: number
  ): Promise<DuplicateScanResult> {
    const query = new URLSearchParams({
      strategies: strategies.join(","),
      fuzzyThreshold: String(fuzzyThreshold),
    });
    return this.get(`/api/rekordbox/duplicates?${query.toString()}`);
  }

  async resolveDuplicates(
    items: DuplicateResolutionItem[],
    dryRun = false
  ): Promise<DuplicateResolutionResponse> {
    return this.post("/api/rekordbox/duplicates/resolve", { items, dryRun });
  }

  async getSettings(): Promise<AppSettings> {
    return this.get("/api/settings");
  }

  async saveSettings(settings: AppSettings): Promise<AppSettings> {
    return this.post("/api/settings", settings);
  }

  async ensureStorage(): Promise<StorageLayout> {
    return this.post("/api/storage/ensure", {});
  }

  async getStorageLayout(): Promise<StorageLayout> {
    return this.get("/api/storage/layout");
  }

  async validatePath(path: string): Promise<PathValidation> {
    return this.get(`/api/storage/validate-path?path=${encodeURIComponent(path)}`);
  }

  async listTagRules(): Promise<TagRule[]> {
    return this.get("/api/tag-rules");
  }

  async saveTagRule(input: Omit<TagRule, "id"> & { id?: number }): Promise<TagRule> {
    return this.post("/api/tag-rules", input);
  }

  async listLibrarySources(): Promise<LibrarySource[]> {
    return this.get("/api/library/sources");
  }

  async saveLibrarySource(
    input: Omit<
      LibrarySource,
      | "id"
      | "status"
      | "newTrackCount"
      | "pendingTrackCount"
      | "readyTrackCount"
      | "importedTrackCount"
      | "conflictTrackCount"
      | "lastSyncedAt"
      | "updatedAt"
    > & { id?: number }
  ): Promise<LibrarySource> {
    return this.post("/api/library/sources", input);
  }

  async syncLibrarySource(sourceId: number): Promise<LibraryReview> {
    return this.post(`/api/library/sources/${sourceId}/sync`, {});
  }

  async syncAllLibrarySources(): Promise<LibraryReview[]> {
    return this.post("/api/library/sources/sync-all", {});
  }

  async getLibraryReview(sourceId: number): Promise<LibraryReview> {
    return this.get(`/api/library/sources/${sourceId}/review`);
  }

  async updateLibraryTracks(input: {
    sourceId: number;
    spotifyTrackIds: string[];
    status?: string | null;
    tags?: string[] | null;
    stagingFilePath?: string | null;
    rekordboxContentId?: string | null;
  }): Promise<LibraryReview> {
    return this.post("/api/library/tracks/update", input);
  }

  async downloadLibraryTracks(input: {
    sourceId: number;
    spotifyTrackIds?: string[] | null;
  }): Promise<LibraryDownloadResponse> {
    return this.post("/api/library/tracks/download", input);
  }

  async applyLibrarySource(sourceId: number): Promise<LibraryApplyResponse> {
    return this.post(`/api/library/sources/${sourceId}/apply`, {});
  }

  async searchDeezer(query: string): Promise<DeezerSearchResult[]> {
    return this.get(`/api/library/search-deezer?query=${encodeURIComponent(query)}`);
  }

  async queueDeezerTrack(sourceId: number, spotifyTrackId: string, deezerTrackId: string): Promise<{ queued: number }> {
    return this.post(`/api/library/sources/${sourceId}/tracks/${spotifyTrackId}/queue-deezer`, { deezerTrackId });
  }

  async listTagPlaylistMappings(): Promise<TagPlaylistMapping[]> {
    return this.get("/api/tag-playlist-mappings");
  }

  async saveTagPlaylistMapping(
    input: Omit<TagPlaylistMapping, "id"> & { id?: number }
  ): Promise<TagPlaylistMapping> {
    return this.post("/api/tag-playlist-mappings", input);
  }

  async listRekordboxTags(): Promise<RekordboxTag[]> {
    return this.get("/api/rekordbox/tags");
  }

  async listRekordboxPlaylists(): Promise<RekordboxPlaylist[]> {
    return this.get("/api/rekordbox/playlists");
  }

  async listProposals(): Promise<SyncProposal[]> {
    return this.get("/api/sync/proposals");
  }

  async resolveProposal(proposalId: number, status: string): Promise<SyncProposal> {
    return this.post(`/api/sync/proposals/${proposalId}/resolve`, { status });
  }

  async listGlobalAcquisitionJobs(params: {
    scope?: string | null;
    status?: string | null;
    source?: string | null;
  } = {}): Promise<GlobalAcquisitionJob[]> {
    const query = new URLSearchParams();
    if (params.scope) query.set("scope", params.scope);
    if (params.status) query.set("status", params.status);
    if (params.source) query.set("source", params.source);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return this.get(`/api/acquisition/jobs${suffix}`);
  }

  async clearAcquisitionJobs(scope?: string): Promise<{ cleared: number }> {
    const suffix = scope ? `?scope=${scope}` : "";
    return this.delete(`/api/acquisition/jobs/clear${suffix}`);
  }

  async getSpotifyAuthUrl(clientId: string, redirectUri: string): Promise<AuthUrlResponse> {
    return this.post("/api/spotify/auth-url", { clientId, redirectUri });
  }

  async listSpotifyPlaylists(offset = 0, limit = 50): Promise<SpotifyPlaylistsResponse> {
    return this.get(`/api/spotify/playlists?offset=${offset}&limit=${limit}`);
  }


  async analyzeSpotifyEvent(input: {
    playlistUrl: string;
    eventName: string;
  }): Promise<EventReview> {
    return this.post("/api/events/spotify/analyze", input);
  }

  async listEvents(): Promise<EventSummary[]> {
    return this.get("/api/events");
  }

  async createManualEvent(input: { eventName: string }): Promise<EventReview> {
    return this.post("/api/events", input);
  }

  async addEventSpotifyTrack(eventId: number, trackUrl: string): Promise<EventReview> {
    return this.post(`/api/events/${eventId}/tracks/spotify`, { trackUrl });
  }

  async getEventReview(eventId: number): Promise<EventReview> {
    return this.get(`/api/events/${eventId}/review`);
  }

  async previewEventDelete(eventId: number): Promise<EventDeletePreview> {
    return this.get(`/api/events/${eventId}/delete-preview`);
  }

  async deleteEvent(eventId: number): Promise<EventDeleteResponse> {
    return this.post(`/api/events/${eventId}/delete`, {});
  }

  async scanEventStaging(eventId: number): Promise<EventReview> {
    return this.post(`/api/events/${eventId}/staging/scan`, {});
  }

  async updateEventTrack(
    eventId: number,
    input: {
      spotifyTrackId: string;
      rekordboxContentId?: string | null;
      stagingFilePath?: string | null;
      status?: string | null;
      permanent?: boolean | null;
      tags?: string[] | null;
    }
  ): Promise<EventReview> {
    return this.post(`/api/events/${eventId}/matches`, input);
  }

  async applyEvent(eventId: number): Promise<EventApplyResponse> {
    return this.post(`/api/events/${eventId}/apply`, {});
  }

  async getDeemixStatus(): Promise<DeemixStatus> {
    return this.get("/api/providers/deemix/status");
  }

  async runAutoAcquisition(eventId: number): Promise<EventAcquisitionResponse> {
    return this.post(`/api/events/${eventId}/acquisition/auto`, {});
  }

  async listAcquisitionJobs(eventId: number): Promise<AcquisitionJob[]> {
    return this.get(`/api/events/${eventId}/acquisition/jobs`);
  }

  async retryAcquisition(eventId: number): Promise<EventAcquisitionResponse> {
    return this.post(`/api/events/${eventId}/acquisition/retry`, {});
  }

  async searchEventDeezer(eventId: number, query: string): Promise<DeezerSearchResult[]> {
    return this.get(`/api/events/${eventId}/search-deezer?query=${encodeURIComponent(query)}`);
  }

  async queueEventDeezerTrack(eventId: number, spotifyTrackId: string, deezerTrackId: string): Promise<{ queued: number; title?: string; artist?: string }> {
    return this.post(`/api/events/${eventId}/tracks/${spotifyTrackId}/queue-deezer`, { deezerTrackId });
  }

  async createLiveImport(input: { eventName: string }): Promise<LiveImportPackage> {
    return this.post("/api/live-imports", input);
  }

  /** Absolute URL for a path — used to open an EventSource (SSE) connection. */
  streamUrl(path: string): string {
    return `${this.baseUrl}${path}`;
  }

  private async get<T>(path: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`);
    return this.parse<T>(response);
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    return this.parse<T>(response);
  }

  private async delete<T>(path: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, { method: "DELETE" });
    return this.parse<T>(response);
  }

  private async parse<T>(response: Response): Promise<T> {
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = payload?.detail ?? payload?.message ?? response.statusText;
      throw new Error(String(detail));
    }
    return payload as T;
  }
}

export async function createApiClient(): Promise<ApiClient> {
  if (window.desktop) {
    return new ApiClient(await window.desktop.getApiBaseUrl());
  }
  return new ApiClient(import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8765");
}
