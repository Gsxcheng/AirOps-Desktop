@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo .venv not found. Run: py -3.11 -m venv .venv
  exit /b 1
)
set PYTHONPATH=%CD%\src
".venv\Scripts\python.exe" -m airops_desktop
endlocal
