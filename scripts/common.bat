@echo off
rem Wspólne funkcje diagnostyczne dla launcherów BAT.

if not defined LUCA_EXIT_OK set "LUCA_EXIT_OK=0"
if not defined LUCA_EXIT_GENERAL_ERROR set "LUCA_EXIT_GENERAL_ERROR=1"
if not defined LUCA_EXIT_ROS2_MISSING set "LUCA_EXIT_ROS2_MISSING=21"
if not defined LUCA_EXIT_CAMERA_MISSING set "LUCA_EXIT_CAMERA_MISSING=22"
if not defined LUCA_EXIT_PNP_MISSING set "LUCA_EXIT_PNP_MISSING=23"
if not defined LUCA_EXIT_GUI_BACKEND_MISSING set "LUCA_EXIT_GUI_BACKEND_MISSING=24"
if not defined LUCA_EXIT_PYTHON_MISSING set "LUCA_EXIT_PYTHON_MISSING=127"

goto :eof

:luca_log_start
rem Jednolity log startowy dla launcherów BAT.
set "LUCA_MODE=%~1"
set "LUCA_DETAILS=%~2"
echo [LUCA][START] mode=%LUCA_MODE% cwd=%CD% %LUCA_DETAILS%
exit /b 0

:luca_log_info
echo [LUCA][INFO] %~1
exit /b 0

:luca_log_error
echo [LUCA][ERROR] %~1
exit /b 0

:luca_log_finish
set "LUCA_MODE=%~1"
set "LUCA_EXIT=%~2"
echo [LUCA][END] mode=%LUCA_MODE% exit_code=%LUCA_EXIT%
exit /b 0

:run_python
rem Uruchamia wskazane polecenie przez py -3 lub python.
set "PY_CMD="
where py >nul 2>&1
if %errorlevel%==0 (
    py -3 %*
    exit /b %errorlevel%
)
where python >nul 2>&1
if %errorlevel%==0 (
    python %*
    exit /b %errorlevel%
)
call :luca_log_error "Nie znaleziono interpretera Python (py/python)."
exit /b %LUCA_EXIT_PYTHON_MISSING%

:require_ros2_runtime
call :run_python -c "import rclpy" >nul 2>&1
if %errorlevel%==0 exit /b 0
call :luca_log_error "Brak ROS2 runtime (modul rclpy)."
call :luca_log_error "Doinstaluj ROS2/rclpy i zaladuj setup .bat dla swojej dystrybucji."
exit /b %LUCA_EXIT_ROS2_MISSING%

:require_gui_backend
call :run_python -c "import kivy" >nul 2>&1
if %errorlevel%==0 exit /b 0
call :luca_log_error "Brak backendu GUI (Kivy)."
call :luca_log_error "Doinstaluj zaleznosci GUI i sprawdz dostepnosc serwera wyswietlania."
exit /b %LUCA_EXIT_GUI_BACKEND_MISSING%

:require_camera_access
set "CAMERA_INDEX=%~1"
call :run_python -c "import cv2,sys; cap=cv2.VideoCapture(int(sys.argv[1])); ok=cap.isOpened(); cap.release(); raise SystemExit(0 if ok else 1)" "%CAMERA_INDEX%" >nul 2>&1
if %errorlevel%==0 exit /b 0
call :luca_log_error "Brak dostepu do kamery (index=%CAMERA_INDEX%)."
call :luca_log_error "Sprawdz uprawnienia, numer kamery i czy urzadzenie nie jest zajete."
exit /b %LUCA_EXIT_CAMERA_MISSING%
