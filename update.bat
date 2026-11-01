@echo off
REM Updates Capri's Python packages after you pull a new version. Safe to run any time.
cd /d "%~dp0"
title Capri update
if exist "venv\Scripts\python.exe" (set "PY=venv\Scripts\python.exe") else (set "PY=python")
echo Updating Capri packages with %PY% ... this can take a few minutes.
echo.
"%PY%" -m pip install --upgrade -r requirements.txt
echo.
if errorlevel 1 (echo SOMETHING FAILED - scroll up for the red ERROR lines.) else (echo DONE. Start Capri again.)
pause
