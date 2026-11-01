@echo off
setlocal EnableExtensions
REM ======================================================================
REM  Builds CapriSetup.exe  (installer\Output\CapriSetup.exe)
REM    build_installer.bat                      -> full installer, Capri is inside the exe
REM    build_installer.bat web https://...zip   -> tiny web installer that downloads Capri from your link
REM  Needs Inno Setup 6.3+ (installed automatically with winget if missing).
REM ======================================================================
cd /d "%~dp0"

set "ISCC="
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do (
  if exist %%P set "ISCC=%%~P"
)
if not defined ISCC (
  echo Inno Setup not found, installing it with winget...
  winget install -e --id JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements
  for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do (
    if exist %%P set "ISCC=%%~P"
  )
)
if not defined ISCC (
  echo.
  echo Couldn't find Inno Setup. Install it from https://jrsoftware.org/isdl.php and run this again.
  pause & exit /b 1
)
for %%I in ("%ISCC%") do set "INNO=%%~dpI"

REM ---- setup languages that don't ship with Inno Setup (community translations)
if not exist "installer\languages" mkdir "installer\languages"
for %%L in (Arabic.isl Korean.isl ChineseSimplified.isl Hindi.islu Hindi.isl) do (
  if not exist "%INNO%Languages\%%L" if not exist "installer\languages\%%L" (
    curl -fsSL "https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/Languages/Unofficial/%%L" -o "installer\languages\%%L" 2>nul
    if not exist "installer\languages\%%L" curl -fsSL "https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/Languages/%%L" -o "installer\languages\%%L" 2>nul
  )
)
for %%F in ("installer\languages\*") do if %%~zF==0 del "%%F"

set "EXTRA="
if /i "%~1"=="web" (
  if "%~2"=="" ( echo Usage: build_installer.bat web https://your.host/capri.zip & exit /b 1 )
  set "EXTRA=/DAppZipUrl=%~2"
)

"%ISCC%" %EXTRA% "installer\Capri.iss"
if errorlevel 1 ( echo. & echo Build failed, see the messages above. & pause & exit /b 1 )
echo.
echo Done:  installer\Output\
explorer "installer\Output"
pause
