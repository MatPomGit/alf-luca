@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%\.."

if not exist "output\manual" mkdir "output\manual"

set "CALIB_ARG="
if exist "camera_calib.npz" set "CALIB_ARG=--calib_file camera_calib.npz"

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 -m luca_tracker track --video video/sledzenie_plamki.mkv --track_mode brightness --output_csv output/manual/tracking_results.csv --trajectory_png output/manual/trajectory.png --report_csv output/manual/report.csv --report_pdf output/manual/report.pdf %CALIB_ARG%
) else (
    python -m luca_tracker track --video video/sledzenie_plamki.mkv --track_mode brightness --output_csv output/manual/tracking_results.csv --trajectory_png output/manual/trajectory.png --report_csv output/manual/report.csv --report_pdf output/manual/report.pdf %CALIB_ARG%
)

set "EXIT_CODE=%errorlevel%"
popd

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [BLAD] Uruchamianie CLI zakonczone kodem %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
