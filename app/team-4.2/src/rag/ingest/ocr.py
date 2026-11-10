"""OCR cho PDF scan / ảnh — W02-02c phần A (OCR trong pipeline).

    GeminiOCREngine      Gemini 3.5 Flash-Lite qua OpenRouter (mặc định), prompt ``v1`` đã benchmark
    TesseractConfidence  tín hiệu chất lượng chạy LOCAL: Gemini không trả confidence, nên dùng
                         confidence trung bình của Tesseract trên cùng ảnh để gắn ``ocr.low_confidence``
    split_ocr_markdown   output Markdown + <table> HTML -> text sạch + ParsedTable (chunk như bảng W02-02b)

Lý do chọn model (evals/team-4.2/results/w02-ocr-gemini-compare): trên 159 trang tiếng Việt CER 3.88 %,
sai dấu 0.19 %, "Điều/Khoản N" đúng 100 %, không RECITATION trên trang đã chặn 2.5 Flash,
~0.0016 USD/trang. ``gemini-2.5-flash`` có lịch ngừng trên Gemini API.

Nguyên tắc:
- OCR theo TỪNG TRANG: trang PDF có text layer dùng luôn, chỉ trang không có text mới OCR.
- Cache theo (sha256 ảnh, model, prompt_version): ingest lại không trả tiền lần hai.
- Ngưỡng chi phí cứng (``cost_cap_usd``) cộng dồn từ ``cost_log.jsonl``; vượt thì dừng, không gọi tiếp.
- Không sửa chữ: prompt bắt chép nguyên văn, chỗ mờ ghi ``[không đọc được]``.
- HẠN CHẾ: ảnh được gửi ra ngoài (OpenRouter -> Google) TRƯỚC khi mask PII; text OCR được mask sau
  đó như mọi trang khác. Chỉ bật cho tài liệu công khai (văn bản luật) — không dùng cho hồ sơ khách.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-3.5-flash-lite"
# 3.x không tắt được reasoning ("Reasoning is mandatory") -> mức thấp nhất; đo thực tế 0 reasoning token.
REASONING = {"google/gemini-2.5-flash": {"enabled": False}}
REASONING_DEFAULT = {"effort": "minimal"}

PROMPT_VERSION = "v1"
PROMPT = """Bạn là công cụ OCR. Chép lại NGUYÊN VĂN toàn bộ chữ trong ảnh tài liệu, theo đúng thứ tự đọc.
Quy tắc:
- Không sửa chính tả, không sửa số, không thêm, không bỏ, không tóm tắt, không dịch. Giữ đúng dấu tiếng Việt.
- Chép cả quốc hiệu, tiêu ngữ, số hiệu, nơi nhận, chữ ký, chữ trong con dấu nếu đọc được.
- Định dạng Markdown: tiêu đề dùng #, ##; danh sách giữ nguyên ký hiệu gốc.
- Bảng: viết bằng HTML <table> (dùng rowspan/colspan nếu có ô gộp).
- Công thức toán: LaTeX trong $...$ hoặc $$...$$.
- Hình ảnh không có chữ: bỏ qua.
- Chỗ không đọc được: ghi [không đọc được].
Chỉ trả về nội dung đã chép, không giải thích, không bọc trong ```."""
"""Giống hệt prompt ``v1`` trong evals/team-4.2/runners/ocr_bench/run_engine.py — số benchmark áp dụng được."""

UNREADABLE = "[không đọc được]"

# Mã issue (khớp labels.jsonl)
OCR_LOW_CONFIDENCE = "ocr.low_confidence"
OCR_TRUNCATED = "ocr.truncated"
OCR_EMPTY = "ocr.empty"

Transport = Callable[[str, dict, dict], dict]


class OCRError(RuntimeError):
    pass


class OCRBudgetExceeded(OCRError):
    pass


class OCRFatalError(OCRError):
    """Lỗi không nên thử lại (401/402/403/404...)."""


@dataclass(frozen=True)
class OCRPageResult:
    text: str                                   # Markdown đã bỏ ``` , còn nguyên <table>
    issues: tuple[str, ...] = ()                # mã issue chất lượng
    meta: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


