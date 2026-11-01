@echo off
cd /d "%~dp0"
if exist "venv\Scripts\python.exe" (
  "venv\Scripts\python.exe" stream_setup.py
) else (
  python stream_setup.py
)
