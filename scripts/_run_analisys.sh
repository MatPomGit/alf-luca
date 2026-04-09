#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if command -v python3 >/dev/null 2>&1; then

python tools/data.py \
  output/tracking_results.csv \
  output/inny_pomiar.csv \
  --x-col frame \
  --y-cols x y speed \
  --output-dir output/compare_plots

elif command -v python >/dev/null 2>&1; then

python tools/data.py \
  output/tracking_results.csv \
  output/inny_pomiar.csv \
  --x-col frame \
  --y-cols x y speed \
  --output-dir output/compare_plots

else
  echo "[BLAD] Nie znaleziono interpretera Python (python3/python)." >&2
  exit 127
fi
