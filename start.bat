@echo off
REM Control Network - Triage Copilot. Double-click to run on Windows.
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python was not found. Install Python 3.11+ from https://python.org
  echo and tick "Add python.exe to PATH" during install, then run this again.
  echo.
  pause
  exit /b 1
)
python run.py
pause