# ---------------------------------------------------------------------------
# Tín hiệu chất lượng local: Tesseract confidence
# ---------------------------------------------------------------------------


@dataclass
class TesseractConfidence:
    """Confidence trung bình theo từ của Tesseract (0–100) trên cùng ảnh.

    Ngưỡng 65 chọn trên split DEV của fixtures (w02-23 kém: 43.4, w02-24 rõ: 84.0); split test
    (w02-25/29/30) không dùng để chọn. Ít hơn ``min_words`` từ đọc được cũng tính là kém.
    """

    cmd: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    lang: str = "vie"
    min_confidence: float = 65.0
    min_words: int = 10

    def available(self) -> bool:
        return Path(self.cmd).is_file() or shutil.which(self.cmd) is not None

    def measure(self, image) -> tuple[float | None, int]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.png"
            image.convert("L").save(path)
            tsv = subprocess.run([self.cmd, str(path), "stdout", "-l", self.lang, "--psm", "3", "tsv"],
                                 capture_output=True, text=True, encoding="utf-8", timeout=120).stdout
        confs: list[float] = []
        for row in tsv.splitlines()[1:]:
            cols = row.split("\t")
            if len(cols) >= 12 and cols[0] == "5" and cols[11].strip() and float(cols[10]) >= 0:
                confs.append(float(cols[10]))
        return (round(sum(confs) / len(confs), 1) if confs else None), len(confs)

    def is_low(self, mean: float | None, words: int) -> bool:
        return mean is None or words < self.min_words or mean < self.min_confidence


# ---------------------------------------------------------------------------
# Gemini qua OpenRouter
# ---------------------------------------------------------------------------


def _http_post(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode("utf-8"), headers)
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.load(resp)


