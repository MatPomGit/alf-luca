#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VIDEO_FILE="$(find /output -maxdepth 1 -type f \( -iname '*.mp4' -o -iname '*.mkv' -o -iname '*.avi' -o -iname '*.mov' -o -iname '*.m4v' -o -iname '*.webm' \) | sort | head -n 1 || true)"
if [[ -z "${VIDEO_FILE}" ]]; then
  echo "[BLAD] Brak plików wideo w /output." >&2
  exit 2
fi

if command -v python3 >/dev/null 2>&1; then
  echo -e "\033[96m[ETAP]\033[0m Start analizy CLI dla: ${VIDEO_FILE}"
  python3 track_luca.py track \
    --video "$VIDEO_FILE" \
    --track_mode brightness
elif command -v python >/dev/null 2>&1; then
  echo -e "\033[96m[ETAP]\033[0m Start analizy CLI dla: ${VIDEO_FILE}"
  python track_luca.py track \
    --video "$VIDEO_FILE" \
    --track_mode brightness
else
  echo "[BLAD] Nie znaleziono interpretera Python (python3/python)." >&2
  exit 127
fi

echo -e "\033[92m[OK]\033[0m Analiza zakończona. Okno zamknie się za 6 sekund."
printf '\a\a'
sleep 6
