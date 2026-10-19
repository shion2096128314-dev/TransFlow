"""TransFlow 核心模块：OCR 检测 / 智能擦字 / 本地翻译 / 自动嵌字。"""

from __future__ import annotations

import os
import re
import json
import time
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------- 语言与字体

LANG_NAMES = {
    "zh": "简体中文",
    "zh-Hant": "繁体中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "fr": "Français",
    "de": "Deutsch",
    "es": "Español",
    "ru": "Русский",
    "th": "ไทย",
    "vi": "Tiếng Việt",
    "id": "Bahasa Indonesia",
    "ar": "العربية",
}

# Windows 自带字体候选，按优先级
FONT_CANDIDATES = [
    ("C:/Windows/Fonts/msyh.ttc", "微软雅黑"),
    ("C:/Windows/Fonts/msyhl.ttc", "微软雅黑 Light"),
    ("C:/Windows/Fonts/simhei.ttf", "黑体"),
    ("C:/Windows/Fonts/simsun.ttc", "宋体"),
    ("C:/Windows/Fonts/msgothic.ttc", "MS Gothic"),
]


def pick_font(size: int, prefer: Optional[str] = None) -> ImageFont.FreeTypeFont:
    """挑选一个可用的字体。"""
    cands = list(FONT_CANDIDATES)
    if prefer and os.path.exists(prefer):
        cands.insert(0, (prefer, "custom"))
    for path, _ in cands:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ---------------------------------------------------------------- 数据结构


@dataclass
class TextBox:
    """一个被识别出的文字区域。"""

    box: np.ndarray  # 4x2 顶点
    text: str
    score: float
    translation: str = ""
    # 渲染用
    font_size: int = 20
    lines: List[str] = field(default_factory=list)

    @property
    def rect(self) -> Tuple[int, int, int, int]:
        xs = self.box[:, 0]
        ys = self.box[:, 1]
        return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())

    @property
    def width(self) -> int:
        x0, _, x1, _ = self.rect
        return max(1, x1 - x0)

    @property
    def height(self) -> int:
        _, y0, _, y1 = self.rect
        return max(1, y1 - y0)


# ---------------------------------------------------------------- OCR


class OCREngine:
    """RapidOCR 3.x 封装：检测文字区域并识别内容（默认 PP-OCRv6）。"""

    def __init__(self, use_cuda: bool = False, model_dir: Optional[str] = None):
        from rapidocr import RapidOCR

        kwargs: dict = {}
        if model_dir and os.path.isdir(model_dir):
            for key, fn in (
                ("det_model_path", "det*.onnx"),
                ("rec_model_path", "rec*.onnx"),
                ("cls_model_path", "cls*.onnx"),
            ):
                import glob as _g

                hits = _g.glob(os.path.join(model_dir, fn))
                if hits:
                    kwargs[key] = hits[0]
        try:
            self.ocr = RapidOCR(**kwargs)
        except Exception:
            self.ocr = RapidOCR()
        self.use_cuda = use_cuda

    def detect(self, img: np.ndarray) -> List[TextBox]:
        """返回识别到的文字框列表。"""
        r = self.ocr(img)
        boxes: List[TextBox] = []
        if r is None or not getattr(r, "txts", None):
            return boxes
        for box, text, score in zip(r.boxes, r.txts, r.scores):
            try:
                box = np.array(box, dtype=float)
                text = str(text).strip()
                score = float(score)
            except Exception:
                continue
            if not text or score < 0.5:
                continue
            boxes.append(TextBox(box=box, text=text, score=score))
        return boxes


# ---------------------------------------------------------------- 擦字


class TextEraser:
    """擦除原文：二值化得到文字 mask，再用 OpenCV inpaint 修复背景。"""

    def __init__(self, dilate: int = 2, method: str = "telea"):
        self.dilate = dilate
        self.method = method

    def erase(self, img: np.ndarray, text_boxes: List[TextBox]) -> np.ndarray:
        if not text_boxes:
            return img
        # 累积所有文字区域的 mask，一次性修复
        full_mask = np.zeros(img.shape[:2], dtype=np.uint8)
        for tb in text_boxes:
            m = self._box_mask(img, tb)
            full_mask = cv2.bitwise_or(full_mask, m)

        if self.dilate > 0:
            k = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (self.dilate * 2 + 1, self.dilate * 2 + 1)
            )
            full_mask = cv2.dilate(full_mask, k, iterations=1)

        flag = cv2.INPAINT_TELEA if self.method == "telea" else cv2.INPAINT_NS
        return cv2.inpaint(img, full_mask, 3, flag)

    def _box_mask(self, img: np.ndarray, tb: TextBox) -> np.ndarray:
        x0, y0, x1, y1 = tb.rect
        # 外扩一点，避免文字边缘残留
        pad = 2
        x0 = max(0, x0 - pad)
        y0 = max(0, y0 - pad)
        x1 = min(img.shape[1], x1 + pad)
        y1 = min(img.shape[0], y1 + pad)
        roi = img[y0:y1, x0:x1]
        if roi.size == 0:
            return np.zeros(img.shape[:2], dtype=np.uint8)

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        # Otsu 自动阈值
        _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # 判断文字是深色的还是浅色的：像素少的那一边视为文字
        dark = int((bw == 0).sum())
        light = int((bw == 255).sum())
        if dark <= light:
            ink = (bw == 0).astype(np.uint8) * 255
        else:
            ink = (bw == 255).astype(np.uint8) * 255

        box_mask = np.zeros(img.shape[:2], dtype=np.uint8)
        box_mask[y0:y1, x0:x1] = ink
        return box_mask


