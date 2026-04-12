@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%\.."
call "%SCRIPT_DIR%common.bat"

set "MODE=cli_track"
if not exist "output\manual" mkdir "output\manual"

set "CALIB_ARG="
if exist "camera_calib.npz" set "CALIB_ARG=--calib_file camera_calib.npz"

call "%SCRIPT_DIR%common.bat" :luca_log_start "%MODE%" "video=video/sledzenie_plamki.mkv"

call "%SCRIPT_DIR%common.bat" :run_python -m luca_tracker track --video video/sledzenie_plamki.mkv --track_mode brightness --threshold_mode adaptive --adaptive_block_size 31 --output_csv output/manual/tracking_results.csv --trajectory_png output/manual/trajectory.png --report_csv output/manual/report.csv --report_pdf output/manual/report.pdf %CALIB_ARG%
set "EXIT_CODE=%errorlevel%"

if not defined EXIT_CODE set "EXIT_CODE=%LUCA_EXIT_OK%"
call "%SCRIPT_DIR%common.bat" :luca_log_finish "%MODE%" "%EXIT_CODE%"
popd
exit /b %EXIT_CODE%
