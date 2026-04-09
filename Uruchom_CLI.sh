#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if command -v python3 >/dev/null 2>&1; then
echo -e "\033[96m[ETAP]\033[0m Start analizy CLI..."
python track_luca.py track \
  --video /output/sledzenie_plamki.mkv \
  --track_mode brightness

elif command -v python >/dev/null 2>&1; then
echo -e "\033[96m[ETAP]\033[0m Start analizy CLI..."
python track_luca.py track \
  --video /output/sledzenie_plamki.mkv \
  --track_mode brightness
else
  echo "[BLAD] Nie znaleziono interpretera Python (python3/python)." >&2
  exit 127
fi

echo -e "\033[92m[OK]\033[0m Analiza zakończona. Okno zamknie się za 6 sekund."
printf '\a\a'
sleep 6
