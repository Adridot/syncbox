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
  permanentPath: string;
  manualCollectionPath: string;
  backupRetention: number;
};

export type SettingsBackup = {
  type: string;
  version: number;
  exportedAt: string;
  settings: Record<string, string>;
};

export type SettingsImportResponse = {
  applied: number;
  settings: AppSettings;
};

export type DataImportResponse = {
  restored: boolean;
  safetyBackupPath: string | null;
  message: string;
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
  scope: "event" | "library" | "collection";
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

export type RekordboxBackup = {
  name: string;
  path: string;
  createdAt: number;
  sizeBytes: number;
  fileCount: number;
};

export type RekordboxBackupsResponse = {
  backups: RekordboxBackup[];
  readable: boolean;
  retention: number;
  totalSizeBytes: number;
};

export type BackupPruneResponse = {
  removed: number;
  kept: number;
  freedBytes: number;
  readable: boolean;
};

export type BackupRestoreResponse = {
  restored: string;
  restoredFiles: number;
  safetyBackupPath: string;
};

export type DiagnosticStatus = "ok" | "warn" | "error";

export type DiagnosticCheck = {
  key: string;
  label: string;
  status: DiagnosticStatus;
  detail: string;
  hint?: string | null;
};

export type DiagnosticsReport = {
  status: DiagnosticStatus;
  generatedAt: string;
  checks: DiagnosticCheck[];
};

export type DuplicateTrack = {
  contentId: string;
  title: string;
  artist: string;
  durationMs: number | null;
  isrc: string | null;
  filePath: string | null;
  fileName: string | null;
  fileType: string | null;
  bitRate: number | null;
  sampleRate: number | null;
  bitDepth: number | null;
  fileSize: number | null;
  bpm: number | null;
  rating: number | null;
  cueCount: number;
  playlistCount: number;
  tagCount: number;
  analysed: boolean;
  protected: boolean;
  fileMissing: boolean;
  dateCreated: string | null;
  qualityScore: number;
  isKeeper: boolean;
};

export type DuplicateGroup = {
  groupId: string;
  reason: "isrc" | "fuzzy";
  confidence: number;
  note: string | null;
  keeperContentId: string;
  tracks: DuplicateTrack[];
};

export type DuplicateScanResult = {
  available: boolean;
  reason: string | null;
  totalTracks: number;
  strategies: string[];
  groups: DuplicateGroup[];
};

export type DuplicateResolutionItem = {
  groupId?: string;
  keeperContentId: string;
  removeContentIds: string[];
  deleteFiles?: boolean;
  dismiss?: boolean;
};

export type MissingTrack = {
  contentId: string;
  title: string;
  artist: string;
  durationMs: number | null;
  isrc: string | null;
  filePath: string | null;
  fileName: string | null;
  fileType: string | null;
  playlistCount: number;
  tagCount: number;
  protected: boolean;
};

export type MissingFilesReport = {
  available: boolean;
  reason: string | null;
  total: number;
  missing: number;
  tracks: MissingTrack[];
};

export type RelinkCandidate = {
  filePath: string;
  fileName: string;
  score: number;
  reason: string;
};

export type MissingActionResponse = {
  contentId: string;
  filePath: string | null;
  title: string | null;
  artist: string | null;
  backupPath: string | null;
  message: string;
};

export type UntaggedSuggestion = "junk" | "dup_of_tagged" | "alt_version" | "review";

export type UntaggedTrack = {
  contentId: string;
  title: string;
  artist: string;
  durationMs: number | null;
  isrc: string | null;
  filePath: string | null;
  fileName: string | null;
  playlistCount: number;
  fileMissing: boolean;
  protected: boolean;
  dateCreated: string | null;
  suggestion: UntaggedSuggestion;
  suggestionDetail: string;
};

export type UntaggedReport = {
  available: boolean;
  reason: string | null;
  total: number;
  untagged: number;
  tracks: UntaggedTrack[];
  tags: RekordboxTag[];
};

export type UntaggedTagResponse = {
  backupPath: string | null;
  tagged: number;
  createdTag: boolean;
  tagName: string;
};

export type UntaggedDeleteResponse = {
  backupPath: string | null;
  removed: number;
  skippedProtected: number;
};

export type DuplicateResolutionResponse = {
  backupPath: string | null;
  removedFromRekordbox: number;
  filesDeleted: number;
  relinkedPlaylists: number;
  relinkedTags: number;
  skippedProtected: number;
  dismissed: number;
  dryRun: boolean;
  warnings: string[];
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
