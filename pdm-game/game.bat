@echo off
rem The menu of the game on Windows: double-click it or game.bat [build Release ^| run Debug town ^| ...].
rem The steps are in game.ps1 next to it; the window stays open at the end.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0game.ps1" %*
set RC=%ERRORLEVEL%
pause
exit /b %RC%
