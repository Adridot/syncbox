/* Client-side Spotify id extraction (Spotify-only — §11.1; Deezer/SoundCloud
   halves of the mockup placeholders are deprecated and not parsed). */

const ID = '([0-9A-Za-z]{22})'

function extract(kind: 'playlist' | 'track', input: string): string | null {
  const raw = input.trim()
  if (!raw) return null
  const patterns = [
    new RegExp(`open\\.spotify\\.com/(?:[a-z-]+/)?${kind}/${ID}`),
    new RegExp(`spotify:${kind}:${ID}`),
    new RegExp(`^${ID}$`),
  ]
  for (const pattern of patterns) {
    const match = raw.match(pattern)
    if (match) return match[1]
  }
  return null
}

export const extractPlaylistId = (input: string) => extract('playlist', input)
export const extractTrackId = (input: string) => extract('track', input)

export function spotifyUrl(kind: 'playlist' | 'track', id: string): string {
  const valid = extract(kind, id)
  if (!valid) throw new Error(`invalid Spotify ${kind} id`)
  return `https://open.spotify.com/${kind}/${valid}`
}

/** Deep-link for the installed Spotify desktop app (scheme handler). */
export function spotifyAppUri(kind: 'playlist' | 'track', id: string): string {
  const valid = extract(kind, id)
  if (!valid) throw new Error(`invalid Spotify ${kind} id`)
  return `spotify:${kind}:${valid}`
}
