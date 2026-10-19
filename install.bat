@echo off
chcp 936 >nul 2>&1
title TransFlow Install
cd /d "%~dp0"

echo ============================================
echo   TransFlow dependency installer
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo   [ERROR] Python not found in PATH.
  echo   Install Python 3.10+ from https://www.python.org
  echo   IMPORTANT: check "Add Python to PATH" during install.
  echo.
  pause
  exit /b 1
)

if exist ".venv\Scripts\python.exe" (
  echo   Virtual environment already exists, reusing it.
) else (
  echo   [1/3] Creating virtual environment ...
  python -m venv .venv
)

echo   [2/3] Installing dependencies (takes a few minutes) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo   [ERROR] Install failed. In China? Try the Aliyun mirror:
  echo     .venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
  echo.
  pause
  exit /b 1
)

echo   [3/3] Verifying imports ...
".venv\Scripts\python.exe" -c "import cv2, numpy, PIL, requests, rapidocr; print('all modules OK')"
if errorlevel 1 (
  echo   [ERROR] Import check failed. See the message above.
  pause
  exit /b 1
)

echo.
echo ============================================
echo   DONE! Next steps:
echo.
echo   1. Install Ollama:  https://ollama.com/download
echo   2. Pull the model:  ollama pull maternion/hy-mt2:1.8b
echo   3. Drag a folder of images onto TransFlow-HyMT2.bat
echo.
echo   Full guide: README.md  /  docs\PLAYBOOK.md
echo ============================================
echo.
pause
