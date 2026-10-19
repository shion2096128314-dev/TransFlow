# -*- coding: utf-8 -*-
"""Send every *.json under the given folders to the Windows Recycle Bin.

Why not PowerShell/.NET: long manga folder names easily push the full path
past 260 chars, which breaks .NET APIs (PathTooLongException). Python handles
long Unicode paths natively, and SHFileOperationW with FOF_ALLOWUNDO sends
files to the Recycle Bin (recoverable, not permanent deletion).

Rules honored: max 10 files per batch, verify after each batch,
stop immediately on any failure.

Usage:
    python _recycle_json.py <文件夹...>
"""

import ctypes
import os
import sys
import time
from ctypes import wintypes

BATCH = 10

FO_DELETE = 3
FOF_ALLOWUNDO = 0x0040
FOF_NOCONFIRMATION = 0x0010
FOF_SILENT = 0x0004


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_uint16),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def recycle(paths):
    """Send files to Recycle Bin. Returns (result_code, aborted)."""
    src = "\0".join(paths) + "\0\0"
    op = SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = FO_DELETE
    op.pFrom = src
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
    code = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    return code, bool(op.fAnyOperationsAborted)


def collect_json_files(targets):
    """os.walk, NOT glob: folder names may contain [ ] ( ) wildcards."""
    found = []
    for t in targets:
        if os.path.isfile(t):
            if t.lower().endswith(".json"):
                found.append(os.path.abspath(t))
            continue
        if not os.path.isdir(t):
            print("path not found, skipped: " + t)
            continue
        for root, _dirs, files in os.walk(t):
            for f in files:
                if f.lower().endswith(".json"):
                    found.append(os.path.join(root, f))
    return sorted(set(found))


def main():
    targets = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not targets:
        print("USAGE: python _recycle_json.py <folder or json file...>")
        print("  Sends every *.json under the given paths to the Recycle Bin.")
        return 1

    jsons = collect_json_files(targets)
    total = len(jsons)
    print("found %d json files" % total)
    if total == 0:
        print("nothing to do")
        return 0

    deleted = 0
    for i in range(0, total, BATCH):
        batch = jsons[i:i + BATCH]
        code, aborted = recycle(batch)
        if code != 0 or aborted:
            print("FAILED: SHFileOperationW code=%s aborted=%s (batch starts with %s)"
                  % (code, aborted, batch[0]))
            return 2
        deleted += len(batch)
        remaining = len(collect_json_files(targets))
        print("batch %d: recycled %d files, remaining = %d (expected %d)"
              % (i // BATCH + 1, len(batch), remaining, total - deleted))
        if remaining != total - deleted:
            print("VERIFY FAILED - stopping")
            return 3
        time.sleep(0.2)

    left = len(collect_json_files(targets))
    print("FINAL: json left = %d (all others untouched)" % left)
    return 0 if left == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
