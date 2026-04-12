#!/usr/bin/env bash
set -euo pipefail

# Uruchomienie z checkoutu repo; pakiet `luca_tracker` doładowuje workspace `packages/*/src`.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

MODE="cli_track"
cd "$REPO_ROOT"
mkdir -p "$OUTPUT_ROOT"
log_start "$MODE" "video=video/sledzenie_plamki.mkv"

CMD=(
  -m luca_tracker track
  --video video/sledzenie_plamki.mkv
  --track_mode brightness
  --threshold_mode adaptive
  --adaptive_block_size 31
  --output_csv "$OUTPUT_ROOT/tracking_results.csv"
  --trajectory_png "$OUTPUT_ROOT/trajectory.png"
  --report_csv "$OUTPUT_ROOT/report.csv"
  --report_pdf "$OUTPUT_ROOT/report.pdf"
)

if [[ -f "$REPO_ROOT/camera_calib.npz" ]]; then
  CMD+=(--calib_file "$REPO_ROOT/camera_calib.npz")
fi

set +e
run_python "${CMD[@]}"
EXIT_CODE=$?
set -e
finish_with_code "$MODE" "$EXIT_CODE"
