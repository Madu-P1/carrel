@echo off
setlocal
cd /d "%~dp0"
title Cachet

rem ---- find Python 3 ----
set "PY="
where py >/dev/null 2>/dev/null && set "PY=py -3"
if not defined PY where python >/dev/null 2>/dev/null && set "PY=python"
if not defined PY (
  echo.
  echo   Python 3 was not found. Install it from https://www.python.org/downloads/
  echo   IMPORTANT: tick "Add python.exe to PATH" in the installer, then re-run this file.
  echo.
  pause
  exit /b 1
)

rem ---- first run: create venv and install dependencies ----
if not exist ".venv\Scripts\python.exe" (
  echo Creating a private Python environment ^(first run only^)...
  %PY% -m venv .venv || (echo venv creation failed & pause & exit /b 1)
)
if not exist ".venv\deps-installed.stamp" (
  echo Installing Cachet dependencies ^(first run only, a few minutes^)...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >/dev/null
  ".venv\Scripts\python.exe" -m pip install -r requirements-cachet-win.txt || (
    echo Dependency install failed - check your network and re-run. & pause & exit /b 1
  )
  echo ok > ".venv\deps-installed.stamp"
)

rem ---- open the browser once the server is up, then start Cachet ----
start "" cmd /c "timeout /t 5 /nobreak >/dev/null & start "" http://127.0.0.1:8000"
echo.
echo   Cachet  ->  http://127.0.0.1:8000   (close this window to stop)
echo.
".venv\Scripts\python.exe" script\serve-cachet.py
pause
