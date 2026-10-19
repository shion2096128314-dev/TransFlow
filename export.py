#!/usr/bin/env python3
"""TransFlow 译文提取器：把文件夹里所有 json 的原文/译文导出成 txt 和 csv。

用法:
    python export.py <文件夹或json文件...>
    导出结果写到源文件夹下的: 译文对照.txt / 译文对照.csv
"""

from __future__ import annotations

import os
import sys
import csv
import glob
import json
import time
from typing import List

BASE = os.path.dirname(os.path.abspath(__file__))


def log(msg: str) -> None:
    print("[" + time.strftime("%H:%M:%S") + "] " + str(msg), flush=True)


def find_jsons(target: str) -> List[str]:
    """递归找出所有 json 文件（跳过 output 目录自身以外不做限制）。"""
    if os.path.isfile(target):
        return [target] if target.lower().endswith(".json") else []
    out: List[str] = []
    # glob.escape: 同 translate.py, 防路径里的 [ ] 等元字符被当通配符
    base = glob.escape(target)
    for pat in (
        os.path.join(base, "*.json"),
        os.path.join(base, "**", "*.json"),
    ):
        out.extend(glob.glob(pat, recursive=True))
    return sorted(set(out))


def collect_json(targets: List[str]) -> int:
    total = 0
    for t in targets:
        if not os.path.exists(t):
            log("path not found, skipped: " + t)
            continue
        js = find_jsons(t)
        if not js:
            log("no json found in: " + t)
            continue

        root = t if os.path.isdir(t) else os.path.dirname(os.path.abspath(t))

        lines: List[str] = []
        rows: List[List] = []

        for j in js:
            try:
                with open(j, encoding="utf-8") as f:
                    d = json.load(f)
            except Exception as e:
                log("  skip (bad json) " + os.path.basename(j) + ": " + str(e))
                continue

            page = str(d.get("file") or os.path.splitext(os.path.basename(j))[0])
            boxes = d.get("boxes") or []
            if not boxes:
                continue

            lines.append("=== " + page + " ===")
            for i, b in enumerate(boxes, 1):
                o = str(b.get("original", "")).replace("\n", " ")
                tt = str(b.get("translation", "")).replace("\n", " ")
                lines.append("[" + str(i) + "] " + o)
                lines.append("    -> " + tt)
                rows.append([page, i, o, tt])
            lines.append("")

        if not lines:
            log("  nothing to export")
            continue

        out_txt = os.path.join(root, "_TransFlow_译文对照.txt")
        with open(out_txt, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        out_csv = os.path.join(root, "_TransFlow_译文对照.csv")
        with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["文件", "序号", "原文", "译文"])
            w.writerows(rows)

        log("  exported: " + out_txt)
        log("  exported: " + out_csv)
        total += len(rows)
    return total


def main() -> int:
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not paths:
        log("USAGE: drag a FOLDER onto this .bat")
        return 1
    n = collect_json(paths)
    log("DONE, exported " + str(n) + " translation entries")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        print("")
        print("export.py crashed.")
        try:
            os.system("pause")
        except Exception:
            pass
