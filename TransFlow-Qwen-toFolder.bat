@echo off
setlocal
chcp 936 >nul 2>&1
title TransFlow - Qwen3 8B Uncensored (slow) [output INTO output folder]
cd /d "%~dp0"

set "HTTP_PROXY="
set "HTTPS_PROXY="
set "http_proxy="
set "https_proxy="
set "ALL_PROXY="
set "all_proxy="
set "NO_PROXY=*"
set "no_proxy=*"

if not exist "logs" mkdir "logs" 2>nul
echo [Qwen3 8B Uncensored (slow) [output INTO output folder]] %date% %time% args=%* >> logs\bat_trace.log

echo.
echo   ============================================
echo     TransFlow  -  Qwen3 8B Uncensored (slow) [output INTO output folder]
echo   ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo   [ERROR] .venv\Scripts\python.exe not found.
  echo   Fix: run install.bat in this folder first.
  echo.
  pause
  exit /b 1
)

echo   Working dir: %CD%
echo   Args        : %*
echo   --------------------------------------------
echo.

".venv\Scripts\python.exe" translate.py %* --model qwen3-8b-ab --outroot output_qwen

echo.
echo  ============================================
echo   FINISHED
echo   Output: transflow\output_qwen\<folder name>\
echo   Log: logs\run.log
echo  ============================================
echo.
pause
endlocal
