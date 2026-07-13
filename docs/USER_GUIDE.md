# User Guide

Syncbox 0.2.1 supports macOS 14 or later on Apple Silicon. It is an ad-hoc
signed local application with no Developer ID signature, notarization, or
automatic updater.

## Install and first launch

1. Unzip `Syncbox-0.2.1-macos-arm64.zip` and move `Syncbox.app` to
   Applications if desired.
2. Right-click `Syncbox.app`, choose **Open**, then confirm **Open**. If macOS
   still blocks the locally obtained build, remove quarantine explicitly:

   ```sh
   xattr -dr com.apple.quarantine /path/to/Syncbox.app
   ```

3. In onboarding, select the Rekordbox `master.db` file and a storage root.
   The usual Rekordbox path is
   `~/Library/Pioneer/rekordbox/master.db`. Syncbox validates both paths before
   showing them as ready.
4. Spotify is optional. To enable playlist features, create a Spotify
   developer application, enter its public Client ID in Settings, and register
   this exact redirect URI:

   ```text
   http://127.0.0.1:8765/callback
   ```

   Choose **Connect Spotify**. Authorization opens in the system browser and
   returns to the local Syncbox callback. Syncbox uses read-only playlist
   scopes and PKCE; it does not ask for a Spotify password or client secret.

Application state is stored under
`~/Library/Application Support/Syncbox`. OAuth tokens live in a separate
encrypted SQLCipher secret store protected by an owner-only per-install key.
Syncbox does not use Keychain in this unsigned release.

## Rekordbox write safety

Reading and previewing are separate from mutation. Before a Rekordbox database
write, Syncbox requires Rekordbox and `rekordboxAgent` to be closed, creates a
timestamped backup, revalidates the exact preview, and rejects stale database
state. Database deletions are soft deletes. Owned audio deletion uses the
macOS Trash first and requires explicit consent if an irreversible fallback is
the only available option.

Audio ownership is explicit:

- `app_managed`: working files under `<storage root>/_syncbox/`;
- `permanent_library`: files under `<storage root>/rekordbox/`;
- `external`: every other location.

Syncbox does not treat all files under one generic "protected" flag, and it
does not move or rename ordinary library audio as a background action.

## Main screens

### Dashboard

The Dashboard summarizes configuration, Rekordbox status, followed sources,
events, review work, backups, and current jobs. The activity list is fed by the
local SSE connection. If the backend cannot recover after bounded restarts, an
overlay explains that the backend is unavailable and offers a manual restart.

### Library

Add a Spotify playlist as a source, synchronize it, review ISRC/fuzzy matches,
assign MyTags, and apply selected matches while Rekordbox is closed. Removed or
ambiguous tracks remain review items; Syncbox does not silently apply them.

Tracks missing from the owned collection are handled through the Missing
center. Beatport and Bandcamp searches remain the primary path and open in the
system browser. Syncbox can also use a separately distributed optional Deezer
component after explicit setup; it is disabled by default and never required
for the base application.

### Events

Create an event from a Spotify playlist or as a manual event, review its
matches, add individual Spotify track links, and claim lawfully obtained files
from the event staging folder. Applying creates or updates the event MyTag and
smart playlist. Re-applying handles only the pending delta.

Event deletion always presents an exact preview. A retained staging track with
other active MyTags is migrated to
`<storage root>/rekordbox/Collection/` while preserving its Rekordbox content
identity and memberships. Already-permanent files stay in place. Event-only
managed files follow the guarded delete path.

### Collection Health

The Health hub contains five tabs:

- **Duplicates**: review proposed duplicate groups and choose the keeper;
- **Missing**: repair missing Rekordbox file references;
- **Untagged**: review structurally untagged or suspicious entries;
- **Smart Fixes**: preview conservative metadata corrections before applying;
- **Backups**: inspect, rotate, and restore guarded Rekordbox backups.

Audio-quality diagnostics are local and read-only. An uncertain spectral
cutoff is keeper-neutral; it is not presented as proof of a lossy transcode.

### Missing

The Missing center separates library, event, and Rekordbox-collection scopes.
For a missing acquisition, open a Beatport or Bandcamp search and buy from the
artist/store, then place or select the file you lawfully own and relink it.
Store results are searches, not guaranteed exact matches; verify artist,
title, version, and duration before buying.

For optional Deezer acquisition:

1. Enable it in Settings.
2. Save a valid Premium credential. The value is sent only to the local
   sidecar, stored in the encrypted secret database, and immediately cleared
   from the input field.
3. Install the matching component. Syncbox downloads the versioned macOS arm64
   archive from the GitHub Release, verifies its exact byte size and SHA-256,
   extracts it into app data, and runs its self-check before marking it ready.
4. Start acquisition explicitly from a missing track with a valid ISRC.

The component is Deezer-only at the Syncbox interface. It does not expose
SoundCloud or invoke ffmpeg. Each job passes the credential through an
owner-only one-shot file, never as a command-line value. Purchase links remain
available even when the component is absent or disabled. Only acquire music
when your account and local law authorize it.

### Settings

Settings contains the Spotify Client ID and connection flow, optional Deezer
enablement and component controls, Rekordbox and storage paths, backup
retention, language, matching controls, and transfer tools. Secret fields are
write-only: the UI receives only a boolean indicating whether a value exists.
Blank credential updates preserve an existing value.

**Settings export** creates JSON containing portable non-secret settings.
**All-data export** creates one coherent Syncbox SQLite snapshot. Neither
format contains OAuth tokens or the Deezer credential. All-data import
validates and migrates a staged copy before atomically replacing current data
and keeps a safety backup of the previous database.

## Managed storage

With `<storage root>` configured, Syncbox derives:

```text
<storage root>/
  rekordbox/                 permanent-library ownership
    Collection/              retained event tracks migrated here
  _syncbox/
    inbox/                   app-managed incoming work
    events/                  app-managed event staging
    backups/                 Rekordbox database backups
```

Back up your music library independently. Syncbox database backups protect
Rekordbox metadata; they are not copies of your audio files.

## Current release limits

- Apple Silicon and macOS 14+ only;
- no Developer ID, notarization, Keychain, Windows build, or auto-update;
- the base app contains no streamrip component and works without it;
- optional Deezer acquisition requires the matching GitHub Release asset,
  explicit enablement, a Premium credential, and an ISRC;
- no SoundCloud interface or ffmpeg support;
- private real-Rekordbox fixture gates remain prerequisites for a public
  release claim covering all database mutations.
