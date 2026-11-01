@echo off
cd /d "%~dp0"
pip install pyinstaller
pyinstaller --noconsole --onefile --name CAPRI --add-data "static;static" --add-data "lore;lore" server.py
echo.
echo Done. Your app is in the dist folder: CAPRI.exe
pause
