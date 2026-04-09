#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if command -v python3 >/dev/null 2>&1; then

python track_luca.py track \
  --video video/sledzenie_plamki.mkv \
  --track_mode brightness \
  --output_csv sledzenie_plamki_measurement_track.csv \
  --trajectory_png sledzenie_plamki_measurement_trajectory.png \
  --report_csv sledzenie_plamki_measurement_metrics.csv \
  --report_pdf sledzenie_plamki_measurement_report.pdf

elif command -v python >/dev/null 2>&1; then
python track_luca.py track \
  --video video/sledzenie_plamki.mkv \
  --track_mode brightness \
  --output_csv sledzenie_plamki_measurement_track.csv \
  --trajectory_png sledzenie_plamki_measurement_trajectory.png \
  --report_csv sledzenie_plamki_measurement_metrics.csv \
  --report_pdf sledzenie_plamki_measurement_report.pdf
else
  echo "[BLAD] Nie znaleziono interpretera Python (python3/python)." >&2
  exit 127
fi
