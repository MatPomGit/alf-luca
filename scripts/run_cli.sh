#!/usr/bin/env bash
set -euo pipefail

# Ładujemy współdzielone funkcje uruchomieniowe dla skryptów automatycznych.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

cd "$REPO_ROOT"

# Domyślny przebieg śledzenia dla środowiska testowego/roboczego.
run_python track_luca.py track \
  --video video/sledzenie_plamki.mkv \
  --track_mode brightness \
  --output_csv tracking_results.csv \
  --trajectory_png trajectory.png \
  --report_csv report.csv \
  --report_pdf report.pdf
