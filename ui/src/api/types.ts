/* Shared payload shapes of the sidecar REST contract (api.py). Only the
   fields the UI actually reads — the sidecar may send more. */

export interface Source {
  id: number
  spotify_playlist_id: string
  name: string
  snapshot_id: string | null
  tags: string[]
  enabled: number
  status: string
  created_at: string
}

export interface LibraryTrack {
  id: number
  source_id: number
  spotify_track_id: string
  title: string | null
  artist: string | null
  duration_ms: number | null
  isrc: string | null
  status: string
  content_id: string | null
  match_method: string | null
  confidence: number | null
  staging_file_path: string | null
  tags: string[]
  prior_status: string | null
  /** joined from the RB snapshot for matched rows; null otherwise */
  bit_rate?: number | null
}

export interface MyTag {
  name: string
  category: string | null
}

export interface PlaylistPreview {
  name: string
  owner: string | null
  tracks_total: number
  image_url: string | null
}

export interface SpotifyPlaylist extends PlaylistPreview {
  spotify_playlist_id: string
}

export interface EventSummary {
  id: number
  name: string
  slug: string
  default_tag: string
  spotify_playlist_id: string
  staging_dir: string | null
  status: string
  applied_at: string | null
  created_at: string
  n_tracks: number
  pending_delta: number
}

export interface EventTrack {
  id: number
  event_id: number
  spotify_track_id: string | null
  title: string | null
  artist: string | null
  duration_ms: number | null
  isrc: string | null
  status: string
  content_id: string | null
  confidence: number | null
  staging_file_path: string | null
  added_after_apply: number
  prior_status: string | null
}

export interface EventDeletePreview {
  dry_run: boolean
  tag_id: string | null
  contents: Array<{ content_id: string; title: string | null; action: 'keep' | 'soft_delete'; reason: string }>
  playlists: Array<{ playlist_id: string; name: string }>
  artifacts: string[]
  removed_files?: unknown[]
}

export interface MatchCandidate {
  content_id: string
  title: string | null
  artist: string | null
  duration_ms: number | null
  bit_rate: number | null
  confidence: number
}

/** mutate() freshness fingerprint — echoed back VERBATIM (JSON arrays). */
export type Fingerprint = unknown

export interface DuplicateMember {
  content_id: string
  title: string | null
  artist: string | null
  bit_rate: number | null
  file_missing: boolean
  protected: boolean
  playlist_count: number
  cue_count: number
  resolved_path: string | null
  quality_verdict: 'ok' | 'lossy_source_probable' | 'incertain'
  quality_reason: string
}

export interface DuplicateGroup {
  key: string
  method: string
  confidence: number
  warning: boolean
  members: DuplicateMember[]
  keeper: { content_id: string; reason: string }
}

export interface DuplicateScan {
  groups: DuplicateGroup[]
  scanned: number
  fingerprint: Fingerprint
}

export interface MissingEntry {
  scope: 'library' | 'event' | 'collection'
  /** library/event rows carry an app-DB int id; collection rows reuse content_id */
  id: number | string
  content_id?: string
  title: string | null
  artist: string | null
  status?: string
  file_path?: string | null
  resolved_path?: string | null
  purchase_links: Array<{ store: string; url: string }>
  relink_candidates: Array<{ path: string; score: number; format: string; duration_s?: number }>
}

export interface UntaggedTrack {
  content_id: string
  title: string | null
  artist: string | null
  protected: boolean
  category: 'junk' | 'dup_of_tagged' | 'alt_version' | 'review'
}

export interface SmartFixChange {
  content_id: string
  field: string
  before: string
  after: string
}

export interface SmartFixesDryRun {
  payload: SmartFixChange[]
  skipped_protected: Array<{ content_id: string; name: string }>
  fingerprint: Fingerprint
}

export interface BackupInfo {
  name: string
  files: string[]
  size_bytes: number
}
