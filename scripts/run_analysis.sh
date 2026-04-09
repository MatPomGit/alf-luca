#!/usr/bin/env bash
set -euo pipefail

# Ładujemy współdzielone funkcje uruchomieniowe dla skryptów automatycznych.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

cd "$REPO_ROOT"

# Automatyczne porównanie dwóch pomiarów i zapis wykresów porównawczych.
run_python tools/data.py \
  output/tracking_results.csv \
  output/inny_pomiar.csv \
  --x-col frame \
  --y-cols x y speed \
  --output-dir output/compare_plots
