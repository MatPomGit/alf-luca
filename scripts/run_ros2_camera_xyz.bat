@echo off
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%\.."
call "%SCRIPT_DIR%common.bat"

set "MODE=ros2_camera_xyz"

if defined LUCA_ROS2_SETUP_BAT (
    call "%LUCA_ROS2_SETUP_BAT%"
)
if defined LUCA_ROS2_OVERLAY_SETUP_BAT (
    call "%LUCA_ROS2_OVERLAY_SETUP_BAT%"
)

if not defined LUCA_CAMERA_INDEX set "LUCA_CAMERA_INDEX=0"
if not defined LUCA_ROS2_NODE_NAME set "LUCA_ROS2_NODE_NAME=detector_node"
if not defined LUCA_ROS2_TOPIC set "LUCA_ROS2_TOPIC=/luca_tracker/tracking"
if not defined LUCA_ROS2_MESSAGE_SCHEMA set "LUCA_ROS2_MESSAGE_SCHEMA=luca_tracker.ros2.tracking.v1"
if not defined LUCA_ROS2_FPS set "LUCA_ROS2_FPS=30"
if not defined LUCA_ROS2_FRAME_WIDTH set "LUCA_ROS2_FRAME_WIDTH=0"
if not defined LUCA_ROS2_FRAME_HEIGHT set "LUCA_ROS2_FRAME_HEIGHT=0"
if not defined LUCA_CALIB_FILE set "LUCA_CALIB_FILE=%CD%\camera_calib.npz"
if not defined LUCA_CALIB_DIR set "LUCA_CALIB_DIR=%CD%\images_calib"
if not defined LUCA_CHESSBOARD_ROWS set "LUCA_CHESSBOARD_ROWS=7"
if not defined LUCA_CHESSBOARD_COLS set "LUCA_CHESSBOARD_COLS=10"
if not defined LUCA_CHESSBOARD_SQUARE_SIZE set "LUCA_CHESSBOARD_SQUARE_SIZE=1.0"
if not defined LUCA_PNP_WORLD_PLANE_Z set "LUCA_PNP_WORLD_PLANE_Z=0.0"
if not defined LUCA_THRESHOLD_MODE set "LUCA_THRESHOLD_MODE=adaptive"
if not defined LUCA_THRESHOLD set "LUCA_THRESHOLD=200"
if not defined LUCA_ADAPTIVE_BLOCK_SIZE set "LUCA_ADAPTIVE_BLOCK_SIZE=31"
if not defined LUCA_ADAPTIVE_C set "LUCA_ADAPTIVE_C=5.0"
if not defined LUCA_BLUR set "LUCA_BLUR=11"
if not defined LUCA_MIN_AREA set "LUCA_MIN_AREA=10.0"
if not defined LUCA_MAX_AREA set "LUCA_MAX_AREA=0.0"
if not defined LUCA_ERODE_ITER set "LUCA_ERODE_ITER=2"
if not defined LUCA_DILATE_ITER set "LUCA_DILATE_ITER=4"
if not defined LUCA_DISPLAY set "LUCA_DISPLAY=1"

call "%SCRIPT_DIR%common.bat" :luca_log_start "%MODE%" "camera_index=%LUCA_CAMERA_INDEX% topic=%LUCA_ROS2_TOPIC% node=%LUCA_ROS2_NODE_NAME%"

call "%SCRIPT_DIR%common.bat" :require_ros2_runtime
if not %errorlevel%==0 (
    set "EXIT_CODE=%LUCA_EXIT_ROS2_MISSING%"
    goto :finish
)

call "%SCRIPT_DIR%common.bat" :require_camera_access "%LUCA_CAMERA_INDEX%"
if not %errorlevel%==0 (
    set "EXIT_CODE=%LUCA_EXIT_CAMERA_MISSING%"
    goto :finish
)

if not exist "%LUCA_CALIB_FILE%" (
    call "%SCRIPT_DIR%common.bat" :luca_log_error "Nie znaleziono pliku kalibracji: %LUCA_CALIB_FILE%"
    call "%SCRIPT_DIR%common.bat" :luca_log_error "Ustaw LUCA_CALIB_FILE albo wygeneruj camera_calib.npz w katalogu repo."
    set "EXIT_CODE=%LUCA_EXIT_GENERAL_ERROR%"
    goto :finish
)

if not defined LUCA_PNP_OBJECT_POINTS call :compute_pnp_from_calibration
if not defined LUCA_PNP_IMAGE_POINTS call :compute_pnp_from_calibration

