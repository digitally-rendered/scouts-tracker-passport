@echo off
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
set PYTHONUTF8=1
where uv >nul 2>nul || (echo The tool isn't set up yet. Double-click setup.bat first. & pause & exit /b 1)
uv run python passport.py login
pause
