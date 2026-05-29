#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="$ROOT_DIR/.references"

mkdir -p "$TARGET_DIR"

clone_or_update() {
  local repo_url="$1"
  local target_name="$2"
  local target_path="$TARGET_DIR/$target_name"

  if [[ -d "$target_path/.git" ]]; then
    git -C "$target_path" fetch --depth 1 origin main
    git -C "$target_path" checkout --quiet FETCH_HEAD
  else
    git clone --depth 1 "$repo_url" "$target_path"
  fi
}

clone_or_update "https://github.com/davehenke/rekordbox-mcp.git" "rekordbox-mcp"
clone_or_update "https://github.com/marcelmarais/spotify-mcp-server.git" "spotify-mcp-server"

echo "Reference repositories are available in $TARGET_DIR"
