# Distribution — building, signing, notarizing & auto-update

Syncbox packages the FastAPI service (PyInstaller `--onedir`) as an Electron
app resource and ships it as a macOS bundle. This document covers the three
distribution levels, from a local unsigned build to a signed/notarized,
auto-updating release.

---

## 1. Build outputs

| Command | Output | Use |
|---------|--------|-----|
| `npm run dist` | `release/mac-arm64/Syncbox.app` (unsigned, `--dir`) | Fast local testing |
| `npm run dist:dmg` | `release/Syncbox-<version>-arm64.dmg` | Shareable installer (still unsigned by default) |

Both first run `npm run build` (renderer + main + preload) and
`npm run build:service` (PyInstaller binary into `service/dist/syncbox-service`).

> Requires **Node ≥ 20** — the bundler uses `crypto.hash`.

`build:service` collects, besides the app's own modules, a few packages whose
data PyInstaller can't infer: `pyrekordbox`, `sqlcipher3`, `uvicorn`, `mutagen`,
`pydantic`, and — importantly — **`certifi` / `httpx` / `httpcore`** so the
bundled service ships a CA bundle. Without it every outbound HTTPS call (Spotify
token exchange, Deezer search) fails SSL verification in the packaged app.

The bundled service is spawned by the main process from
`process.resourcesPath/syncbox-service/syncbox-service`; the seed DB is copied
on first launch (see `electron/main.ts`). The Electron main process also
auto-launches (or one-click-installs) **Deemix Remastered** — see
`electron/deemix.ts`.

### Unsigned `.dmg` caveat

Without a Developer ID signature, Gatekeeper quarantines the app. To open an
unsigned build the user must **right-click → Open** once, or run:

```bash
xattr -dr com.apple.quarantine /Applications/Syncbox.app
```

### Publishing an (unsigned) release to GitHub

The current public builds are unsigned and published by hand with the `gh` CLI:

```bash
npm run dist:dmg
gh release create v<version> \
  "release/Syncbox-<version>-arm64.dmg" \
  --repo Adridot/syncbox \
  --title "Syncbox <version>" \
  --notes "…release notes…"
```

The README's **Install** section links to
<https://github.com/Adridot/syncbox/releases>. For a hands-off, signed,
auto-updating feed instead, see §2–§3 below.

---

## 2. Signing & notarization (Developer ID)

Requires an Apple Developer account ($99/yr) and a **Developer ID Application**
certificate in the login keychain.

1. In `package.json` → `build.mac`, replace `"identity": null` with your
   identity (or remove it to auto-detect), and add hardened runtime:

   ```json
   "mac": {
     "target": ["dmg"],
     "category": "public.app-category.music",
     "icon": "build/icon.icns",
     "hardenedRuntime": true,
     "gatekeeperAssess": false,
     "entitlements": "build/entitlements.mac.plist",
     "entitlementsInherit": "build/entitlements.mac.plist"
   }
   ```

   A minimal `build/entitlements.mac.plist` must allow the JIT/unsigned-memory
   needed by the embedded Python runtime:

   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0"><dict>
     <key>com.apple.security.cs.allow-jit</key><true/>
     <key>com.apple.security.cs.allow-unsigned-executable-memory</key><true/>
     <key>com.apple.security.cs.disable-library-validation</key><true/>
   </dict></plist>
   ```

   > `disable-library-validation` is required because the PyInstaller binary
   > loads unsigned `.so` files (sqlcipher3, pyrekordbox, numpy).

2. Notarize. electron-builder ≥25 notarizes automatically when credentials are
   present. Provide an app-specific password via environment:

   ```bash
   export APPLE_ID="you@example.com"
   export APPLE_APP_SPECIFIC_PASSWORD="abcd-efgh-ijkl-mnop"
   export APPLE_TEAM_ID="XXXXXXXXXX"
   npm run dist:dmg
   ```

   electron-builder runs `notarytool submit --wait` and staples the ticket.

3. Verify:

   ```bash
   spctl -a -vvv -t install release/Syncbox-<version>.dmg
   xcrun stapler validate "release/mac/Syncbox.app"
   ```

---

## 3. Auto-update (electron-updater)

Scaffolding is wired in `electron/main.ts` (`checkForUpdates()`) but **dormant**
by default — it only runs when:

- the app is packaged (`app.isPackaged`), **and**
- `RBSYNC_ENABLE_UPDATES=1`, **and**
- a publish provider is configured (so electron-builder emits `app-update.yml`).

To enable a GitHub-releases feed:

1. Set the provider in `package.json` → `build`:

   ```json
   "publish": [{ "provider": "github", "owner": "<you>", "repo": "syncbox" }]
   ```

2. Build & publish a **signed, notarized** release (auto-update refuses
   unsigned updates on macOS):

   ```bash
   GH_TOKEN=<token> npm run dist:dmg -- --publish always
   ```

3. Ship the app with `RBSYNC_ENABLE_UPDATES=1`. On launch the updater checks the
   feed, downloads in the background, and notifies the user to restart.

For a self-hosted feed use `{ "provider": "generic", "url": "https://…" }` and
upload the `latest-mac.yml` + `.dmg`/`.zip` artifacts there.

> macOS auto-update requires a `.zip` target in addition to `.dmg` for the
> differential download. Add `"zip"` to `build.mac.target` when enabling updates.
