from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    database_path: str = Field(alias="databasePath")


class ProcessInfo(BaseModel):
    pid: int
    command: str


class RekordboxStatus(BaseModel):
    database_dir: str = Field(alias="databaseDir")
    database_file: str = Field(alias="databaseFile")
    database_exists: bool = Field(alias="databaseExists")
    rekordbox_running: bool = Field(alias="rekordboxRunning")
    mutation_allowed: bool = Field(alias="mutationAllowed")
    running_processes: list[ProcessInfo] = Field(alias="runningProcesses")


class AppSettings(BaseModel):
    spotify_client_id: str = Field(default="", alias="spotifyClientId")
    spotify_redirect_uri: str = Field(
        default="http://127.0.0.1:8765/api/spotify/callback",
        alias="spotifyRedirectUri",
    )
    rekordbox_database_dir: str = Field(alias="rekordboxDatabaseDir")
    storage_root: str = Field(alias="storageRoot")
    api_port: int = Field(default=8765, alias="apiPort")
    permanent_path: str = Field(default="", alias="permanentPath")
    manual_collection_path: str = Field(default="", alias="manualCollectionPath")


class StorageLayout(BaseModel):
    root: str
    inbox: str
    permanent: str
    events: str
    manual_collection: str = Field(alias="manualCollection")
    backups: str


class TagRuleIn(BaseModel):
    id: int | None = None
    source_playlist_id: str = Field(alias="sourcePlaylistId")
    source_playlist_name: str = Field(alias="sourcePlaylistName")
    tags: list[str]
    enabled: bool = True


class TagRule(TagRuleIn):
    id: int


class TagPlaylistMappingIn(BaseModel):
    id: int | None = None
    tag_name: str = Field(alias="tagName", min_length=1)
    spotify_playlist_id: str = Field(alias="spotifyPlaylistId", min_length=1)
    spotify_playlist_name: str = Field(alias="spotifyPlaylistName", min_length=1)
    enabled: bool = True


class TagPlaylistMapping(TagPlaylistMappingIn):
    id: int


class SyncProposal(BaseModel):
    id: int
    proposal_type: str = Field(alias="proposalType")
    status: str
    spotify_track_id: str | None = Field(default=None, alias="spotifyTrackId")
    rekordbox_content_id: str | None = Field(default=None, alias="rekordboxContentId")
    file_path: str | None = Field(default=None, alias="filePath")
    reason: str
    payload: dict[str, Any]
    created_at: str = Field(alias="createdAt")


class SyncProposalResolveRequest(BaseModel):
    status: Literal["approved", "ignored", "protected"] = "ignored"


class SpotifyAuthUrlRequest(BaseModel):
    client_id: str = Field(alias="clientId")
    redirect_uri: str = Field(alias="redirectUri")


class SpotifyAuthUrlResponse(BaseModel):
    authorization_url: str = Field(alias="authorizationUrl")
    state: str


class SpotifyPlaylistSummary(BaseModel):
    id: str
    name: str
    owner: str
    track_count: int = Field(alias="trackCount")
    public: bool | None = None
    snapshot_id: str | None = Field(default=None, alias="snapshotId")
    image_url: str | None = Field(default=None, alias="imageUrl")
    url: str


class SpotifyPlaylistsResponse(BaseModel):
    items: list[SpotifyPlaylistSummary]
    total: int
    limit: int
    offset: int
    next_offset: int | None = Field(default=None, alias="nextOffset")


class LiveImportRequest(BaseModel):
    event_name: str = Field(alias="eventName", min_length=1)


class LiveImportPackage(BaseModel):
    event_name: str = Field(alias="eventName")
    event_slug: str = Field(alias="eventSlug")
    event_dir: str = Field(alias="eventDir")
    audio_dir: str = Field(alias="audioDir")
    playlist_path: str = Field(alias="playlistPath")
    track_count: int = Field(alias="trackCount")
    audio_files: list[str] = Field(alias="audioFiles")


class SpotifyEventPreviewRequest(BaseModel):
    playlist_url: HttpUrl = Field(alias="playlistUrl")
    event_name: str = Field(alias="eventName", min_length=1)


