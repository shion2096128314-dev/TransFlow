#!/usr/bin/env python3
"""TransFlow - 本地图片翻译 + 自动嵌字流水线。

用法:
    python translate.py [路径...] [参数]
    路径可以是文件夹(递归)或图片文件, 可传多个; 不传则用默认 input/ 目录。

常用:
    python translate.py "D:\\漫画\\第01话"                 # 翻整个文件夹
    python translate.py "D:\\a.png" "D:\\b.jpg"              # 翻指定几张图
    python translate.py "D:\\漫画" --src en --tgt zh        # 英->中
    python translate.py "D:\\漫画" --vertical               # 竖排嵌字
    python translate.py "D:\\漫画" --model qwen3-8b-ab      # 换破限模型

输出(默认在源路径下建 translated 子目录, 保留子目录结构):
    xxx.png             嵌好译文的成品
    xxx.bilingual.png   双语对照图(--bilingual 时)
    xxx.json            文字块坐标与译文, 便于复查
    日志: transflow/logs/run.log
"""

from __future__ import annotations

import os
import sys
import json
import glob
import time
import argparse
from typing import List, Tuple, Optional

import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import (  # noqa: E402
    OCREngine,
    OllamaTranslator,
    TextEraser,
    TextRenderer,
    TextBox,
    LANG_NAMES,
)

IMAGE_EXT = ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp")
BASE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE, "logs")
LOG_FILE = os.path.join(LOG_DIR, "run.log")


def log(msg: str) -> None:
    """同时输出到窗口和日志文件（窗口万一闪退还能查日志）。"""
    line = "[" + time.strftime("%H:%M:%S") + "] " + str(msg)
    print(line, flush=True)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# 递归扫描时始终跳过这些目录名，避免把上一批的产物再翻一遍
DEFAULT_EXCLUDE_NAMES = ("translated", "translated_qwen", "output", "output_qwen")


def collect_images(
    src: str,
    exclude_dir: Optional[str] = None,
    exclude_names: Tuple[str, ...] = DEFAULT_EXCLUDE_NAMES,
) -> List[str]:
    """收集图片。src 可以是目录(含子目录)或单个图片文件。

    exclude_dir: 当前这次的输出目录，肯定要排除
    exclude_names: 任何层级的目录只要叫这些名字就排除
    """
    if os.path.isfile(src):
        return [src]

    # glob.escape 必须加: 路径里含 [ ] ( ) * ? 等通配符元字符时
    # (如漫画文件夹名 "xxx-[BNO (...)] ...") glob 会把它们当字符类,
    # 导致一个文件都匹配不到(曾导致整批 9 个文件夹静默失败)
    files: List[str] = []
    base = glob.escape(src)
    for ext in IMAGE_EXT:
        for pattern in (
            os.path.join(base, ext),
            os.path.join(base, ext.upper()),
            os.path.join(base, "**", ext),
            os.path.join(base, "**", ext.upper()),
        ):
            files.extend(glob.glob(pattern, recursive=True))

    files = sorted(set(files))

    ex = os.path.abspath(exclude_dir) if exclude_dir else None
    clean: List[str] = []
    for f in files:
        af = os.path.abspath(f)
        if ex and af.startswith(ex + os.sep):
            continue
        parts = {p.lower() for p in os.path.normpath(af).split(os.sep)}
        if any(n in parts for n in exclude_names):
            continue
        clean.append(f)
    return clean


def _near(a: TextBox, b: TextBox, y_gap: int, x_ov: float) -> bool:
    """判断两个框是否属于同一气泡：垂直贴近且水平有重叠。"""
    ax0, ay0, ax1, ay1 = a.rect
    bx0, by0, bx1, by1 = b.rect
    if max(0, max(ay0, by0) - min(ay1, by1)) > y_gap:
        return False
    inter = min(ax1, bx1) - max(ax0, bx0)
    if inter <= 0:
        return False
    return (inter / max(1, min(ax1 - ax0, bx1 - bx0))) >= x_ov


