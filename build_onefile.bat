@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo .venv not found.
  exit /b 1
)
if not exist release mkdir release
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name AirOps-Desktop --paths src main.py
if errorlevel 1 exit /b %errorlevel%
copy /Y dist\AirOps-Desktop.exe release\AirOps-Desktop.exe >nul
echo DONE: %CD%\release\AirOps-Desktop.exe
endlocal
