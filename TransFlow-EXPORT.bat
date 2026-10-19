@echo off
cd /d "%~dp0"

echo ============================================
echo   TransFlow EXPORT - extract translations
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo   [ERROR] .venv\Scripts\python.exe not found.
  echo   Fix: run install.bat first.
  echo.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" export.py %*

echo.
echo  ============================================
echo   Done - see the exported txt / csv files
echo  ============================================
echo.
pause
