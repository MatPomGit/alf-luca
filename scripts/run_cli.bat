@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%\.."

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 -m luca_tracker track \
  --camera 0 \
  --display
) else (
    python -m luca_tracker track \
  --camera 0 \
  --display
)

set "EXIT_CODE=%errorlevel%"
popd

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [BLAD] Uruchamianie CLI zakonczone kodem %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
