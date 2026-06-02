# User Guide

Day-to-day use of Syncbox. For architecture and developer details see the
[README](../README.md); for packaging see [DISTRIBUTION.md](DISTRIBUTION.md).

## First run

1. **Install Syncbox** (`.dmg` from Releases → drag to Applications;
   right-click → Open the first time, it's unsigned).
2. **Connect Spotify** — Settings → paste your **Client ID**, click **Connect
   Spotify**, approve in the browser. Add this exact redirect URI in the
   [Spotify Developer Dashboard](https://developer.spotify.com/dashboard):

   ```text
   http://127.0.0.1:8765/api/spotify/callback
   ```

3. **Set up the downloader** — Settings → *Deemix downloader*. If Deemix
   Remastered isn't installed, click **Install Deemix**; otherwise Syncbox
   launches it automatically. Paste your Deezer **ARL** into Deemix once.
4. **Check the paths** — Settings: Rekordbox database directory, storage root,
   and your permanent / manual-collection folders. Save (the managed folders are
   created automatically).
5. **Run the Doctor** (sidebar → Doctor) to confirm everything is green.

## The write lock

Any change to your Rekordbox database requires **Rekordbox (and
`rekordboxAgent`) to be closed**. While Rekordbox is open, Syncbox shows a write
lock and read-only features still work, but Apply / Delete / Resolve / Re-link
are blocked. `rekordboxAgent` keeps running in the background after you close the
Rekordbox window — quit it from the menu bar if a write is still blocked.

## Screens

### Dashboard
Status at a glance: permanent playlists, events, pending proposals, active
downloads, and the health of the Local API / Rekordbox / Deemix.

### My Library
Your **permanent** Spotify sources.
1. Add a source (a Spotify playlist) and give it **tag rules** (the MyTags its
   tracks should get).
2. **Analyze** → each track is matched against your Rekordbox collection.
3. For missing tracks, **Search Deezer**, preview, and **Download**.
4. When the file lands the track becomes **ready**; **Apply** (Rekordbox closed)
   adds + tags it.
5. Later re-syncs surface removed tracks as *proposals* — never auto-applied.

### Events
A **temporary** import (a wedding, a party).
1. Create the event from a Spotify playlist and pick its **event tag**.
2. Match / stage tracks (download or assign existing files).
3. **Apply** → tags every track and builds a smart playlist under *Event
   Imports*.
4. **Delete event** afterwards → removes the tag, the smart playlist, and tracks
   that *only* belonged to this event; its on-disk folder (audio included) is
   deleted. Anything in your permanent/manual collection is always kept.

### Live import
For use **while Rekordbox is open**: generates an `.m3u8` you import with
`File > Import > Import Playlist`. No database write.

### Download & Match
Every download job in one place — from My Library, Events, and missing-file
re-downloads — with live progress, plus tools to match a finished download to
the track that asked for it.

### Duplicates
Find duplicate tracks Rekordbox's native tool misses.
1. **Scan collection** (choose ISRC / fuzzy and the similarity threshold).
2. Each group shows a suggested **keeper** (best quality / most cues / permanent
   copy) — change it with the radio button if you disagree.
3. **Keep selected** removes the others (their playlist & tag memberships move to
   the keeper). Tick *Delete files* to also remove the loser's audio (never for
   protected/permanent files). **Not a duplicate** dismisses a group for good.
4. *Auto-resolve N ISRC groups* handles the high-confidence ones in one click.
   Groups flagged *"same ISRC but titles differ"* are excluded — review those by
   hand.

### Missing Files
Collection entries whose audio file is gone.
- **Re-download** — queues a download (watch it in Download & Match) that
  re-links the entry when done (Rekordbox closed).
- **Re-link** — pick a moved/renamed file already on disk.
- **Remove** — drop an orphaned entry (e.g. `spotify:track:` junk).

### Doctor
Health checks + your safety net:
- **Diagnostics** for Rekordbox DB, storage, disk space, Deemix, Spotify, backups.
- **Backups** — every change makes one automatically; here you can **Restore** a
  previous state, set how many to **keep** (rotation), and **clean up** old ones.
- **Open Logs**.

> Running the dev build from a terminal, the backups folder may show as
> *unreadable* (macOS blocks listing cloud-storage folders from a terminal
> process). The packaged app lists them normally.

### Settings
- **Spotify** — Client ID, redirect URI, Connect.
- **Deemix downloader** — install / launch status.
- **Rekordbox & storage** — database directory, storage root, permanent &
  manual-collection folders. *Storage locations* shows where downloads land.
- **Backup & Restore** — see below.

## Backup & restore

Settings already survive app updates (they live in *Application Support*).
**Backup & Restore** (Settings) makes them portable for a clean reinstall or a
new Mac:

- **Settings only** → a small `.json` (paths, Spotify client id + tokens,
  retention). Export/Import.
- **All data** → the whole app database (sources, events, tag rules, mappings +
  settings). Export downloads a `.sqlite3`; Restore replaces your data after a
  confirmation and makes a safety backup first.

## Managed storage

Syncbox keeps downloads under your storage root:

```text
<storageRoot>/
  rekordbox/
    Collection/            # canonical permanent collection (permanentPath)
    Collection manuelle/   # manual collection (manualCollectionPath), protected
  _rekordbox_sync/
    inbox/
    events/
    backups/
```

Tracks in the permanent and manual collections are **protected** — never
auto-deleted, and re-downloads land there with clean names.

> Syncbox never *moves* audio files (macOS TCC blocks file operations on Dropbox
> CloudStorage from the service). Apply references each downloaded file where it
> is; consolidating into `rekordbox/Collection` is a separate, explicit step via
> `service/scripts/migrate_collection.py`.
