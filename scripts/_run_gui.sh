#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if command -v python3 >/dev/null 2>&1; then
  python3 track_luca.py gui
elif command -v python >/dev/null 2>&1; then
  python track_luca.py gui
else
  echo "[BLAD] Nie znaleziono interpretera Python (python3/python)." >&2
  exit 127
fi
