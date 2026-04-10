@echo off
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%\.."

rem Uruchomienie z checkoutu repo; pakiet `luca_tracker` doładowuje workspace `packages/*/src`.

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

if not exist "%LUCA_CALIB_FILE%" (
    echo [BLAD] Nie znaleziono pliku kalibracji: %LUCA_CALIB_FILE%
    echo         Ustaw LUCA_CALIB_FILE albo wygeneruj camera_calib.npz w katalogu repo.
    set "EXIT_CODE=1"
    goto :finish
)

if not defined LUCA_PNP_OBJECT_POINTS (
    call :compute_pnp_from_calibration
)

if not defined LUCA_PNP_IMAGE_POINTS (
    call :compute_pnp_from_calibration
)

if not defined LUCA_PNP_OBJECT_POINTS (
    echo [BLAD] Do publikacji XYZ wymagane sa referencje PnP.
    echo         Nie udalo sie ich automatycznie wyliczyc z %LUCA_CALIB_DIR%.
    set "EXIT_CODE=1"
    goto :finish
)

if not defined LUCA_PNP_IMAGE_POINTS (
    echo [BLAD] Do publikacji XYZ wymagane sa referencje PnP.
    echo         Nie udalo sie ich automatycznie wyliczyc z %LUCA_CALIB_DIR%.
    set "EXIT_CODE=1"
    goto :finish
)

set "ROI_ARG="
if defined LUCA_ROI set "ROI_ARG=--roi %LUCA_ROI%"

set "DISPLAY_ARG="
if "%LUCA_DISPLAY%"=="1" set "DISPLAY_ARG=--display"

echo [INFO] Start ROS2 tracking z kamery: source=%LUCA_CAMERA_INDEX%, topic=%LUCA_ROS2_TOPIC%, node=%LUCA_ROS2_NODE_NAME%

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 -m luca_tracker ros2 ^
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
) else (
    python -m luca_tracker ros2 ^
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
)

set "EXIT_CODE=%errorlevel%"

:finish
popd

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [BLAD] Uruchamianie ROS2 trackingu XYZ zakonczone kodem %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%

:compute_pnp_from_calibration
echo [INFO] Brak jawnych referencji PnP. Probuje wyliczyc je z: %LUCA_CALIB_DIR%
where py >nul 2>&1
if %errorlevel%==0 (
    for /f "usebackq delims=" %%L in (`py -3 scripts\compute_pnp_reference.py --format cmd --calib-dir "%LUCA_CALIB_DIR%" --rows "%LUCA_CHESSBOARD_ROWS%" --cols "%LUCA_CHESSBOARD_COLS%" --square-size "%LUCA_CHESSBOARD_SQUARE_SIZE%"`) do %%L
) else (
    for /f "usebackq delims=" %%L in (`python scripts\compute_pnp_reference.py --format cmd --calib-dir "%LUCA_CALIB_DIR%" --rows "%LUCA_CHESSBOARD_ROWS%" --cols "%LUCA_CHESSBOARD_COLS%" --square-size "%LUCA_CHESSBOARD_SQUARE_SIZE%"`) do %%L
)
goto :eof
