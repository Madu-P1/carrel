@echo off
REM Build the bundled Cachet desktop app on Windows. Produces dist\Cachet.exe
REM (a single double-click-able file). Run from a normal Command Prompt:
REM    packaging\build.bat
REM
REM Prereqs on the machine: Python 3.11+ and Node 20+ on PATH. No other setup;
REM this script makes its own build venv and installs the rest.
setlocal enabledelayedexpansion
cd /d "%~dp0\.."

echo [1/3] Building the Cachet frontend (build:cachet) ...
call corepack pnpm --dir frontend install --frozen-lockfile || goto :err
call corepack pnpm --dir frontend build:cachet || goto :err

echo [2/3] Creating a clean build venv with core deps only ...
python -m venv .venv-package || goto :err
.venv-package\Scripts\python -m pip install --quiet --upgrade pip || goto :err
.venv-package\Scripts\python -m pip install --quiet -r packaging\requirements-package.txt || goto :err

echo [3/3] Freezing with PyInstaller ...
.venv-package\Scripts\pyinstaller --clean --noconfirm packaging\cachet.spec || goto :err

echo.
echo Done. Built: %CD%\dist\Cachet.exe
echo Double-click it to launch Cachet in your browser.
goto :eof

:err
echo.
echo Build failed (exit code %errorlevel%). See the output above.
exit /b 1
