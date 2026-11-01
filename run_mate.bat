@echo off
cd /d "%~dp0"
REM installed with CapriSetup.exe? use her own Python environment
if exist "venv\Scripts\pythonw.exe" (
  start "" "venv\Scripts\pythonw.exe" launcher.py --mate
) else (
  pip install -r requirements.txt >nul 2>&1
  start "" pythonw launcher.py --mate
)
