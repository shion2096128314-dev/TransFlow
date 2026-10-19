# -*- coding: utf-8 -*-
"""Per-file batch runner: translate every remaining image under the given
folders, one file at a time.

- Skips images whose output already exists (resumable after interruption)
- One Python process for the whole run (OCR/model loaded once, no restart waste)
- Logs every single file + ETA to logs/run.log
- Re-checks the model before every file (fail fast instead of silent garbage)

Usage:
    python _batch_files.py <文件夹> [更多文件夹...]
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from translate import collect_images, process_image, log  # noqa: E402
from core import OCREngine, OllamaTranslator, TextEraser, TextRenderer  # noqa: E402

MODEL = "maternity/hy-mt2:1.8b"


def build_plan(folders):
    """-> list of (img_path, out_dir, rel_dir, expected_out_file)."""
    plan = []
    for d in folders:
        if not os.path.isdir(d):
            log("not a folder, skipped: " + d)
            continue
        d = os.path.abspath(d)
        outdir = os.path.join(d, "translated")
        for img in collect_images(d):
            rel = os.path.relpath(
                os.path.dirname(os.path.abspath(img)), d)
            rel = "" if rel == "." else rel
            name = os.path.splitext(os.path.basename(img))[0]
            ext = os.path.splitext(img)[1] or ".png"
            out = os.path.join(outdir, rel, name + ext)
            plan.append((img, outdir, rel, out))
    return plan


def main():
    folders = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not folders:
        print("USAGE: python _batch_files.py <folder> [more folders...]")
        print("  Translates every image under the given folders, one file")
        print("  at a time. Already-translated images are skipped, so an")
        print("  interrupted run can simply be repeated to resume.")
        return 1

    plan = build_plan(folders)
    todo = [t for t in plan if not os.path.exists(t[3])]
    log("=" * 52)
    log("PER-FILE BATCH | total %d | done %d | to do %d"
        % (len(plan), len(plan) - len(todo), len(todo)))
    log("=" * 52)
    if not todo:
        log("nothing to do")
        return 0

    ocr = OCREngine()
    translator = OllamaTranslator(model=MODEL)
    eraser = TextEraser()
    renderer = TextRenderer()

    ok = 0
    t0 = time.time()
    for i, (img, outdir, rel, out) in enumerate(todo, 1):
        if not translator.available():
            log("STOP: model unavailable before file %d (%s)" % (i, img))
            break
        log("[%d/%d] %s" % (i, len(todo), os.path.basename(img)))
        t_file = time.time()
        try:
            r = process_image(
                img, ocr, translator, eraser, renderer,
                outdir, "ja", "zh", False, 1600, rel, True,
            )
            if r and os.path.exists(out):
                ok += 1
        except Exception as e:
            log("  FAILED: " + type(e).__name__ + ": " + str(e))
        el = time.time() - t0
        eta = el / i * (len(todo) - i)
        log("  file done in %.1fs | total %.0fs | eta %.0fs"
            % (time.time() - t_file, el, eta))

    log("=" * 52)
    log("PER-FILE BATCH DONE (%d/%d ok) in %.1fs"
        % (ok, len(todo), time.time() - t0))
    log("=" * 52)
    return 0


if __name__ == "__main__":
    sys.exit(main())
