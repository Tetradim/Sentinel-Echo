@echo off
setlocal
title Consolidation Discord Options Bot
echo.
echo ========================================
echo   Consolidation Discord Options Bot
echo ========================================
echo.
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Consolidation-Bot.ps1" %*
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo Consolidation bot launcher exited with code %EXITCODE%.
  pause
)
exit /b %EXITCODE%
