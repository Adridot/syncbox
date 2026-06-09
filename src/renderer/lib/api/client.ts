import type {
  AcquisitionJob,
  AppSettings,
  AuthUrlResponse,
  BackupPruneResponse,
  BackupRestoreResponse,
  DataImportResponse,
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
  MissingActionResponse,
  MissingFilesReport,
  PathValidation,
  RelinkCandidate,
  RekordboxBackupsResponse,
  RekordboxCollectionStats,
  SettingsBackup,
  SettingsImportResponse,
  RekordboxStatus,
  RekordboxTag,
  SpotifyConnectionStatus,
  SpotifyPlaylistsResponse,
  StorageLayout,
  TagRule,
  UntaggedDeleteResponse,
  UntaggedReport,
  UntaggedTagResponse,
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

  async scanMissingFiles(): Promise<MissingFilesReport> {
    return this.get("/api/rekordbox/missing");
  }

  async removeMissingEntry(contentId: string): Promise<MissingActionResponse> {
    return this.post(`/api/rekordbox/missing/${encodeURIComponent(contentId)}/remove`, {});
  }

  async getRelinkCandidates(contentId: string): Promise<RelinkCandidate[]> {
    return this.get(`/api/rekordbox/missing/${encodeURIComponent(contentId)}/relink-candidates`);
  }

  async relinkMissingEntry(contentId: string, filePath: string): Promise<MissingActionResponse> {
    return this.post(`/api/rekordbox/missing/${encodeURIComponent(contentId)}/relink`, { filePath });
  }

  async redownloadMissingEntry(contentId: string): Promise<MissingActionResponse> {
    return this.post(`/api/rekordbox/missing/${encodeURIComponent(contentId)}/redownload`, {});
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

  async getUntaggedTracks(): Promise<UntaggedReport> {
    return this.get("/api/rekordbox/untagged");
  }

  async tagUntaggedTracks(
    contentIds: string[],
    tagName: string,
    category = "Genre"
  ): Promise<UntaggedTagResponse> {
    return this.post("/api/rekordbox/untagged/tag", { contentIds, tagName, category });
  }

  async deleteUntaggedTracks(contentIds: string[]): Promise<UntaggedDeleteResponse> {
    return this.post("/api/rekordbox/untagged/delete", { contentIds });
  }

  async getSettings(): Promise<AppSettings> {
    // In the desktop app, read from electron-store: it's instant and durable, so
    // settings populate the moment the window opens instead of racing (and
    // losing to) the slow Python service boot. The main process keeps this JSON
    // mirror in sync with the service DB.
    if (window.desktop?.settings) {
      return window.desktop.settings.get();
    }
    return this.get("/api/settings");
  }

  async saveSettings(settings: AppSettings): Promise<AppSettings> {
    // The service is authoritative for canonicalisation (it preserves blank
    // credentials and resolves paths) and side effects, so persist there first,
    // then mirror the canonical result into electron-store for instant cold-start
    // reads.
    const canonical = await this.post<AppSettings>("/api/settings", settings);
    if (window.desktop?.settings) {
      await window.desktop.settings.set(canonical);
    }
    return canonical;
  }

  async exportSettings(): Promise<SettingsBackup> {
    return this.get("/api/settings/export");
  }

  async importSettings(backup: SettingsBackup): Promise<SettingsImportResponse> {
    return this.post("/api/settings/import", backup);
  }

  /** Full-database export as a blob (for a direct download). */
  async exportData(): Promise<Blob> {
    const response = await fetch(`${this.baseUrl}/api/data/export`);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(String(payload?.detail ?? payload?.message ?? response.statusText));
    }
    return response.blob();
  }

  async importData(file: File): Promise<DataImportResponse> {
    const response = await fetch(`${this.baseUrl}/api/data/import`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
    });
    return this.parse<DataImportResponse>(response);
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

  async deleteLibrarySource(sourceId: number): Promise<{ deleted: boolean; sourceId: number }> {
    return this.delete(`/api/library/sources/${sourceId}`);
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

  async listRekordboxTags(): Promise<RekordboxTag[]> {
    return this.get("/api/rekordbox/tags");
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

  async testSpotifyConnection(): Promise<SpotifyConnectionStatus> {
    return this.post("/api/spotify/test", {});
  }

  async getSpotifyStatus(): Promise<SpotifyConnectionStatus> {
    return this.get("/api/spotify/status");
  }

  async getSpotifyAuthUrl(clientId: string): Promise<AuthUrlResponse> {
    return this.post("/api/spotify/auth-url", { clientId });
  }

  async disconnectSpotify(): Promise<SpotifyConnectionStatus> {
    return this.post("/api/spotify/disconnect", {});
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

  async loginDeemixArl(): Promise<DeemixStatus> {
    return this.post("/api/providers/deemix/login", {});
  }

  async runAutoAcquisition(eventId: number): Promise<EventAcquisitionResponse> {
    return this.post(`/api/events/${eventId}/acquisition/auto`, {});
  }

  async listAcquisitionJobs(eventId: number): Promise<AcquisitionJob[]> {
    return this.get(`/api/events/${eventId}/acquisition/jobs`);
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
