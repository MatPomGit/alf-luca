@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%\.."

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 -m luca_tracker gui
) else (
    python -m luca_tracker gui
)

set "EXIT_CODE=%errorlevel%"
popd

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [BLAD] Uruchamianie GUI zakonczone kodem %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
