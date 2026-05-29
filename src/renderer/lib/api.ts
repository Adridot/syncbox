export type DeezerSearchResult = {
  id: string;
  title: string;
  artist: string;
  album?: string | null;
  durationMs?: number | null;
};

export type HealthResponse = {
  status: string;
  service: string;
  version: string;
  databasePath: string;
};

export type RekordboxStatus = {
  databaseDir: string;
  databaseFile: string;
  databaseExists: boolean;
  rekordboxRunning: boolean;
  mutationAllowed: boolean;
  runningProcesses: Array<{ pid: number; command: string }>;
};

export type AppSettings = {
  spotifyClientId: string;
  spotifyRedirectUri: string;
  rekordboxDatabaseDir: string;
  storageRoot: string;
  apiPort: number;
};

export type StorageLayout = {
  root: string;
  inbox: string;
  permanent: string;
  events: string;
  manualCollection: string;
  backups: string;
};

export type TagRule = {
  id: number;
  sourcePlaylistId: string;
  sourcePlaylistName: string;
  tags: string[];
  enabled: boolean;
};

export type TagPlaylistMapping = {
  id: number;
  tagName: string;
  spotifyPlaylistId: string;
  spotifyPlaylistName: string;
  enabled: boolean;
};

export type SyncProposal = {
  id: number;
  proposalType: string;
  status: string;
  spotifyTrackId?: string | null;
  rekordboxContentId?: string | null;
  filePath?: string | null;
  reason: string;
  payload: Record<string, unknown>;
  createdAt: string;
};

export type LibrarySource = {
  id: number;
  spotifyPlaylistId: string;
  spotifyPlaylistName: string;
  spotifySnapshotId?: string | null;
  imageUrl?: string | null;
  trackCount: number;
  tags: string[];
  enabled: boolean;
  status: string;
  newTrackCount: number;
  pendingTrackCount: number;
  readyTrackCount: number;
  importedTrackCount: number;
  conflictTrackCount: number;
  lastSyncedAt?: string | null;
  updatedAt: string;
};

export type LibraryTrackReview = {
  id: number;
  sourceId: number;
  spotifyTrackId: string;
  spotifyUri: string;
  title: string;
  artists: string[];
  durationMs: number;
  isrc?: string | null;
  status: string;
  rekordboxContentId?: string | null;
  rekordboxTitle?: string | null;
  rekordboxArtist?: string | null;
  rekordboxFilePath?: string | null;
  matchMethod?: string | null;
  confidence: number;
  stagingFilePath?: string | null;
  tags: string[];
  reason: string;
};

export type LibraryReview = {
  source: LibrarySource;
  totalTracks: number;
  newTracks: number;
  matchedTracks: number;
  missingTracks: number;
  readyTracks: number;
  importedTracks: number;
  ignoredTracks: number;
  conflictTracks: number;
  removedTracks: number;
  tracks: LibraryTrackReview[];
};

export type LibraryDownloadResponse = {
  sourceId: number;
  created: number;
  queued: number;
  downloading: number;
  downloaded: number;
  ready: number;
  failed: number;
  ambiguous: number;
  jobs: AcquisitionJob[];
  review: LibraryReview;
};

export type LibraryApplyResponse = {
  sourceId: number;
  backupPath: string;
  imported: number;
  tagged: number;
  spotifyAdded: number;
  warnings: string[];
};

export type GlobalAcquisitionJob = {
  id?: number | null;
  scope: "event" | "library";
  eventId?: number | null;
  sourceId?: number | null;
  sourceName: string;
  spotifyTrackId: string;
  trackTitle: string;
  trackArtists: string[];
  provider: string;
  deezerTrackId?: string | null;
  status: string;
  confidence: number;
  matchMethod?: string | null;
  downloadId?: string | null;
  outputDir?: string | null;
  error?: string | null;
  updatedAt: string;
};

export type AuthUrlResponse = {
  authorizationUrl: string;
  state: string;
};

export type SpotifyPlaylistSummary = {
  id: string;
  name: string;
  owner: string;
  trackCount: number;
  public: boolean | null;
  snapshotId: string | null;
  imageUrl?: string | null;
  url: string;
};

