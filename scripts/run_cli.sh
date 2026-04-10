#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

cd "$REPO_ROOT"
mkdir -p "$OUTPUT_ROOT"

run_python -m luca_tracker track \
  --video video/sledzenie_plamki.mkv \
  --track_mode brightness \
  --output_csv "$OUTPUT_ROOT/tracking_results.csv" \
  --trajectory_png "$OUTPUT_ROOT/trajectory.png" \
  --report_csv "$OUTPUT_ROOT/report.csv" \
  --report_pdf "$OUTPUT_ROOT/report.pdf"
