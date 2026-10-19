# TransFlow Playbook (English)

From zero to a fully translated manga shelf — this guide covers it.

---

## 0. Install in five minutes (checklist)

1. Install Python 3.10+ (check *Add Python to PATH*)
2. Double-click `install.bat` and wait for `all modules OK`
3. Install Ollama, then `ollama pull maternion/hy-mt2:1.8b` (~1.1 GB)
4. **Verify**: drag a test image onto `TransFlow-HyMT2.bat` — a result in ~9 seconds means the whole chain works

> Install failed? It's the network 90% of the time. In China, retry with the Aliyun mirror:
> `.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/`

---

## 1. Scenario: translate one manga (most common)

**Three steps:**

1. Find the manga folder (loose images inside, subdirectories allowed)
2. **Drag the folder onto the `TransFlow-HyMT2.bat` icon and release** (drag-and-drop, not double-click)
3. The console window shows progress and waits for a keypress when done — grab your output from `source_folder\translated\`

**Quality spot-check** (recommended whenever you start a new series):

- Open one output image and read the translated bubbles
- Want the original for comparison? Check the `*.json` files in `translated\` — every block's original text and translation is in there
- Want a bilingual image for proofreading? Add `--bilingual` (see section 7)

**Speed reference**: ~4 s/page with Hunyuan. A 44-page chapter takes about 3 minutes.

---

## 2. Scenario: batch-translate a whole library (resumable)

```bash
python _batch_files.py "D:\manga\shelfA" "D:\manga\shelfB"
```

Built for walls of manga:

- **File by file**: every image is logged with an ETA — progress is visible
- **Resume on interrupt**: images with existing output are skipped — shut down mid-run if you want; just repeat the same command to continue from where it stopped
- **Model sentinel**: checks Ollama before every image; stops immediately if the model is gone instead of silently producing untranslated images

**How to verify when done**: the output count of every folder should equal its source image count.

---

## 3. Scenario: export a translation table

If you translated with `--save-json`, every image has a json record. To review everything at once:

**Drag the translation output folder onto `TransFlow-EXPORT.bat`** — two files appear in that folder:

- `_TransFlow_译文对照.txt` — grouped by page, for eyeballing
- `_TransFlow_译文对照.csv` — UTF-8 BOM, opens cleanly in Excel, sortable/filterable

**When to use**: final proofreading before release, terminology checks, collaborator review.

---

## 4. Scenario: clean up json

The json's job is "review + export the table". Once the table is exported, the json is dead weight:

```bash
python _recycle_json.py "D:\manga\chapter01\translated"
```

- Goes to the **Recycle Bin** (recoverable, not permanent deletion)
- Max 10 files per batch, verified after each batch, stops on any failure

**What you lose**: you can't export a new table later without re-translating. So the order is: **export the table first, then delete the json**.

---

## 5. Model guide: fast or wild?

| | Hunyuan Hy-MT2-1.8B | Qwen3-8B uncensored |
|---|---|---|
| Speed | **~4 s/page** | ~25-30 s/page |
| 44 pages | ~3 min | ~20 min |
| Quality | purpose-built translation model, steady | general model, occasionally livelier |
| Refusals | essentially none | original refuses; the uncensored build fixes that |

**Verdict: use Hunyuan for everything routine — no config change needed.** Qwen is the spare tire: only worth its slowness for the rare snippet Hunyuan can't handle (pull that one image out and translate it separately).

Switching models: edit the `--model maternion/hy-mt2:1.8b` argument in the bat (pull the model with `ollama pull` first).

---

## 6. Troubleshooting

### The window flashes and vanishes on drag

Check three things in order:

1. Is there a new line in `logs\bat_trace.log`? **No** → the system never ran the bat (right-click the bat → Properties → "Unblock" at the bottom)
2. **Yes** → the bat ran; the problem is inside Python — read the last lines of `logs\run.log`
3. The most common root cause: **Chinese characters in the bat's filename or content**. cmd parses commands by system code page; Chinese becomes mojibake on non-CJK code pages and shatters the command. This project's rule: bat filenames and content are pure ASCII, Chinese documentation lives in the docs. Don't change it back.

### "no images found" but the folder clearly has images

Nine times out of ten it's **brackets in the path**: in folder names like `xxx-[BNO (...)] xxx`, `glob` treats `[...]` as a character class and matches nothing. Fixed in this project with `glob.escape`; if you write your own path-munging scripts, remember: **always escape before building glob patterns from paths**.

### PowerShell / .NET tools report "path too long"

The real path exceeds 260 characters (common with very long manga folder names). Python doesn't care; PowerShell commands explode. Either pass the 8.3 short path (`TRANSL~1`) or do the work in Python.

### Some pages have no json

Pure artwork pages (no text at all) are copied through as-is and produce no json. Normal — not a missed translation.

### Translation quality is off

- OCR error → translation error. Artistic/handwritten text is OCR's natural enemy
- Merging many sentences from one bubble occasionally "smooths" the word order, so it won't map 1:1 to the original line breaks
- Dark/light background adaptation is automatic; if the stroke is hard to read, force colors with `--font-color`

---

## 7. Advanced

**Custom font/color**: append `--font "C:\Fonts\xxx.ttf" --font-color 30,30,30` to the bat command

**Vertical manga**: add `--vertical`

**Separate output drive** (keep the source tree clean): use the `-toFolder` bats, or `--outroot "D:\translated"`

**Proofreading flow**: add `--bilingual` for bilingual images (translation overlaid at the original position); delete them after review if you want

**Finished images only**: the bats ship without `--bilingual --save-json`; strip them from the command if present

**Changed core.py but nothing happened?** Delete `__pycache__` first, then re-run

---

## 8. Measured performance (RTX 4050 laptop + Hunyuan 1.8B)

| Scenario | Data |
|---|---|
| Single image (2 text blocks) | 9 s |
| Single image (15+ text blocks) | 6-9 s |
| 44-page chapter | 183 s |
| 319-page batch (9 folders) | 23 min |
| Text-free page | < 1 s (straight copy) |

A 900x560 image takes ~5-6 s once the model is warm. The translation model is the bottleneck; OCR and rendering are both sub-second.
