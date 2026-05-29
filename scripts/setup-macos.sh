#!/usr/bin/env bash
set -euo pipefail

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required for SQLCipher setup on macOS." >&2
  exit 1
fi

if ! brew list --versions sqlcipher >/dev/null 2>&1; then
  brew install sqlcipher
fi

npm install
(cd service && uv sync --group dev)

echo "Base development dependencies are ready."