class SpotifyEventAnalyzeRequest(SpotifyEventPreviewRequest):
    pass


class ManualEventCreateRequest(BaseModel):
    event_name: str = Field(alias="eventName", min_length=1)


class EventTrackAddRequest(BaseModel):
    track_url: str = Field(alias="trackUrl", min_length=1)


class EventTrackUpdateRequest(BaseModel):
    spotify_track_id: str = Field(alias="spotifyTrackId", min_length=1)
    rekordbox_content_id: str | None = Field(default=None, alias="rekordboxContentId")
    staging_file_path: str | None = Field(default=None, alias="stagingFilePath")
    status: str | None = None


class EventApplyResponse(BaseModel):
    event_id: int = Field(alias="eventId")
    backup_path: str = Field(alias="backupPath")
    imported: int
    tagged: int
    spotify_added: int = Field(alias="spotifyAdded")
    smart_playlist: str | None = Field(default=None, alias="smartPlaylist")
    warnings: list[str] = Field(default_factory=list)


class EventDeletePreview(BaseModel):
    event_id: int = Field(alias="eventId")
    event_name: str = Field(alias="eventName")
    default_tag: str = Field(alias="defaultTag")
    local_only: bool = Field(default=False, alias="localOnly")
    tracks_with_event_tag: int = Field(default=0, alias="tracksWithEventTag")
    will_delete_from_rekordbox: int = Field(default=0, alias="willDeleteFromRekordbox")
    will_remove_event_tag: int = Field(default=0, alias="willRemoveEventTag")
    protected_tracks: int = Field(default=0, alias="protectedTracks")
    deleted_samples: list[str] = Field(default_factory=list, alias="deletedSamples")
    protected_samples: list[str] = Field(default_factory=list, alias="protectedSamples")
    warnings: list[str] = Field(default_factory=list)


class EventDeleteResponse(EventDeletePreview):
    backup_path: str | None = Field(default=None, alias="backupPath")
    deleted_from_rekordbox: int = Field(default=0, alias="deletedFromRekordbox")
    removed_event_tags: int = Field(default=0, alias="removedEventTags")
    local_event_deleted: bool = Field(default=False, alias="localEventDeleted")


class DeemixStatus(BaseModel):
    base_url: str = Field(alias="baseUrl")
    available: bool
    authenticated: bool
    detail: str
    version: str | None = None


class AcquisitionJob(BaseModel):
    id: int | None = None
    event_id: int = Field(alias="eventId")
    spotify_track_id: str = Field(alias="spotifyTrackId")
    provider: str
    deezer_track_id: str | None = Field(default=None, alias="deezerTrackId")
    status: str
    confidence: int = 0
    match_method: str | None = Field(default=None, alias="matchMethod")
    download_id: str | None = Field(default=None, alias="downloadId")
    output_dir: str | None = Field(default=None, alias="outputDir")
    error: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class RekordboxTag(BaseModel):
    id: str
    name: str
    parent_id: str | None = Field(default=None, alias="parentId")


class RekordboxPlaylist(BaseModel):
    id: str
    name: str
    parent_id: str | None = Field(default=None, alias="parentId")
    is_folder: bool = Field(alias="isFolder")
    is_smart_playlist: bool = Field(alias="isSmartPlaylist")
    track_count: int = Field(default=0, alias="trackCount")


class StagingFile(BaseModel):
    id: int | None = None
    event_id: int = Field(alias="eventId")
    file_path: str = Field(alias="filePath")
    title: str
    artist: str
    duration_ms: int | None = Field(default=None, alias="durationMs")
    isrc: str | None = None
    matched_spotify_track_id: str | None = Field(
        default=None, alias="matchedSpotifyTrackId"
    )
    status: str


