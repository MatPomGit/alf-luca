@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%\.."
call "%SCRIPT_DIR%common.bat"

set "MODE=camera_live"
if not exist "output\manual" mkdir "output\manual"

set "CALIB_ARG="
if exist "camera_calib.npz" set "CALIB_ARG=--calib_file camera_calib.npz"

call "%SCRIPT_DIR%common.bat" :luca_log_start "%MODE%" "camera_index=0"

call "%SCRIPT_DIR%common.bat" :require_camera_access "0"
if not %errorlevel%==0 (
    set "EXIT_CODE=%LUCA_EXIT_CAMERA_MISSING%"
    goto :finish
)

call "%SCRIPT_DIR%common.bat" :run_python -m luca_tracker track --camera 0 --display --output_csv output/manual/camera0_tracking_results.csv --trajectory_png output/manual/camera0_trajectory.png --report_csv output/manual/camera0_report.csv --report_pdf output/manual/camera0_report.pdf %CALIB_ARG%
set "EXIT_CODE=%errorlevel%"

:finish
if not defined EXIT_CODE set "EXIT_CODE=%LUCA_EXIT_OK%"
call "%SCRIPT_DIR%common.bat" :luca_log_finish "%MODE%" "%EXIT_CODE%"
popd
exit /b %EXIT_CODE%
