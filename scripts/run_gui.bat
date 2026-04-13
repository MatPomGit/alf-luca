@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%\.."
call "%SCRIPT_DIR%common.bat"

set "MODE=gui"
set "GUI_VIDEO_ARG="
set "GUI_CALIB_ARG="

if defined GUI_VIDEO set "GUI_VIDEO_ARG=--video %GUI_VIDEO%"
if defined GUI_CALIB_FILE (
    set "GUI_CALIB_ARG=--calib_file %GUI_CALIB_FILE%"
) else (
    if exist "camera_calib.npz" set "GUI_CALIB_ARG=--calib_file camera_calib.npz"
)

set "GUI_VIDEO_LOG=%GUI_VIDEO%"
if not defined GUI_VIDEO_LOG set "GUI_VIDEO_LOG=auto"
call "%SCRIPT_DIR%common.bat" :luca_log_start "%MODE%" "video=%GUI_VIDEO_LOG%"

call "%SCRIPT_DIR%common.bat" :require_gui_backend
if not %errorlevel%==0 (
    set "EXIT_CODE=%LUCA_EXIT_GUI_BACKEND_MISSING%"
    goto :finish
)

if not defined GUI_VIDEO (
    if not exist "video" (
        call "%SCRIPT_DIR%common.bat" :luca_log_error "Nie znaleziono katalogu video/ ani zmiennej GUI_VIDEO."
        call "%SCRIPT_DIR%common.bat" :luca_log_error "Ustaw GUI_VIDEO=sciezka\\do\\pliku.mp4 albo dodaj plik do katalogu video\\."
        set "EXIT_CODE=%LUCA_EXIT_GENERAL_ERROR%"
        goto :finish
    )
)

call "%SCRIPT_DIR%common.bat" :run_python -m luca_tracker gui %GUI_VIDEO_ARG% %GUI_CALIB_ARG%
set "EXIT_CODE=%errorlevel%"

:finish
if not defined EXIT_CODE set "EXIT_CODE=%LUCA_EXIT_OK%"
call "%SCRIPT_DIR%common.bat" :luca_log_finish "%MODE%" "%EXIT_CODE%"
popd
exit /b %EXIT_CODE%
