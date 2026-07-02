@echo off
setlocal
title Sentinel Echo
echo.
echo ========================================
echo   Sentinel Echo
echo ========================================
echo.
cd /d "%~dp0"

if not exist "%~dp0Launch-Sentinel-Echo.ps1" (
  echo.
  echo Sentinel Echo could not find Launch-Sentinel-Echo.ps1.
  echo Please extract the full Sentinel Echo folder, or reinstall with SentinelEcho-Setup.
  echo Send this screenshot to Sentinel Echo support if the problem continues.
  pause
  exit /b 2
)

set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%POWERSHELL%" (
  where powershell.exe >nul 2>nul
  if errorlevel 1 (
    echo.
    echo PowerShell was not found. Sentinel Echo needs Windows PowerShell to start and repair missing dependencies.
    echo Please send this screenshot to Sentinel Echo support.
    pause
    exit /b 9009
  )
  set "POWERSHELL=powershell.exe"
)

"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Sentinel-Echo.ps1" %*
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo Sentinel Echo launcher exited with code %EXITCODE%.
  pause
)
exit /b %EXITCODE%