class EventTrackReview(BaseModel):
    id: int
    event_id: int = Field(alias="eventId")
    spotify_track_id: str = Field(alias="spotifyTrackId")
    spotify_uri: str = Field(alias="spotifyUri")
    title: str
    artists: list[str]
    duration_ms: int = Field(alias="durationMs")
    isrc: str | None = None
    status: str
    rekordbox_content_id: str | None = Field(default=None, alias="rekordboxContentId")
    rekordbox_title: str | None = Field(default=None, alias="rekordboxTitle")
    rekordbox_artist: str | None = Field(default=None, alias="rekordboxArtist")
    rekordbox_file_path: str | None = Field(default=None, alias="rekordboxFilePath")
    match_method: str | None = Field(default=None, alias="matchMethod")
    confidence: int = 0
    staging_file_path: str | None = Field(default=None, alias="stagingFilePath")
    reason: str


class EventReview(BaseModel):
    id: int
    event_name: str = Field(alias="eventName")
    event_slug: str = Field(alias="eventSlug")
    spotify_playlist_id: str = Field(alias="spotifyPlaylistId")
    spotify_playlist_name: str = Field(alias="spotifyPlaylistName")
    spotify_snapshot_id: str | None = Field(default=None, alias="spotifySnapshotId")
    default_tag: str = Field(alias="defaultTag")
    status: str
    event_dir: str = Field(alias="eventDir")
    audio_dir: str = Field(alias="audioDir")
    playlist_path: str = Field(alias="playlistPath")
    total_tracks: int = Field(alias="totalTracks")
    matched_tracks: int = Field(alias="matchedTracks")
    missing_tracks: int = Field(alias="missingTracks")
    ambiguous_tracks: int = Field(alias="ambiguousTracks")
    ready_tracks: int = Field(alias="readyTracks")
    applied_tracks: int = Field(alias="appliedTracks")
    ignored_tracks: int = Field(alias="ignoredTracks")
    tracks: list[EventTrackReview]
    staging_files: list[StagingFile] = Field(alias="stagingFiles")


class EventAcquisitionResponse(BaseModel):
    event_id: int = Field(alias="eventId")
    created: int
    queued: int
    downloading: int
    downloaded: int
    ready: int
    failed: int
    ambiguous: int
    jobs: list[AcquisitionJob]
    review: EventReview


class LibrarySourceIn(BaseModel):
    id: int | None = None
    spotify_playlist_id: str = Field(alias="spotifyPlaylistId", min_length=1)
    spotify_playlist_name: str = Field(alias="spotifyPlaylistName", min_length=1)
    spotify_snapshot_id: str | None = Field(default=None, alias="spotifySnapshotId")
    image_url: str | None = Field(default=None, alias="imageUrl")
    track_count: int = Field(default=0, alias="trackCount")
    tags: list[str]
    enabled: bool = True


class LibrarySource(LibrarySourceIn):
    id: int
    status: str
    new_track_count: int = Field(default=0, alias="newTrackCount")
    pending_track_count: int = Field(default=0, alias="pendingTrackCount")
    ready_track_count: int = Field(default=0, alias="readyTrackCount")
    imported_track_count: int = Field(default=0, alias="importedTrackCount")
    conflict_track_count: int = Field(default=0, alias="conflictTrackCount")
    last_synced_at: str | None = Field(default=None, alias="lastSyncedAt")
    updated_at: str = Field(alias="updatedAt")


class LibraryTrackReview(BaseModel):
    id: int
    source_id: int = Field(alias="sourceId")
    spotify_track_id: str = Field(alias="spotifyTrackId")
    spotify_uri: str = Field(alias="spotifyUri")
    title: str
    artists: list[str]
    duration_ms: int = Field(alias="durationMs")
    isrc: str | None = None
    status: str
    rekordbox_content_id: str | None = Field(default=None, alias="rekordboxContentId")
    rekordbox_title: str | None = Field(default=None, alias="rekordboxTitle")
    rekordbox_artist: str | None = Field(default=None, alias="rekordboxArtist")
    rekordbox_file_path: str | None = Field(default=None, alias="rekordboxFilePath")
    match_method: str | None = Field(default=None, alias="matchMethod")
    confidence: int = 0
    staging_file_path: str | None = Field(default=None, alias="stagingFilePath")
    tags: list[str] = Field(default_factory=list)
    reason: str
    pending_deezer_track_id: str | None = Field(default=None, alias="pendingDeezerTrackId")
    pending_deezer_isrc: str | None = Field(default=None, alias="pendingDeezerIsrc")


