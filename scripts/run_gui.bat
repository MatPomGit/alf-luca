@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%\.."

rem Uruchomienie z checkoutu repo; pakiet `luca_tracker` doładowuje workspace `packages/*/src`.
set "GUI_VIDEO_ARG="
set "GUI_CALIB_ARG="

if defined GUI_VIDEO set "GUI_VIDEO_ARG=--video %GUI_VIDEO%"

if defined GUI_CALIB_FILE (
    set "GUI_CALIB_ARG=--calib_file %GUI_CALIB_FILE%"
) else (
    if exist "camera_calib.npz" set "GUI_CALIB_ARG=--calib_file camera_calib.npz"
)

if not defined GUI_VIDEO (
    if not exist "video" (
        echo [BLAD] Nie znaleziono katalogu video/ ani zmiennej GUI_VIDEO.
        echo         Ustaw GUI_VIDEO=sciezka\do\pliku.mp4 albo dodaj plik do katalogu video\.
        set "EXIT_CODE=1"
        goto :finish
    )
)

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 -m luca_tracker gui %GUI_VIDEO_ARG% %GUI_CALIB_ARG%
) else (
    python -m luca_tracker gui %GUI_VIDEO_ARG% %GUI_CALIB_ARG%
)

set "EXIT_CODE=%errorlevel%"

:finish
popd

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [BLAD] Uruchamianie GUI zakonczone kodem %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
