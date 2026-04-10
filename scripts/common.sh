#!/usr/bin/env bash
set -euo pipefail

# Wyznaczamy katalog repozytorium niezależnie od miejsca uruchomienia skryptu.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_ROOT="$REPO_ROOT/output/manual"

run_python() {
  # Skrypty repo zakładają uruchamianie z katalogu checkoutu i wybierają dostępny interpreter.
  if command -v python3 >/dev/null 2>&1; then
    python3 "$@"
    return
  fi
  if command -v python >/dev/null 2>&1; then
    python "$@"
    return
  fi
  echo "[BLAD] Nie znaleziono interpretera Python (python3/python)." >&2
  exit 127
}
