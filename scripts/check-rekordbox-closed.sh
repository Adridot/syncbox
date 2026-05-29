#!/usr/bin/env bash
set -euo pipefail

if pgrep -fl "rekordbox|rekordboxAgent" >/tmp/rekordbox-sync-processes.txt; then
  echo "Rekordbox is running. Close Rekordbox before mutations."
  cat /tmp/rekordbox-sync-processes.txt
  exit 1
fi

echo "Rekordbox is closed."