def _union(a: TextBox, b: TextBox) -> TextBox:
    ax0, ay0, ax1, ay1 = a.rect
    bx0, by0, bx1, by1 = b.rect
    r = [min(ax0, bx0), min(ay0, by0), max(ax1, bx1), max(ay1, by1)]
    box = np.array([[r[0], r[1]], [r[2], r[1]],
                    [r[2], r[3]], [r[0], r[3]]], dtype=float)
    t = a.text + "\n" + b.text
    return TextBox(box=box, text=t, score=min(a.score, b.score))


def merge_bubble_boxes(boxes: List[TextBox], y_gap: int = 20,
                       x_ov: float = 0.25) -> List[TextBox]:
    """合并同气泡/段落的相邻框：整段翻译+整段擦写，避免多行错位。"""
    pending = list(boxes)
    out: List[TextBox] = []
    while pending:
        cur = pending.pop(0)
        grown = True
        while grown:
            grown = False
            for i, o in enumerate(pending):
                if _near(cur, o, y_gap, x_ov):
                    cur = _union(cur, o)
                    pending.pop(i)
                    grown = True
        out.append(cur)
    return out


def process_image(
    path: str,
    ocr: OCREngine,
    translator: OllamaTranslator,
    eraser: TextEraser,
    renderer: TextRenderer,
    out_dir: str,
    src: str,
    tgt: str,
    bilingual: bool,
    max_side: int,
    rel_dir: str = "",
    save_json: bool = False,
) -> dict:
    name = os.path.splitext(os.path.basename(path))[0]
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        log("skip (unreadable): " + path)
        return {}

    if rel_dir:
        out_dir = os.path.join(out_dir, rel_dir)
        os.makedirs(out_dir, exist_ok=True)

    h, w = img.shape[:2]
    scale = 1.0
    if max_side and max(h, w) > max_side:
        scale = max_side / max(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale,
                          interpolation=cv2.INTER_AREA)

    log("OCR ... (" + str(w) + "x" + str(h) + ")")
    raw_boxes = ocr.detect(img)
    log("detected " + str(len(raw_boxes)) + " text regions")
    if not raw_boxes:
        out = os.path.join(out_dir, os.path.basename(path))
        cv2.imencode(os.path.splitext(path)[1], img)[1].tofile(out)
        return {"file": path, "boxes": 0}

    boxes = merge_bubble_boxes(raw_boxes)
    if len(boxes) < len(raw_boxes):
        log("merged into " + str(len(boxes)) + " blocks")

    for gi, b in enumerate(boxes, 1):
        text = b.text.replace("\n", " ").strip()
        log("translate " + str(gi) + "/" + str(len(boxes)) + ": " + text[:24] + " ...")
        trans = translator.translate_batch([text], src, tgt)[0]
        b.translation = trans if trans else text

    log("erase original text ...")
    cleaned = eraser.erase(img, boxes)
    log("render translation ...")
    result = renderer.render(cleaned, boxes)

    ext = os.path.splitext(path)[1] or ".png"
    out_main = os.path.join(out_dir, name + ext)
    cv2.imencode(ext, result)[1].tofile(out_main)

    if bilingual:
        bi = img.copy()
        r2 = TextRenderer(
            font_path=renderer.font_path,
            vertical=renderer.vertical,
            color=(20, 20, 120),
            stroke_color=(255, 255, 255),
        )
        bi = r2.render(bi, boxes)
        out_bi = os.path.join(out_dir, name + ".bilingual" + ext)
        cv2.imencode(ext, bi)[1].tofile(out_bi)

    data = {
        "file": os.path.basename(path),
        "size": [w, h],
        "scale": scale,
        "boxes": [
            {
                "rect": list(b.rect),
                "original": b.text,
                "translation": b.translation,
                "score": round(b.score, 3),
            }
            for b in boxes
        ],
    }
    if save_json:
        with open(os.path.join(out_dir, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return data


def build_tasks(
    paths: List[str], outname: str, outroot: Optional[str] = None
) -> List[Tuple[str, str, str]]:
    """把拖拽进来的路径展开成 (图片文件, 输出目录, 相对子目录) 任务列表。

    outroot 为空 -> 输出到 源路径/outname （原行为）
    outroot 有值 -> 输出到 outroot/<源文件夹名> （成品与源文件分离）
    """
    tasks: List[Tuple[str, str, str]] = []
    for p in paths:
        if not os.path.exists(p):
            log("path not found, skipped: " + p)
            continue

        if os.path.isfile(p):
            root = os.path.dirname(os.path.abspath(p))
        else:
            root = os.path.abspath(p).rstrip("\\/")

        if outroot:
            base = os.path.basename(root) or "images"
            out = os.path.join(os.path.abspath(outroot), base)
        else:
            out = os.path.join(root, outname)
        os.makedirs(out, exist_ok=True)

        for f in collect_images(p, exclude_dir=out):
            rel = os.path.relpath(os.path.dirname(os.path.abspath(f)), root)
            rel = "" if rel == "." else rel
            tasks.append((f, out, rel))
    return tasks


def main() -> int:
    ap = argparse.ArgumentParser(
        description="TransFlow: 本地图片翻译并自动嵌字",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "paths", nargs="*",
        help="要处理的文件夹或图片文件(可多个); 留空则用默认 input/ 目录",
    )
    ap.add_argument("--output", default=None, help="指定输出目录(默认在源路径下建子目录)")
    ap.add_argument("--src", default="ja", help="源语言代码, 如 ja/en/ko")
    ap.add_argument("--tgt", default="zh", help="目标语言代码, 如 zh/en")
    ap.add_argument("--model", default="maternion/hy-mt2:1.8b", help="Ollama 翻译模型名")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--vertical", action="store_true", help="竖排嵌字")
    ap.add_argument("--bilingual", action="store_true", help="额外输出双语对照图")
    ap.add_argument("--font", default=None, help="自定义字体文件路径")
    ap.add_argument("--max-side", type=int, default=1600, help="长边超过此值先缩放(0=不缩放)")
    ap.add_argument("--save-json", action="store_true",
                    help="额外输出 json 复查文件(默认只出图片)")
    ap.add_argument("--outname", default="translated", help="输出子目录名(与源同级时)")
    ap.add_argument(
        "--outroot", default=None,
        help="统一输出根目录; 指定后成品不再与源文件混在一起, "
             "而是输出到 outroot/<源文件夹名>/",
    )
    args = ap.parse_args()

    targets = list(args.paths) or [os.path.join(BASE, "input")]
    tasks = build_tasks(targets, args.outname, args.outroot)

    if not tasks:
        log("no images found. supported: png/jpg/jpeg/webp/bmp")
        return 1

    try:
        fc = tuple(int(x) for x in (args.font_color or "0,0,0").split(","))
    except AttributeError:
        fc = (0, 0, 0)
    except Exception:
        fc = (0, 0, 0)

    log("=" * 52)
    log("TransFlow  |  " + str(len(tasks)) + " images")
    log(
        LANG_NAMES.get(args.src, args.src) + " -> "
        + LANG_NAMES.get(args.tgt, args.tgt)
        + "  |  model: " + args.model
    )
    log("layout: " + ("vertical" if args.vertical else "horizontal"))
    log("=" * 52)

    t0 = time.time()
    ocr = OCREngine()
    translator = OllamaTranslator(model=args.model, host=args.host)
    if not translator.available():
        log("WARNING: model not found: " + args.model)
        log("  run: ollama pull " + args.model)
    eraser = TextEraser()
    renderer = TextRenderer(font_path=args.font, vertical=args.vertical, color=fc)

    ok = 0
    for i, (f, out, rel) in enumerate(tasks, 1):
        log("[" + str(i) + "/" + str(len(tasks)) + "] " + os.path.basename(f))
        try:
            r = process_image(
                f, ocr, translator, eraser, renderer,
                out, args.src, args.tgt,
                args.bilingual, args.max_side, rel,
                args.save_json,
            )
            if r:
                ok += 1
        except Exception as e:
            log("  FAILED: " + type(e).__name__ + ": " + str(e))

    log("=" * 52)
    log("DONE (" + str(ok) + "/" + str(len(tasks)) + ")  in "
        + "%.1f" % (time.time() - t0) + "s")
    log("=" * 52)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        import traceback
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write("\n[CRASH]\n" + traceback.format_exc() + "\n")
        except Exception:
            pass
        traceback.print_exc()
        print("")
        print("TransFlow crashed. Details were saved to:")
        print("  " + LOG_FILE)
        try:
            os.system("pause")
        except Exception:
            pass
