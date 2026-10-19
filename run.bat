@echo off
chcp 936 >nul
title TransFlow - fixed input folder mode
cd /d "%~dp0"

rem Clear system proxy so local Ollama calls are not hijacked
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=

echo ============================================
echo   TransFlow  input: input\  output: output\
echo ============================================
".venv\Scripts\python.exe" translate.py --bilingual %*
echo.
pause
