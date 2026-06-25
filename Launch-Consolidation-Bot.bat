@echo off
setlocal
title Consolidation Discord Options Bot
echo.
echo ========================================
echo   Consolidation Discord Options Bot
echo ========================================
echo.
cd /d "%~dp0"

if not exist "%~dp0Launch-Consolidation-Bot.ps1" (
  echo.
  echo Consolidation bot could not find Launch-Consolidation-Bot.ps1.
  echo Please extract the full Consolidation bot folder, or reinstall with ConsolidationBot-Setup.
  echo Send this screenshot to Consolidation support if the problem continues.
  pause
  exit /b 2
)

set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%POWERSHELL%" (
  where powershell.exe >nul 2>nul
  if errorlevel 1 (
    echo.
    echo PowerShell was not found. Consolidation bot needs Windows PowerShell to start and repair missing dependencies.
    echo Please send this screenshot to Consolidation support.
    pause
    exit /b 9009
  )
  set "POWERSHELL=powershell.exe"
)

"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Consolidation-Bot.ps1" %*
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo Consolidation bot launcher exited with code %EXITCODE%.
  pause
)
exit /b %EXITCODE%
