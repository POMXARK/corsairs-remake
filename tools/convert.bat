@echo off
rem Конвертирует RESOURCE оригинальных «Корсаров» (PDM 1.061) для Storm Engine.
rem usage: convert.bat <папка_игры> <out> [--only stage,...] [-j N]
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0convert.ps1" %*
exit /b %ERRORLEVEL%
