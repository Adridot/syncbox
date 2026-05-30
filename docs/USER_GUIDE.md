# User Guide

## Current V2 Workflow

Syncbox now supports the first end-to-end event import workflow: Spotify playlist analysis, Rekordbox matching, manual file staging, and guarded Rekordbox application while Rekordbox is closed.

## Main Screens

### Overview

Shows the local API status, the active Rekordbox database path, and whether Rekordbox mutations are allowed.

If Rekordbox is open, the app shows `Write lock active`. This is expected. Any write to the Rekordbox database must wait until Rekordbox and `rekordboxAgent` are closed.

### Imports

Use this screen to prepare an event import.

1. Connect Spotify from Settings.
2. Click `Load Spotify Playlists`.
3. Select a playlist from the list.
4. Set or adjust the event name.
5. Click `Analyze Import`.

Analysis creates an event review with matched, missing, ambiguous, ignored, and ready tracks.

### Live Rekordbox Import

Use this flow while Rekordbox is open.

1. Set the event name in Imports.
2. Click `Prepare Folder`.
3. Drop local audio files into the generated `audio` folder.
4. Click `Prepare Folder` again to refresh the `.m3u8` playlist.
5. In Rekordbox, import the generated `.m3u8` file with `File > Import > Import Playlist`.

This flow does not write to `master.db`. It creates a Rekordbox-compatible playlist file that Rekordbox imports itself. My Tags and direct Rekordbox database updates remain part of the closed-app sync flow.

### Review

Use this screen to work through an event review.

1. Open an analyzed event.
2. Drop missing files into the event audio folder.
3. Click `Scan Staging`.
4. Mark tracks as permanent when they should become part of the long-term collection.
5. Add existing MyTags as comma-separated values.
6. Close Rekordbox.
7. Click `Apply to Rekordbox`.

Applying an event creates a database backup, imports staged files, applies the event MyTag, and creates a smart playlist based on that event MyTag. Existing business MyTags must already exist in Rekordbox. The event MyTag is the only MyTag the app may create automatically.

Shows proposed actions such as:

- Add a missing Spotify track to Rekordbox.
- Manually match an ambiguous track.
- Protect a manual collection track.
- Propose a deletion without applying it automatically.

No destructive action is automatic.

### Tag Rules

Maps a Spotify source playlist to default Rekordbox tags. Event imports always use the event name as the first default tag; tag rules add extra default tags.

The tag-to-Spotify mapping section links existing Rekordbox MyTags to Spotify playlists. Permanent tracks are added to mapped Spotify playlists after event application.

### Settings

Stores:

- Spotify Client ID.
- Spotify redirect URI.
- Rekordbox database directory.
- Dropbox storage root.

The redirect URI must exactly match the value configured in the Spotify Developer Dashboard.

## Spotify Setup

Add this exact redirect URI in the Spotify Developer Dashboard:

```text
http://127.0.0.1:8765/api/spotify/callback
```

Then paste the Client ID into Settings and click `Connect Spotify`.

## Managed Storage

The app creates this structure under the configured Dropbox music root:

```text
Jockey Tricolore/Musique/
  rekordbox/
    Collection/            # canonical permanent collection (permanentPath)
    Collection manuelle/   # manual collection (manualCollectionPath), protected
  _rekordbox_sync/
    inbox/
    events/
    backups/
```

Tracks in the manual collection are protected from automatic deletion proposals.

> **Note:** Syncbox never *moves* audio files (macOS TCC blocks file operations
> on Dropbox CloudStorage from the service). Apply references each downloaded
> file where it already is; consolidating files into `rekordbox/Collection` is a
> separate, explicit step run via `service/scripts/migrate_collection.py`.
