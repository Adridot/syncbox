/* Client-side Spotify id extraction (SPEC-DESIGN §6: AddSourceModal /
   AddTrackByLink resolve a pasted link before following). Spotify-only in
   v1 — Deezer/SoundCloud link parsing is deprecated (M4-PLAN §6). */

const ID = '[0-9A-Za-z]{22}'
const PLAYLIST = new RegExp(`playlist[/:](${ID})`)
const TRACK = new RegExp(`track[/:](${ID})`)
const BARE = new RegExp(`^(${ID})$`)

export function extractPlaylistId(input: string): string | null {
  const trimmed = input.trim()
  return PLAYLIST.exec(trimmed)?.[1] ?? BARE.exec(trimmed)?.[1] ?? null
}

export function extractTrackId(input: string): string | null {
  const trimmed = input.trim()
  return TRACK.exec(trimmed)?.[1] ?? BARE.exec(trimmed)?.[1] ?? null
}
