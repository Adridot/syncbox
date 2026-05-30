export type DeezerSearchResult = {
  id: string;
  title: string;
  artist: string;
  album?: string | null;
  durationMs?: number | null;
  coverUrl?: string | null;
  previewUrl?: string | null;
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

export type RekordboxCollectionStats = {
  available: boolean;
  total: number;
  tagged: number;
  untagged: number;
  withoutIsrc: number;
  withoutArtist: number;
  reason?: string | null;
};

export type AppSettings = {
  spotifyClientId: string;
  spotifyRedirectUri: string;
  rekordboxDatabaseDir: string;
  storageRoot: string;
  apiPort: number;
  permanentPath: string;
  manualCollectionPath: string;
};

export type StorageLayout = {
  root: string;
  inbox: string;
  permanent: string;
  events: string;
  manualCollection: string;
  backups: string;
};

export type PathValidation = {
  path: string;
  configured: boolean;
  exists: boolean;
  isDir: boolean;
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

export type TrackReview = {
  id: number;
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
