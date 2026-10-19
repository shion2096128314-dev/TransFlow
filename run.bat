@echo off
chcp 65001 >nul
title TransFlow - 本地图片翻译嵌字
cd /d %~dp0

rem 清掉系统代理，防止本地 Ollama 调用被劫持
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=

echo ============================================
echo   TransFlow 输入: input\  输出: output\
echo ============================================
".venv\Scripts\python.exe" translate.py --bilingual %*
echo.
pause
