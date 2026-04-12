#!/usr/bin/env bash
set -euo pipefail

# Uruchomienie z checkoutu repo; pakiet `luca_tracker` doładowuje workspace `packages/*/src`.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

MODE="ros2_camera_xyz"
cd "$REPO_ROOT"

ROS2_SETUP_FILE="${LUCA_ROS2_SETUP_FILE:-}"
ROS2_OVERLAY_SETUP_FILE="${LUCA_ROS2_OVERLAY_SETUP_FILE:-}"

if [[ -n "$ROS2_SETUP_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ROS2_SETUP_FILE"
elif [[ -n "${ROS_DISTRO:-}" && -f "/opt/ros/$ROS_DISTRO/setup.bash" ]]; then
  # shellcheck disable=SC1091
  source "/opt/ros/$ROS_DISTRO/setup.bash"
fi

if [[ -n "$ROS2_OVERLAY_SETUP_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ROS2_OVERLAY_SETUP_FILE"
fi

CAMERA_INDEX="${LUCA_CAMERA_INDEX:-0}"
NODE_NAME="${LUCA_ROS2_NODE_NAME:-detector_node}"
TOPIC_NAME="${LUCA_ROS2_TOPIC:-/luca_tracker/tracking}"
MESSAGE_SCHEMA="${LUCA_ROS2_MESSAGE_SCHEMA:-luca_tracker.ros2.tracking.v1}"
FPS_VALUE="${LUCA_ROS2_FPS:-30}"
FRAME_WIDTH_VALUE="${LUCA_ROS2_FRAME_WIDTH:-0}"
FRAME_HEIGHT_VALUE="${LUCA_ROS2_FRAME_HEIGHT:-0}"
CALIB_FILE_PATH="${LUCA_CALIB_FILE:-$REPO_ROOT/camera_calib.npz}"
CALIB_DIR_PATH="${LUCA_CALIB_DIR:-$REPO_ROOT/images_calib}"
CHESSBOARD_ROWS_VALUE="${LUCA_CHESSBOARD_ROWS:-7}"
CHESSBOARD_COLS_VALUE="${LUCA_CHESSBOARD_COLS:-10}"
CHESSBOARD_SQUARE_SIZE_VALUE="${LUCA_CHESSBOARD_SQUARE_SIZE:-1.0}"
PNP_OBJECT_POINTS_VALUE="${LUCA_PNP_OBJECT_POINTS:-}"
PNP_IMAGE_POINTS_VALUE="${LUCA_PNP_IMAGE_POINTS:-}"
PNP_WORLD_PLANE_Z_VALUE="${LUCA_PNP_WORLD_PLANE_Z:-0.0}"
THRESHOLD_MODE_VALUE="${LUCA_THRESHOLD_MODE:-adaptive}"
THRESHOLD_VALUE="${LUCA_THRESHOLD:-200}"
ADAPTIVE_BLOCK_SIZE_VALUE="${LUCA_ADAPTIVE_BLOCK_SIZE:-31}"
ADAPTIVE_C_VALUE="${LUCA_ADAPTIVE_C:-5.0}"
BLUR_VALUE="${LUCA_BLUR:-11}"
MIN_AREA_VALUE="${LUCA_MIN_AREA:-10.0}"
MAX_AREA_VALUE="${LUCA_MAX_AREA:-0.0}"
ERODE_ITER_VALUE="${LUCA_ERODE_ITER:-2}"
DILATE_ITER_VALUE="${LUCA_DILATE_ITER:-4}"
ROI_VALUE="${LUCA_ROI:-}"
DISPLAY_ENABLED="${LUCA_DISPLAY:-1}"

log_start "$MODE" "camera_index=$CAMERA_INDEX topic=$TOPIC_NAME node=$NODE_NAME"

if ! require_ros2_runtime; then
  finish_with_code "$MODE" "$LUCA_EXIT_ROS2_MISSING"
fi

if ! require_camera_access "$CAMERA_INDEX"; then
  finish_with_code "$MODE" "$LUCA_EXIT_CAMERA_MISSING"
fi

if [[ ! -f "$CALIB_FILE_PATH" ]]; then
  log_error "Nie znaleziono pliku kalibracji: $CALIB_FILE_PATH"
  log_error "Ustaw LUCA_CALIB_FILE albo wygeneruj camera_calib.npz w katalogu repo."
  finish_with_code "$MODE" "$LUCA_EXIT_GENERAL_ERROR"
fi

if [[ -z "$PNP_OBJECT_POINTS_VALUE" || -z "$PNP_IMAGE_POINTS_VALUE" ]]; then
  log_info "Brak jawnych referencji PnP. Probuje wyliczyc je z: $CALIB_DIR_PATH"
  computed_env="$(run_python scripts/compute_pnp_reference.py --format shell --calib-dir "$CALIB_DIR_PATH" --rows "$CHESSBOARD_ROWS_VALUE" --cols "$CHESSBOARD_COLS_VALUE" --square-size "$CHESSBOARD_SQUARE_SIZE_VALUE")" || {
    log_error "Nie udalo sie automatycznie wyliczyc referencji PnP."
    log_error "Ustaw LUCA_PNP_OBJECT_POINTS i LUCA_PNP_IMAGE_POINTS albo popraw dane w images_calib/."
    finish_with_code "$MODE" "$LUCA_EXIT_PNP_MISSING"
  }
  eval "$computed_env"
  PNP_OBJECT_POINTS_VALUE="${LUCA_PNP_OBJECT_POINTS:-}"
  PNP_IMAGE_POINTS_VALUE="${LUCA_PNP_IMAGE_POINTS:-}"
  if [[ -n "$PNP_OBJECT_POINTS_VALUE" && -n "$PNP_IMAGE_POINTS_VALUE" ]]; then
    log_info "Auto-derywacja PnP zakonczona powodzeniem (kalibracja banan-ready)."
  else
    log_error "Auto-derywacja PnP zwrocila niepelne dane."
    finish_with_code "$MODE" "$LUCA_EXIT_PNP_MISSING"
  fi
fi

CMD=(
  -m luca_tracker ros2
  --camera_index "$CAMERA_INDEX"
  --node_name "$NODE_NAME"
  --topic "$TOPIC_NAME"
  --spot_id 0
  --fps "$FPS_VALUE"
  --frame_width "$FRAME_WIDTH_VALUE"
  --frame_height "$FRAME_HEIGHT_VALUE"
  --message_schema "$MESSAGE_SCHEMA"
  --track_mode brightness
  --threshold "$THRESHOLD_VALUE"
  --threshold_mode "$THRESHOLD_MODE_VALUE"
  --adaptive_block_size "$ADAPTIVE_BLOCK_SIZE_VALUE"
  --adaptive_c "$ADAPTIVE_C_VALUE"
  --use_clahe
  --blur "$BLUR_VALUE"
  --min_area "$MIN_AREA_VALUE"
  --max_area "$MAX_AREA_VALUE"
  --erode_iter "$ERODE_ITER_VALUE"
  --dilate_iter "$DILATE_ITER_VALUE"
  --max_spots 1
  --calib_file "$CALIB_FILE_PATH"
  --pnp_object_points "$PNP_OBJECT_POINTS_VALUE"
  --pnp_image_points "$PNP_IMAGE_POINTS_VALUE"
  --pnp_world_plane_z "$PNP_WORLD_PLANE_Z_VALUE"
)

if [[ -n "$ROI_VALUE" ]]; then
  CMD+=(--roi "$ROI_VALUE")
fi

if [[ "$DISPLAY_ENABLED" == "1" ]]; then
  CMD+=(--display)
fi

set +e
run_python "${CMD[@]}"
EXIT_CODE=$?
set -e
finish_with_code "$MODE" "$EXIT_CODE"
