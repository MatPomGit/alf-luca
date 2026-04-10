#!/usr/bin/env bash
set -euo pipefail

# Ładujemy współdzielone funkcje uruchomieniowe dla skryptów automatycznych.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

cd "$REPO_ROOT"

# Start GUI bez dodatkowych parametrów; domyślny wybór pliku jest po stronie CLI.
run_python -m luca_tracker gui
