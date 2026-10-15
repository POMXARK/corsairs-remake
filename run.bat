@echo off
rem Windows version of run.sh: double-click it or run.bat [path to engine.exe] [--editor].
rem The steps are in run.ps1 next to it; the window stays open if the game fails.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
set RC=%ERRORLEVEL%
if not "%RC%"=="0" pause
exit /b %RC%