class LibraryReview(BaseModel):
    source: LibrarySource
    total_tracks: int = Field(alias="totalTracks")
    new_tracks: int = Field(alias="newTracks")
    matched_tracks: int = Field(alias="matchedTracks")
    missing_tracks: int = Field(alias="missingTracks")
    ready_tracks: int = Field(alias="readyTracks")
    imported_tracks: int = Field(alias="importedTracks")
    ignored_tracks: int = Field(alias="ignoredTracks")
    conflict_tracks: int = Field(alias="conflictTracks")
    removed_tracks: int = Field(alias="removedTracks")
    tracks: list[LibraryTrackReview]


class LibraryTrackUpdateRequest(BaseModel):
    source_id: int = Field(alias="sourceId")
    spotify_track_ids: list[str] = Field(alias="spotifyTrackIds", min_length=1)
    status: str | None = None
    tags: list[str] | None = None
    staging_file_path: str | None = Field(default=None, alias="stagingFilePath")
    rekordbox_content_id: str | None = Field(default=None, alias="rekordboxContentId")


class LibraryTrackDownloadRequest(BaseModel):
    source_id: int = Field(alias="sourceId")
    spotify_track_ids: list[str] | None = Field(default=None, alias="spotifyTrackIds")


class LibraryApplyResponse(BaseModel):
    source_id: int = Field(alias="sourceId")
    backup_path: str = Field(alias="backupPath")
    imported: int
    tagged: int
    spotify_added: int = Field(alias="spotifyAdded")
    warnings: list[str] = Field(default_factory=list)


class GlobalAcquisitionJob(BaseModel):
    id: int | None = None
    scope: Literal["event", "library"]
    event_id: int | None = Field(default=None, alias="eventId")
    source_id: int | None = Field(default=None, alias="sourceId")
    source_name: str = Field(alias="sourceName")
    spotify_track_id: str = Field(alias="spotifyTrackId")
    track_title: str = Field(alias="trackTitle")
    track_artists: list[str] = Field(default_factory=list, alias="trackArtists")
    provider: str
    deezer_track_id: str | None = Field(default=None, alias="deezerTrackId")
    status: str
    confidence: int = 0
    match_method: str | None = Field(default=None, alias="matchMethod")
    download_id: str | None = Field(default=None, alias="downloadId")
    output_dir: str | None = Field(default=None, alias="outputDir")
    error: str | None = None
    updated_at: str = Field(alias="updatedAt")


class EventSummary(BaseModel):
    id: int
    event_name: str = Field(alias="eventName")
    spotify_playlist_name: str = Field(alias="spotifyPlaylistName")
    status: str
    total_tracks: int = Field(alias="totalTracks")
    ready_tracks: int = Field(alias="readyTracks")
    created_at: str = Field(alias="createdAt")


class DeezerSearchResult(BaseModel):
    id: str
    title: str
    artist: str
    album: str | None = None
    duration_ms: int | None = Field(default=None, alias="durationMs")
    cover_url: str | None = Field(default=None, alias="coverUrl")
    preview_url: str | None = Field(default=None, alias="previewUrl")


class SpotifyTrack(BaseModel):
    id: str
    uri: str
    title: str
    artists: list[str]
    duration_ms: int = Field(alias="durationMs")
    isrc: str | None = None


class RekordboxTrack(BaseModel):
    content_id: str = Field(alias="contentId")
    title: str
    artist: str
    duration_ms: int | None = Field(default=None, alias="durationMs")
    isrc: str | None = None
    file_path: str | None = Field(default=None, alias="filePath")
    protected: bool = False


ProposalType = Literal[
    "add_to_rekordbox",
    "add_to_spotify",
    "remove_from_rekordbox",
    "remove_from_spotify",
    "manual_match",
    "protect_manual_track",
]
