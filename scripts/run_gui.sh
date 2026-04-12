#!/usr/bin/env bash
set -euo pipefail

# Uruchomienie z checkoutu repo; pakiet `luca_tracker` doładowuje workspace `packages/*/src`.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

MODE="gui"
cd "$REPO_ROOT"

GUI_VIDEO_PATH="${GUI_VIDEO:-}"
GUI_CALIB_PATH="${GUI_CALIB_FILE:-}"

log_start "$MODE" "video=${GUI_VIDEO_PATH:-auto}"

if ! require_gui_backend; then
  finish_with_code "$MODE" "$LUCA_EXIT_GUI_BACKEND_MISSING"
fi

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
  log_error "Nie znaleziono katalogu video/ ani zmiennej GUI_VIDEO."
  log_error "Ustaw GUI_VIDEO=/sciezka/do/pliku.mp4 albo dodaj plik do katalogu video/."
  finish_with_code "$MODE" "$LUCA_EXIT_GENERAL_ERROR"
fi

set +e
run_python "${CMD[@]}"
EXIT_CODE=$?
set -e
finish_with_code "$MODE" "$EXIT_CODE"
