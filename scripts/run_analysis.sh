#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

cd "$REPO_ROOT"
mkdir -p "$OUTPUT_ROOT/compare_plots"

run_python tools/data.py \
  "$OUTPUT_ROOT/tracking_results.csv" \
  "$OUTPUT_ROOT/inny_pomiar.csv" \
  --x-col frame \
  --y-cols x y speed \
  --output-dir "$OUTPUT_ROOT/compare_plots"
