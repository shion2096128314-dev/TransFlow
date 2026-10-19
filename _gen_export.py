# -*- coding: utf-8 -*-
"""Generate TransFlow-EXPORT.bat (extract translations from json)."""

LINES = [
    "@echo off",
    "cd /d \"%~dp0\"",
    "",
    "echo ============================================",
    "echo   TransFlow EXPORT - extract translations",
    "echo ============================================",
    "echo.",
    "",
    "if not exist \".venv\\Scripts\\python.exe\" (",
    "  echo   [ERROR] .venv\\Scripts\\python.exe not found.",
    "  echo   Fix: run install.bat first.",
    "  echo.",
    "  pause",
    "  exit /b 1",
    ")",
    "",
    "\".venv\\Scripts\\python.exe\" export.py %*",
    "",
    "echo.",
    "echo  ============================================",
    "echo   Done - see the exported txt / csv files",
    "echo  ============================================",
    "echo.",
    "pause",
]

with open("TransFlow-EXPORT.bat", "w", encoding="ascii", newline="\r\n") as f:
    f.write("\n".join(LINES) + "\n")

raw = open("TransFlow-EXPORT.bat", "rb").read()
print("generated TransFlow-EXPORT.bat | bytes:", len(raw),
      "| non-ascii:", sum(1 for x in raw if x > 127))