# ---------------------------------------------------------------- 翻译


class OllamaTranslator:
    """通过 Ollama 本地 API 翻译。默认使用 Hy-MT2 的官方提示词模板。"""

    def __init__(
        self,
        model: str = "maternion/hy-mt2:1.8b",
        host: str = "http://127.0.0.1:11434",
        temperature: float = 0.7,
        top_p: float = 0.6,
        top_k: int = 20,
        repeat_penalty: float = 1.05,
        num_predict: int = 1024,
        timeout: int = 180,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.options = {
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "repeat_penalty": repeat_penalty,
            "num_predict": num_predict,
        }
        self.timeout = timeout

    @staticmethod
    def _session():
        """本地 127.0.0.1 直连，绕开系统代理环境变量（否则会 502）。"""
        import requests

        s = requests.Session()
        s.trust_env = False  # 关键：忽略 HTTP(S)_PROXY 环境变量
        return s

    def available(self) -> bool:
        s = self._session()
        try:
            r = s.get(f"{self.host}/api/tags", timeout=8)
            if r.status_code != 200:
                return False
            names = [m.get("name", "") for m in r.json().get("models", [])]
            return any(self.model.split(":")[0] in n for n in names)
        except Exception:
            return False

    def translate(self, text: str, src: str, tgt: str) -> str:
        return self.translate_batch([text], src, tgt)[0]

    def translate_batch(self, texts: List[str], src: str, tgt: str) -> List[str]:
        """逐条翻译（官方模板，最稳）：1.8B 很快，逐条质量远好于批量对齐。"""
        if not texts:
            return []
        return [self._safe_single(t, src, tgt) for t in texts]

    def _safe_single(self, text: str, src: str, tgt: str) -> str:
        tgt_name = LANG_NAMES.get(tgt, tgt)
        src_name = LANG_NAMES.get(src, src)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"将以下文本从{src_name}翻译为{tgt_name}，"
                        f"注意只需要输出翻译后的结果，不要额外解释：\n\n{text}"
                    ),
                }
            ],
            "stream": False,
            "options": self.options,
        }
        s = self._session()
        try:
            r = s.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout)
            r.raise_for_status()
            return r.json().get("message", {}).get("content", "").strip()
        except Exception:
            return ""

    @staticmethod
    def _align(raw: str, texts: List[str]) -> List[str]:
        """把模型输出按行数对齐回输入条数。"""
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        # 去掉可能的编号前缀
        lines = [re.sub(r"^\s*[\d]+[.、)\]]\s*", "", ln) for ln in lines]
        out = list(lines[: len(texts)])
        # 少了就补空，多了就截断
        while len(out) < len(texts):
            out.append("")
        return out


# ---------------------------------------------------------------- 嵌字渲染


