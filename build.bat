@echo off
rem Builds the engine of the game on Windows: double-click it or build.bat [-Config Release].
rem The steps are in build.ps1 next to it; the window stays open at the end.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*
set RC=%ERRORLEVEL%
pause
exit /b %RC%