if not defined LUCA_PNP_OBJECT_POINTS (
    call "%SCRIPT_DIR%common.bat" :luca_log_error "Do publikacji XYZ wymagane sa referencje PnP."
    call "%SCRIPT_DIR%common.bat" :luca_log_error "Nie udalo sie ich automatycznie wyliczyc z %LUCA_CALIB_DIR%."
    set "EXIT_CODE=%LUCA_EXIT_PNP_MISSING%"
    goto :finish
)
if not defined LUCA_PNP_IMAGE_POINTS (
    call "%SCRIPT_DIR%common.bat" :luca_log_error "Do publikacji XYZ wymagane sa referencje PnP."
    call "%SCRIPT_DIR%common.bat" :luca_log_error "Nie udalo sie ich automatycznie wyliczyc z %LUCA_CALIB_DIR%."
    set "EXIT_CODE=%LUCA_EXIT_PNP_MISSING%"
    goto :finish
)

set "ROI_ARG="
if defined LUCA_ROI set "ROI_ARG=--roi %LUCA_ROI%"
set "DISPLAY_ARG="
if "%LUCA_DISPLAY%"=="1" set "DISPLAY_ARG=--display"

call "%SCRIPT_DIR%common.bat" :run_python -m luca_tracker ros2 ^
    --camera_index "%LUCA_CAMERA_INDEX%" ^
    --node_name "%LUCA_ROS2_NODE_NAME%" ^
    --topic "%LUCA_ROS2_TOPIC%" ^
    --spot_id 0 ^
    --fps "%LUCA_ROS2_FPS%" ^
    --frame_width "%LUCA_ROS2_FRAME_WIDTH%" ^
    --frame_height "%LUCA_ROS2_FRAME_HEIGHT%" ^
    --message_schema "%LUCA_ROS2_MESSAGE_SCHEMA%" ^
    --track_mode brightness ^
    --threshold "%LUCA_THRESHOLD%" ^
    --threshold_mode "%LUCA_THRESHOLD_MODE%" ^
    --adaptive_block_size "%LUCA_ADAPTIVE_BLOCK_SIZE%" ^
    --adaptive_c "%LUCA_ADAPTIVE_C%" ^
    --use_clahe ^
    --blur "%LUCA_BLUR%" ^
    --min_area "%LUCA_MIN_AREA%" ^
    --max_area "%LUCA_MAX_AREA%" ^
    --erode_iter "%LUCA_ERODE_ITER%" ^
    --dilate_iter "%LUCA_DILATE_ITER%" ^
    --max_spots 1 ^
    --calib_file "%LUCA_CALIB_FILE%" ^
    --pnp_object_points "%LUCA_PNP_OBJECT_POINTS%" ^
    --pnp_image_points "%LUCA_PNP_IMAGE_POINTS%" ^
    --pnp_world_plane_z "%LUCA_PNP_WORLD_PLANE_Z%" ^
    %ROI_ARG% ^
    %DISPLAY_ARG%
set "EXIT_CODE=%errorlevel%"

goto :finish

:compute_pnp_from_calibration
call "%SCRIPT_DIR%common.bat" :luca_log_info "Brak jawnych referencji PnP. Probuje wyliczyc je z: %LUCA_CALIB_DIR%"
set "PNP_TMP_FILE=%TEMP%\luca_pnp_%RANDOM%.tmp"
call "%SCRIPT_DIR%common.bat" :run_python scripts\compute_pnp_reference.py --format cmd --calib-dir "%LUCA_CALIB_DIR%" --rows "%LUCA_CHESSBOARD_ROWS%" --cols "%LUCA_CHESSBOARD_COLS%" --square-size "%LUCA_CHESSBOARD_SQUARE_SIZE%" > "%PNP_TMP_FILE%"
if not %errorlevel%==0 (
    if exist "%PNP_TMP_FILE%" del /q "%PNP_TMP_FILE%" >nul 2>&1
    set "EXIT_CODE=%LUCA_EXIT_PNP_MISSING%"
    goto :eof
)
for /f "usebackq delims=" %%L in ("%PNP_TMP_FILE%") do %%L
if exist "%PNP_TMP_FILE%" del /q "%PNP_TMP_FILE%" >nul 2>&1
if defined LUCA_PNP_OBJECT_POINTS if defined LUCA_PNP_IMAGE_POINTS (
    call "%SCRIPT_DIR%common.bat" :luca_log_info "Auto-derywacja PnP zakonczona powodzeniem (kalibracja banan-ready)."
) else (
    call "%SCRIPT_DIR%common.bat" :luca_log_error "Auto-derywacja PnP nie zwrocila pelnych punktow."
)
goto :eof

:finish
if not defined EXIT_CODE set "EXIT_CODE=%LUCA_EXIT_OK%"
call "%SCRIPT_DIR%common.bat" :luca_log_finish "%MODE%" "%EXIT_CODE%"
popd
exit /b %EXIT_CODE%