class TextRenderer:
    """把译文排回原位置：自动字号、自动换行、描边、居中，支持竖排。"""

    def __init__(
        self,
        font_path: Optional[str] = None,
        vertical: bool = False,
        color: Tuple[int, int, int] = (0, 0, 0),
        stroke_color: Tuple[int, int, int] = (255, 255, 255),
        stroke_width_ratio: float = 0.06,
        padding: float = 0.06,
    ):
        self.font_path = font_path
        self.vertical = vertical
        self.color = color
        self.stroke_color = stroke_color
        self.stroke_width_ratio = stroke_width_ratio
        self.padding = padding

    # ---- 文本度量工具 ----

    @staticmethod
    def _text_size(draw, text, font) -> Tuple[int, int]:
        box = draw.textbbox((0, 0), text, font=font)
        return box[2] - box[0], box[3] - box[1]

    def _wrap(self, text: str, font, max_w: int, draw) -> List[str]:
        """按字符/单词换行，兼容中英日混排。"""
        # 先把英文单词和可断行字符切分成 token
        tokens = re.findall(r"[A-Za-z0-9'\-]+|\s+|[^\sA-Za-z0-9]", text)
        lines: List[str] = []
        cur = ""
        for tk in tokens:
            if tk.strip() == "" and not cur:
                continue
            probe = cur + tk
            w, _ = self._text_size(draw, probe, font)
            if w <= max_w or not cur:
                cur = probe
            else:
                # 禁则回退：行尾数字(含中文数字)不要和后面的量词拆开（如 "三年"）
                moved = ""
                while cur and (cur[-1].isdigit() or cur[-1] in "零一二两三四五六七八九十百千万亿") \
                        and tk and not tk[0].isascii():
                    moved = cur[-1] + moved
                    cur = cur[:-1]
                if moved:
                    lines.append(cur.rstrip())
                    cur = moved + (tk.lstrip() if tk.strip() else "")
                else:
                    lines.append(cur.rstrip())
                    cur = tk.lstrip() if tk.strip() else ""
        if cur.strip():
            lines.append(cur.rstrip())
        return lines or [text]

    def _fit(self, tb: TextBox, text: str, draw, img_w: int, img_h: int):
        """二分查找能塞进文本框的最大字号，返回 (font, lines)。"""
        max_w = max(8, int(tb.width * (1 - 2 * self.padding)))
        max_h = max(8, int(tb.height * (1 - 2 * self.padding)))
        hi = max(8, int(tb.height * 0.95))
        lo = 6
        best_font = pick_font(lo, self.font_path)
        best_lines = [text]

        while lo <= hi:
            mid = (lo + hi) // 2
            font = pick_font(mid, self.font_path)
            lines = self._wrap(text, font, max_w, draw)
            # 行高按字号倍数估算
            lh = int(mid * 1.35)
            total_h = lh * len(lines)
            widest = max((self._text_size(draw, ln, font)[0] for ln in lines), default=0)
            if total_h <= max_h and widest <= max_w:
                best_font, best_lines = font, lines
                lo = mid + 1
            else:
                hi = mid - 1
        return best_font, best_lines

    # ---- 主入口 ----

    def render(self, img: np.ndarray, text_boxes: List[TextBox]) -> np.ndarray:
        if not text_boxes:
            return img
        pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).convert("RGB")
        draw = ImageDraw.Draw(pil)
        img_w, img_h = pil.size

        for tb in text_boxes:
            if not tb.translation:
                continue
            # 深色背景自适应：暗底用白字黑描边，亮底用黑字白描边
            if self._is_dark_bg(img, tb):
                color, stroke = (245, 245, 245), (10, 10, 10)
            else:
                color, stroke = self.color, self.stroke_color
            font, lines = self._fit(tb, tb.translation, draw, img_w, img_h)
            x0, y0, x1, y1 = tb.rect
            stroke_w = max(1, int(font.size * self.stroke_width_ratio))

            if self.vertical:
                self._draw_vertical(draw, lines, font, x0, y0, x1, y1, stroke_w, color, stroke)
            else:
                self._draw_horizontal(draw, lines, font, x0, y0, x1, y1, stroke_w, color, stroke)

        return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

    @staticmethod
    def _is_dark_bg(img: np.ndarray, tb: TextBox) -> bool:
        """判断文字框区域的背景亮度（取框内像素中位数）。"""
        x0, y0, x1, y1 = tb.rect
        h, w = img.shape[:2]
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(w, x1)
        y1 = min(h, y1)
        roi = img[y0:y1, x0:x1]
        if roi.size == 0:
            return False
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        # 擦字后框内主要是背景色，中位数即背景亮度
        return float(np.median(gray)) < 110

    def _draw_horizontal(self, draw, lines, font, x0, y0, x1, y1, stroke_w,
                         color=None, stroke=None):
        lh = int(font.size * 1.35)
        total_h = lh * len(lines)
        cy = (y0 + y1) // 2
        top = cy - total_h // 2
        color = color or self.color
        stroke = stroke or self.stroke_color
        for i, ln in enumerate(lines):
            w, _ = self._text_size(draw, ln, font)
            x = x0 + (x1 - x0 - w) // 2
            y = top + i * lh
            draw.text(
                (x, y),
                ln,
                font=font,
                fill=color,
                stroke_width=stroke_w,
                stroke_fill=stroke,
            )

    def _draw_vertical(self, draw, lines, font, x0, y0, x1, y1, stroke_w,
                       color=None, stroke=None):
        """竖排：列从右往左，列内自上而下。"""
        color = color or self.color
        stroke = stroke or self.stroke_color
        box_h = y1 - y0
        box_w = x1 - x0
        col_h = max(1, box_h - int(box_h * 2 * self.padding))
        max_cols = max(1, int(box_w / (font.size * 1.15)))
        if max_cols < 1:
            max_cols = 1

        # 先把所有字符按列、列内按行排好
        cols: List[List[str]] = [[] for _ in range(max_cols)]
        ci = 0
        for ln in lines:
            for ch in ln:
                if ch.strip() == "" and ch != "　":
                    ch = " "
                cols[ci % max_cols].append(ch)
                if len(cols[ci % max_cols]) * font.size >= col_h:
                    ci += 1

        # 从右往左画列
        x_cursor = x1 - int(font.size * 0.15)
        for col in cols:
            if not col:
                continue
            y_cursor = y0 + int(box_h * self.padding)
            for ch in col:
                if ch == " ":
                    y_cursor += int(font.size * 0.5)
                    continue
                # 竖排标点旋转处理（简化：直接竖着放）
                draw.text(
                    (x_cursor - font.size // 2, y_cursor),
                    ch,
                    font=font,
                    fill=color,
                    stroke_width=stroke_w,
                    stroke_fill=stroke,
                )
                y_cursor += int(font.size * 1.05)
            x_cursor -= int(font.size * 1.15)
            if x_cursor < x0:
                break
