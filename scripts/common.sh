#!/usr/bin/env bash
set -euo pipefail

# Wyznaczamy katalog repozytorium niezależnie od miejsca uruchomienia skryptu.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_ROOT="$REPO_ROOT/output/manual"

# Ujednolicone kody zakończenia dla typowych błędów środowiskowych.
readonly LUCA_EXIT_OK=0
readonly LUCA_EXIT_GENERAL_ERROR=1
readonly LUCA_EXIT_ROS2_MISSING=21
readonly LUCA_EXIT_CAMERA_MISSING=22
readonly LUCA_EXIT_PNP_MISSING=23
readonly LUCA_EXIT_GUI_BACKEND_MISSING=24
readonly LUCA_EXIT_PYTHON_MISSING=127

log_info() {
  echo "[LUCA][INFO] $*" >&2
}

log_error() {
  echo "[LUCA][ERROR] $*" >&2
}

# Jednolity log startowy dla wszystkich launcherów.
log_start() {
  local mode="$1"
  shift || true
  echo "[LUCA][START] mode=${mode} cwd=${REPO_ROOT} $*" >&2
}

# Jednolity log końcowy dla wszystkich launcherów.
log_finish() {
  local mode="$1"
  local exit_code="$2"
  echo "[LUCA][END] mode=${mode} exit_code=${exit_code}" >&2
}

# Ustandaryzowane wyjście z logiem końcowym.
finish_with_code() {
  local mode="$1"
  local exit_code="$2"
  log_finish "$mode" "$exit_code"
  exit "$exit_code"
}

# Skrypty repo zakładają uruchamianie z katalogu checkoutu i wybierają dostępny interpreter.
run_python() {
  if command -v python3 >/dev/null 2>&1; then
    python3 "$@"
    return
  fi
  if command -v python >/dev/null 2>&1; then
    python "$@"
    return
  fi
  log_error "Nie znaleziono interpretera Python (python3/python)."
  exit "$LUCA_EXIT_PYTHON_MISSING"
}

# Diagnostyka: brak runtime ROS2 (`rclpy`).
require_ros2_runtime() {
  if run_python -c 'import rclpy' >/dev/null 2>&1; then
    return
  fi
  log_error "Brak ROS2 runtime (modul rclpy)."
  log_error "Doinstaluj ROS2/rclpy i zaladuj setup (np. /opt/ros/<distro>/setup.bash)."
  return "$LUCA_EXIT_ROS2_MISSING"
}

# Diagnostyka: brak dostępu do wybranej kamery.
require_camera_access() {
  local camera_index="$1"
  if run_python - "$camera_index" <<'PY' >/dev/null 2>&1
import cv2
import sys

idx = int(sys.argv[1])
cap = cv2.VideoCapture(idx)
ok = bool(cap.isOpened())
cap.release()
sys.exit(0 if ok else 1)
PY
  then
    return
  fi
  log_error "Brak dostepu do kamery (index=${camera_index})."
  log_error "Sprawdz uprawnienia, numer kamery i czy urzadzenie nie jest zajete."
  return "$LUCA_EXIT_CAMERA_MISSING"
}

# Diagnostyka: brak backendu GUI (Kivy).
require_gui_backend() {
  if run_python -c 'import kivy' >/dev/null 2>&1; then
    return
  fi
  log_error "Brak backendu GUI (Kivy)."
  log_error "Doinstaluj zaleznosci GUI i sprawdz dostepnosc serwera wyswietlania."
  return "$LUCA_EXIT_GUI_BACKEND_MISSING"
}