@dataclass
class GeminiOCREngine:
    api_key: str
    model: str = DEFAULT_MODEL
    cache_dir: Path | None = None
    cost_cap_usd: float = 1.0
    max_side: int = 1600                       # cạnh dài ảnh gửi đi (đủ đọc dấu, ít token) — như benchmark
    max_retries: int = 4
    quality: TesseractConfidence | None = field(default_factory=TesseractConfidence)
    transport: Transport = _http_post
    sleep: Callable[[float], None] = time.sleep
    name: str = "gemini"

    # --- chi phí + cache ---------------------------------------------------

    @property
    def _cost_log(self) -> Path | None:
        return self.cache_dir / "cost_log.jsonl" if self.cache_dir else None

    def spent_usd(self) -> float:
        log = self._cost_log
        if log is None or not log.exists():
            return 0.0
        return sum(json.loads(line).get("cost", 0) or 0 for line in log.read_text(encoding="utf-8").splitlines() if line)

    def _cache_path(self, sha: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"{sha[:24]}_{self.model.replace('/', '_')}_{PROMPT_VERSION}.json"

    # --- OCR ---------------------------------------------------------------

    def _encode(self, image) -> bytes:
        from PIL import Image

        img = image.convert("RGB")
        scale = self.max_side / max(img.size)
        if scale < 1:
            img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        return buf.getvalue()

    def _call(self, jpeg: bytes) -> dict:
        body = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 8192,
            "reasoning": REASONING.get(self.model, REASONING_DEFAULT),
            "usage": {"include": True},
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()}},
            ]}],
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        for attempt in range(self.max_retries + 1):
            try:
                try:
                    resp = self.transport(OPENROUTER_URL, body, headers)
                except urllib.error.HTTPError as error:
                    if error.code in (400, 401, 402, 403, 404):
                        # key hết hạn / sai, hết credit, model không tồn tại: thử lại vô ích
                        detail = error.read()[:300].decode("utf-8", "ignore")
                        raise OCRFatalError(f"OpenRouter HTTP {error.code}: {detail}") from error
                    raise
                if "error" in resp:
                    raise OCRError(f"OpenRouter: {str(resp['error'])[:200]}")
                choice = resp["choices"][0]
                if choice.get("finish_reason") == "error" and not choice.get("native_finish_reason"):
                    raise OCRError("lỗi tạm thời phía provider")          # retry, không cache
                return resp
            except OCRFatalError:
                raise
            except (urllib.error.URLError, TimeoutError, OCRError, KeyError, IndexError) as error:
                if attempt == self.max_retries:
                    raise OCRError(f"Gemini OCR lỗi sau {attempt + 1} lần: {error}") from error
                self.sleep(min(5 * 2 ** attempt, 60))
        raise OCRError("không tới đây")

    def ocr_image(self, image) -> OCRPageResult:
        """OCR một trang (PIL.Image). Có cache; tín hiệu chất lượng tính lại mỗi lần (local, rẻ)."""
        jpeg = self._encode(image)
        sha = hashlib.sha256(jpeg).hexdigest()
        cache = self._cache_path(sha)
        if cache is not None and cache.exists():
            data = json.loads(cache.read_text(encoding="utf-8"))
            text, meta = data["text"], {**data["meta"], "cached": True}
        else:
            if self.spent_usd() >= self.cost_cap_usd:
                raise OCRBudgetExceeded(f"Đã chạm ngưỡng chi phí OCR {self.cost_cap_usd} USD (OCR_COST_CAP_USD)")
            resp = self._call(jpeg)
            choice, usage = resp["choices"][0], resp.get("usage", {})
            text = re.sub(r"^```(?:markdown|md|html)?\n|\n```$", "", (choice["message"].get("content") or "").strip())
            meta = {
                "engine": self.name, "model": resp.get("model", self.model), "prompt_version": PROMPT_VERSION,
                "finish_reason": choice.get("finish_reason"), "native_finish_reason": choice.get("native_finish_reason"),
                "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
                "cost": usage.get("cost", 0) or 0, "date": time.strftime("%Y-%m-%d"), "image_sha256": sha,
            }
            if self.cache_dir is not None:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                with self._cost_log.open("a", encoding="utf-8") as log:   # type: ignore[union-attr]
                    log.write(json.dumps({k: meta[k] for k in ("model", "cost", "date", "image_sha256")}) + "\n")
                cache.write_text(json.dumps({"text": text, "meta": meta}, ensure_ascii=False), encoding="utf-8")  # type: ignore[union-attr]
        return OCRPageResult(text, self._issues(text, meta, image), meta)

    def _issues(self, text: str, meta: dict, image) -> tuple[str, ...]:
        issues: list[str] = []
        native = str(meta.get("native_finish_reason") or "").upper()
        if meta.get("finish_reason") not in ("stop", None) or native in ("RECITATION", "MAX_TOKENS", "SAFETY"):
            issues.append(OCR_TRUNCATED)
        if not text.strip():
            issues.append(OCR_EMPTY)
        low = UNREADABLE in text
        if self.quality is not None and self.quality.available():
            mean, words = self.quality.measure(image)
            meta["tesseract_confidence"], meta["tesseract_words"] = mean, words
            low = low or self.quality.is_low(mean, words)
        else:
            meta["tesseract_confidence"] = "unavailable"
        if low:
            issues.append(OCR_LOW_CONFIDENCE)
        return tuple(issues)


# ---------------------------------------------------------------------------
# Markdown + <table> -> text + bảng
# ---------------------------------------------------------------------------


