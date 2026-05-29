# Setup

## Spotify Developer App

Create a dedicated Spotify Developer app and configure this redirect URI:

```text
http://127.0.0.1:8765/api/spotify/callback
```

Spotify matches redirect URIs exactly. `localhost` and `127.0.0.1` are different values, and a missing path or trailing slash will also fail.

The app uses OAuth PKCE, so no client secret is needed for the desktop client.

Required scopes:

- `playlist-read-private`
- `playlist-modify-private`
- `playlist-modify-public`
- `user-library-read`
- `user-library-modify`

## macOS Dependencies

Node and npm are used by the desktop UI. The Python service uses `uv`.

The service installs `pyrekordbox` and `sqlcipher3-wheels` through `uv`. If the wheel fails on a future machine, install SQLCipher with Homebrew and run `uv sync` again:

```bash
brew install sqlcipher
cd service
uv sync --group dev
```

## Reference Repositories

Download the reference repositories:

```bash
scripts/download-reference-repos.sh
```

They are stored in `.references/` and ignored by Git.
