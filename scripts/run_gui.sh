#!/usr/bin/env bash
set -euo pipefail

# Uruchomienie z checkoutu repo; pakiet `luca_tracker` doładowuje workspace `packages/*/src`.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

cd "$REPO_ROOT"

GUI_VIDEO_PATH="${GUI_VIDEO:-}"
GUI_CALIB_PATH="${GUI_CALIB_FILE:-}"

CMD=(-m luca_tracker gui)

if [[ -n "$GUI_VIDEO_PATH" ]]; then
  CMD+=(--video "$GUI_VIDEO_PATH")
fi

if [[ -n "$GUI_CALIB_PATH" ]]; then
  CMD+=(--calib_file "$GUI_CALIB_PATH")
elif [[ -f "$REPO_ROOT/camera_calib.npz" ]]; then
  CMD+=(--calib_file "$REPO_ROOT/camera_calib.npz")
fi

if [[ -z "$GUI_VIDEO_PATH" && ! -d "$REPO_ROOT/video" ]]; then
  echo "[BLAD] Nie znaleziono katalogu video/ ani zmiennej GUI_VIDEO." >&2
  echo "        Ustaw GUI_VIDEO=/sciezka/do/pliku.mp4 albo dodaj plik do katalogu video/." >&2
  exit 1
fi

run_python "${CMD[@]}"
