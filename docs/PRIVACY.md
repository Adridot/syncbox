# Syncbox Provider Data and Privacy

Includes the event link-import change under development for Syncbox 0.8.0.

Syncbox is a local, single-user macOS application. It has no Syncbox cloud backend and does not create a Syncbox account.

## Spotify authorization

Syncbox uses Spotify Authorization Code with PKCE and the exact loopback callback `http://127.0.0.1:8765/callback`. The callback listener exists only during an authorization attempt; the permanent local API/SSE service uses port 8766. You provide your own Spotify Client ID. Syncbox never requests, stores, or uses a Spotify Client Secret.

The requested scopes are limited to `playlist-read-private` and `playlist-read-collaborative`. Authorization opens in the system browser. Access and refresh tokens are stored in the local encrypted secrets database and are excluded from settings exports, data exports, logs, source code, screenshots, fixtures, and command-line arguments.

Spotify Development Mode requires the application owner to maintain an active Spotify Premium subscription and limits the application to five allowlisted authenticated users. Spotify access tokens normally last one hour. For applications subject to Spotify's June 2026 rules, a refresh token expires six months after the initial authorization and refreshes do not extend that deadline. When Spotify reports an expired, revoked, or otherwise invalid refresh token, Syncbox deletes the local session and requires a new browser authorization instead of retrying the rejected token.

## Data used and local storage

Syncbox requests playlists available to the authorized user and the track metadata needed for read-only library synchronization: Spotify playlist and track identifiers, playlist names and artwork, owner display names, track titles, artists, durations, and ISRCs. Syncbox stores followed playlists, their synchronization state, and selected event metadata in its local application database.

The local performance history reads the play history already present in the local Rekordbox database. When that history contains tracks streamed from Spotify inside Rekordbox, Syncbox uses the Spotify track identifiers stored there by Rekordbox to request only those tracks' titles and artists from the Spotify Web API, and keeps them in the local application database. When no Spotify session is connected, Syncbox may instead query Spotify's public anonymous oEmbed endpoint with those track identifiers to obtain the track titles only; no account data is involved. Syncbox never reads Spotify listening activity from the Spotify account itself.

The optional Deezer acquisition component is separately installed, disabled by default, and uses its own one-shot local credential. When the user explicitly requests acquisition for a missing Spotify-derived track, Syncbox sends that track's ISRC to Deezer's public lookup endpoint and passes the resulting Deezer track identifier to the local optional component. Spotify access and refresh tokens are never sent to Deezer or to that component. The owner has chosen to retain this Spotify-to-Deezer matching workflow despite the documented Spotify Developer Policy risk; Syncbox does not claim that workflow is policy-compliant.

## Event link imports

When you submit a supported music link, Syncbox requests the provider's public
metadata, or uses your connected Spotify account for Spotify collections. It
stores the canonical provider/item identifiers, source collection and positions,
selected track metadata, preview status, selection and committed result in the
local application database. Preview and confirmation do not request audio.
Provider responses may disclose unavailable entries; inaccessible collections
are reported as errors rather than empty successful imports.

The separately enabled web-audio component contacts YouTube/YouTube Music or
SoundCloud and their approved delivery hosts only for requested metadata or
audio operations. It does not receive Spotify tokens or Deezer credentials,
read browser cookies or log into those services. Direct Deezer links use their
own exact item ID with the existing optional Deezer component. Acquisition
records retain source identity, measured output properties and file hashes for
recovery and integrity. Explicit local-file selection records a path and hash.
Disabling a component leaves these local operational records intact. Deleting
an event removes its preview snapshots; normal event file-ownership rules apply.
The web-audio release is currently gated on a complete dependency notice bundle.

## Disconnect and deletion

Use **Settings → Spotify → Disconnect** at any time. Syncbox immediately deletes its stored Spotify access and refresh tokens and cancels any pending PKCE exchange. It also deletes followed Spotify sources, their local track rows and synchronization history, deletes Spotify-related library/event acquisition job history and Spotify preview snapshots, and replaces Spotify identifiers on retained local events with local identifiers.

Local event titles and operational track metadata already incorporated into an event are preserved so the user can safely manage the corresponding local Rekordbox lifecycle. The Spotify Client ID, local Rekordbox database, local audio and analysis files, manual collection records, collection-only acquisition history, and direct-source event imports/acquisition history are not changed. Disconnect never opens or writes the Rekordbox database.

You can also revoke Syncbox from the Spotify account applications page. Revocation makes the next refresh fail closed and clears the stored local Spotify session; use Syncbox's Disconnect action as well to remove the local playlist relationships described above.

## Network access

When Spotify is connected, Syncbox communicates directly with Spotify's authorization and Web API HTTPS endpoints. The system browser may open Spotify, purchase-store, project-documentation, or optional-component links only after an explicit user action. Optional Deezer or web-audio network access occurs only after its feature is separately enabled and invoked. Deezer catalogue metadata for an explicitly submitted event link does not require acquisition enablement.

## Contact

Questions or deletion problems can be reported through the [Syncbox issue tracker](https://github.com/Adridot/syncbox/issues).

## Material sources

- [Spotify Developer Policy](https://developer.spotify.com/policy)
- [Spotify Authorization Code with PKCE](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow)
- [Spotify redirect URI requirements](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri)
- [Spotify February 2026 Development Mode migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide)
- [Spotify quota modes](https://developer.spotify.com/documentation/web-api/concepts/quota-modes)
- [Spotify refresh-token expiration announcement](https://developer.spotify.com/blog/2026-06-18-refresh-token-expiration)
- [Spotify refresh-token flow](https://developer.spotify.com/documentation/web-api/tutorials/refreshing-tokens)
- [Spotify Developer Terms](https://developer.spotify.com/terms)
