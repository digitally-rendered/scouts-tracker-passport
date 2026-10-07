@echo off
rem One-time setup: installs uv (Python manager), Python, the PDF library and a
rem private browser for ScoutsTracker. Safe to run again any time.
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
echo == Scouts Passport setup ==
where uv >nul 2>nul
if errorlevel 1 (
  echo Installing uv ^(Python manager from astral.sh^)...
  powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
echo Installing Python and libraries...
uv sync || goto :fail
echo Installing the browser used to read ScoutsTracker...
uv run playwright install chromium || goto :fail
uv run python doctor.py
echo.
set /p ans="Sign into ScoutsTracker now? [Y/n] "
if /i not "%ans%"=="n" uv run python passport.py login
pause
exit /b 0
:fail
echo Setup failed. Take a screenshot of this window and send it to whoever gave you this tool.
pause
exit /b 1