export type SpotifyPlaylistsResponse = {
  items: SpotifyPlaylistSummary[];
  total: number;
  limit: number;
  offset: number;
  nextOffset: number | null;
};

export type LiveImportPackage = {
  eventName: string;
  eventSlug: string;
  eventDir: string;
  audioDir: string;
  playlistPath: string;
  trackCount: number;
  audioFiles: string[];
};

export type RekordboxTag = {
  id: string;
  name: string;
  parentId?: string | null;
};

export type RekordboxPlaylist = {
  id: string;
  name: string;
  parentId?: string | null;
  isFolder: boolean;
  isSmartPlaylist: boolean;
  trackCount: number;
};

export type EventTrackReview = {
  id: number;
  eventId: number;
  spotifyTrackId: string;
  spotifyUri: string;
  title: string;
  artists: string[];
  durationMs: number;
  isrc?: string | null;
  status: string;
  rekordboxContentId?: string | null;
  rekordboxTitle?: string | null;
  rekordboxArtist?: string | null;
  rekordboxFilePath?: string | null;
  matchMethod?: string | null;
  confidence: number;
  stagingFilePath?: string | null;
  permanent: boolean;
  tags: string[];
  reason: string;
};

export type StagingFile = {
  id?: number | null;
  eventId: number;
  filePath: string;
  title: string;
  artist: string;
  durationMs?: number | null;
  isrc?: string | null;
  matchedSpotifyTrackId?: string | null;
  status: string;
};

export type EventReview = {
  id: number;
  eventName: string;
  eventSlug: string;
  spotifyPlaylistId: string;
  spotifyPlaylistName: string;
  spotifySnapshotId?: string | null;
  defaultTag: string;
  status: string;
  eventDir: string;
  audioDir: string;
  playlistPath: string;
  totalTracks: number;
  matchedTracks: number;
  missingTracks: number;
  ambiguousTracks: number;
  readyTracks: number;
  appliedTracks: number;
  ignoredTracks: number;
  tracks: EventTrackReview[];
  stagingFiles: StagingFile[];
};

export type EventSummary = {
  id: number;
  eventName: string;
  spotifyPlaylistName: string;
  status: string;
  totalTracks: number;
  readyTracks: number;
  createdAt: string;
};

export type EventApplyResponse = {
  eventId: number;
  backupPath: string;
  imported: number;
  tagged: number;
  permanent: number;
  spotifyAdded: number;
  smartPlaylist?: string | null;
  warnings: string[];
};

export type DeemixStatus = {
  baseUrl: string;
  available: boolean;
  authenticated: boolean;
  detail: string;
  version?: string | null;
};

export type AcquisitionJob = {
  id?: number | null;
  eventId: number;
  spotifyTrackId: string;
  provider: string;
  deezerTrackId?: string | null;
  status: string;
  confidence: number;
  matchMethod?: string | null;
  downloadId?: string | null;
  outputDir?: string | null;
  error?: string | null;
  payload: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};

export type EventAcquisitionResponse = {
  eventId: number;
  created: number;
  queued: number;
  downloading: number;
  downloaded: number;
  ready: number;
  failed: number;
  ambiguous: number;
  jobs: AcquisitionJob[];
  review: EventReview;
};

export type EventDeletePreview = {
  eventId: number;
  eventName: string;
  defaultTag: string;
  localOnly: boolean;
  tracksWithEventTag: number;
  willDeleteFromRekordbox: number;
  willRemoveEventTag: number;
  protectedTracks: number;
  deletedSamples: string[];
  protectedSamples: string[];
  warnings: string[];
};

export type EventDeleteResponse = EventDeletePreview & {
  backupPath?: string | null;
  deletedFromRekordbox: number;
  removedEventTags: number;
  localEventDeleted: boolean;
};

export class ApiClient {
  constructor(private readonly baseUrl: string) {}

  async getHealth(): Promise<HealthResponse> {
    return this.get("/api/health");
  }

  async getRekordboxStatus(): Promise<RekordboxStatus> {
    return this.get("/api/rekordbox/status");
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

  async createLiveImport(input: { eventName: string }): Promise<LiveImportPackage> {
    return this.post("/api/live-imports", input);
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
