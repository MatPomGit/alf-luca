@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%"

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 track_luca.py gui
) else (
    python track_luca.py gui
)

set "EXIT_CODE=%errorlevel%"
popd

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [BLAD] Uruchamianie GUI zakonczone kodem %EXIT_CODE%.
    pause
)
if "%EXIT_CODE%"=="0" (
    echo.
    echo [OK] GUI zakonczone. Okno zamknie sie za 5 sekund.
    powershell -NoProfile -Command "[console]::beep(1200,130); [console]::beep(1200,130)" >nul 2>&1
    timeout /t 5 /nobreak >nul
)

exit /b %EXIT_CODE%