class _TableHTML(HTMLParser):
    """<table> HTML -> lưới ô, mở rowspan/colspan bằng cách điền lại giá trị (như ô gộp XLSX)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[tuple[str, int, int]]] = []
        self.header_rows = 0
        self._cell: list[str] | None = None
        self._span = (1, 1)
        self._in_thead = False
        self._row_has_td = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "thead":
            self._in_thead = True
        elif tag == "tr":
            self.rows.append([])
            self._row_has_td = False
        elif tag in ("td", "th"):
            self._cell = []
            self._row_has_td |= tag == "td"
            self._span = (int(a.get("rowspan") or 1), int(a.get("colspan") or 1))
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag == "thead":
            self._in_thead = False
        elif tag in ("td", "th") and self._cell is not None and self.rows:
            self.rows[-1].append((" ".join("".join(self._cell).split()), *self._span))
            self._cell = None
        elif tag == "tr" and self.rows and (self._in_thead or not self._row_has_td) \
                and len(self.rows) == self.header_rows + 1:
            self.header_rows += 1          # hàng đầu toàn <th> hoặc nằm trong <thead>

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def grid(self) -> list[tuple[str, ...]]:
        filled: dict[tuple[int, int], str] = {}
        for r, row in enumerate(self.rows):
            c = 0
            for text, rowspan, colspan in row:
                while (r, c) in filled:
                    c += 1
                for dr in range(max(rowspan, 1)):
                    for dc in range(max(colspan, 1)):
                        filled[(r + dr, c + dc)] = text
                c += max(colspan, 1)
        if not filled:
            return []
        n_rows = max(r for r, _ in filled) + 1
        n_cols = max(c for _, c in filled) + 1
        return [tuple(filled.get((r, c), "") for c in range(n_cols)) for r in range(n_rows)]


_TABLE_RE = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)
_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_MD_EMPHASIS_RE = re.compile(r"(\*\*|__)(.+?)\1")


def clean_markdown(text: str) -> str:
    """Bỏ ký hiệu Markdown để chunker nhận ra 'Chương/Điều' ở đầu dòng như văn bản thường."""
    text = _MD_HEADING_RE.sub("", text)
    text = _MD_EMPHASIS_RE.sub(r"\2", text)
    return re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)


def split_ocr_markdown(text: str, *, source_name: str, page: int | None, first_index: int = 0):
    """Tách bảng HTML khỏi output OCR. Trả (text không còn bảng, list[ParsedTable]).

    Dòng ngay trên bảng dạng 'Bảng …' thành caption, dạng 'Đơn vị: …' thành đơn vị (như W02-02b).
    """
    from rag.ingest.tables import _CAPTION_RE, _UNIT_RE, _from_rows

    tables = []
    pieces: list[str] = []
    cursor = 0
    for match in _TABLE_RE.finditer(text):
        before = text[cursor:match.start()]
        lines = before.rstrip().split("\n")
        caption = unit = None
        for _ in range(2):                       # tối đa 2 dòng ngay trên bảng
            last = clean_markdown(lines[-1]).strip() if lines else ""
            if last and (m := _UNIT_RE.match(last)) and unit is None:
                unit = m.group("unit")
                lines.pop()
            elif last and _CAPTION_RE.match(last) and caption is None:
                caption = last
                lines.pop()
            else:
                break
        pieces.append("\n".join(lines) + "\n")
        parser = _TableHTML()
        parser.feed(match.group(0))
        grid = parser.grid()
        if grid:
            header_rows = min(max(parser.header_rows, 1), len(grid))
            try:
                table = _from_rows(grid, source_name, header_rows=header_rows, caption=caption, unit=unit,
                                   index=first_index + len(tables))
                from dataclasses import replace
                tables.append(replace(table, page=page))
            except ValueError:
                pieces.append(match.group(0))    # bảng hỏng: giữ nguyên text, không mất nội dung
        cursor = match.end()
    pieces.append(text[cursor:])
    return clean_markdown("".join(pieces)).strip(), tables


def render_pdf_page(pdf_page, zoom: float = 2.0):
    """Trang PyMuPDF -> PIL.Image (zoom 2x ~ 144 dpi)."""
    import fitz
    from PIL import Image

    pix = pdf_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return Image.open(io.BytesIO(pix.tobytes("png")))


__all__ = [
    "DEFAULT_MODEL",
    "OCR_EMPTY",
    "OCR_LOW_CONFIDENCE",
    "OCR_TRUNCATED",
    "PROMPT",
    "PROMPT_VERSION",
    "GeminiOCREngine",
    "OCRBudgetExceeded",
    "OCRError",
    "OCRPageResult",
    "TesseractConfidence",
    "clean_markdown",
    "render_pdf_page",
    "split_ocr_markdown",
]
