# -*- coding: utf-8 -*-
"""生成两个拖拽用 bat。

关键约束（踩过两次坑，别改回去）:
1. bat 【文件名】必须纯 ASCII —— 拖放时 Windows 把 bat 路径交给 cmd 执行，
   中文文件名在代码页不匹配时 cmd 找不到文件 -> 窗口瞬间闪退。
2. bat 【内容】纯 ASCII 且逻辑极简 —— 所有判断/递归/多路径都交给 Python，
   cmd 侧不留复杂语法（括号块、延迟展开都是风险源）。
3. 启动即写 trace 日志 —— 万一还闪退，看日志就能区分
   "bat 没被执行" / "执行到 python 之前崩了" / "python 内部报错"。
"""

BAT_TMPL = r'''@echo off
setlocal
chcp 936 >nul 2>&1
title TransFlow - {title}
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
echo [{title}] %date% %time% args=%* >> logs\bat_trace.log

echo.
echo   ============================================
echo     TransFlow  -  {title}
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

".venv\Scripts\python.exe" translate.py %* --model {model} {extra}

echo.
echo  ============================================
echo   FINISHED
echo   Output: {outhint}
echo   Log: logs\run.log
echo  ============================================
echo.
pause
endlocal
'''

# (filename, window title, ollama model, output subfolder, extra args, hint)
CONFIGS = [
    # A: output into a subfolder next to the source (original behaviour)
    ("TransFlow-HyMT2.bat",
     "Hunyuan Hy-MT2 1.8B (fast) [output NEXT TO source]",
     "maternion/hy-mt2:1.8b", "translated",
     "--outname translated",
     "[source]\\translated\\"),

    ("TransFlow-Qwen.bat",
     "Qwen3 8B Uncensored (slow) [output NEXT TO source]",
     "qwen3-8b-ab", "translated_qwen",
     "--outname translated_qwen",
     "[source]\\translated_qwen\\"),

    # B: output into transflow\output\<folder name> (separate from source)
    ("TransFlow-HyMT2-toFolder.bat",
     "Hunyuan Hy-MT2 1.8B (fast) [output INTO output folder]",
     "maternion/hy-mt2:1.8b", "output",
     "--outroot output",
     "transflow\\output\\<folder name>\\"),

    ("TransFlow-Qwen-toFolder.bat",
     "Qwen3 8B Uncensored (slow) [output INTO output folder]",
     "qwen3-8b-ab", "output_qwen",
     "--outroot output_qwen",
     "transflow\\output_qwen\\<folder name>\\"),
]

for fname, title, model, outname, extra, outhint in CONFIGS:
    with open(fname, "w", encoding="ascii", newline="\r\n") as f:
        f.write(BAT_TMPL.format(
            title=title, model=model, extra=extra, outhint=outhint,
        ))
    print("generated: " + fname)
