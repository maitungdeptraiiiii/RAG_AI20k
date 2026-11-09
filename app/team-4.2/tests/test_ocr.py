"""W02-02c phần A — OCR trong pipeline (Gemini 3.5 Flash-Lite + Tesseract confidence). Không gọi mạng."""

import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from rag.config import Settings
from rag.ingest.loaders import OCRPage, TablePage, UnsupportedSourceError, load_image, load_pdf, load_source
from rag.ingest.ocr import (
    DEFAULT_MODEL,
    PROMPT,
    GeminiOCREngine,
    OCRBudgetExceeded,
    OCRPageResult,
    TesseractConfidence,
    split_ocr_markdown,
)
from rag.pipeline import RAGPipeline, make_ocr_engine

ROOT = Path(__file__).resolve().parents[3]
SCANS = ROOT / "data/team-4.2/fixtures/raw/scans"

OCR_MD = """# NGHỊ ĐỊNH SỐ 10/2026/NĐ-CP

## Điều 1. Phạm vi điều chỉnh
Nghị định này quy định về **tiếp nhận hồ sơ** điện tử. Liên hệ 0912 345 678.

Bảng 1. Mức phí
Đơn vị: nghìn đồng
<table><thead><tr><th rowspan="2">Thủ tục</th><th colspan="2">Mức phí</th></tr>
<tr><th>Trực tiếp</th><th>Trực tuyến</th></tr></thead>
<tr><td>Cấp bản sao</td><td>20</td><td>10</td></tr></table>

Điều 2. Hiệu lực
Có hiệu lực từ ngày 01/01/2026."""


def _image(text: str = "Dieu 1") -> Image.Image:
    img = Image.new("RGB", (400, 120), "white")
    ImageDraw.Draw(img).text((10, 40), text, fill="black")
    return img


def _resp(content: str, *, finish="stop", native=None, cost=0.0016):
    return {"model": DEFAULT_MODEL, "usage": {"prompt_tokens": 1300, "completion_tokens": 400, "cost": cost},
            "choices": [{"finish_reason": finish, "native_finish_reason": native, "message": {"content": content}}]}


class _Transport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.bodies: list[dict] = []

    def __call__(self, url, body, headers):
        self.bodies.append(body)
        return self.responses.pop(0)


class _FakeOCR:
    """Engine giả cho loader/pipeline: trả Markdown cố định, đếm số trang đã OCR."""

    name = "fake"

    def __init__(self, text=OCR_MD, issues=()):
        self.text, self.issues, self.calls = text, issues, 0

    def ocr_image(self, image):
        self.calls += 1
        return OCRPageResult(self.text, self.issues, {"engine": "fake", "cost": 0.001})


# --- Markdown + bảng HTML ------------------------------------------------------------------

def test_split_markdown_extracts_table_with_spans_caption_unit_and_page():
    text, tables = split_ocr_markdown(OCR_MD, source_name="nd.pdf", page=3)
    assert "<table" not in text and "#" not in text and "**" not in text
    assert "\nĐiều 1. Phạm vi điều chỉnh\n" in f"\n{text}\n"        # chunker nhận ra Điều ở đầu dòng
    (table,) = tables
    assert table.page == 3 and table.caption == "Bảng 1. Mức phí" and table.unit == "nghìn đồng"
    assert table.headers == (("Thủ tục", "Mức phí", "Mức phí"), ("Thủ tục", "Trực tiếp", "Trực tuyến"))
    assert table.rows == (("Cấp bản sao", "20", "10"),)
    assert table.column_labels() == ("Thủ tục", "Mức phí / Trực tiếp", "Mức phí / Trực tuyến")


# --- GeminiOCREngine (transport giả) ------------------------------------------------------------

def test_gemini_request_uses_benchmarked_prompt_and_cache(tmp_path):
    transport = _Transport(_resp("Điều 1. Nội dung"))
    engine = GeminiOCREngine(api_key="k", cache_dir=tmp_path, quality=None, transport=transport)
    first = engine.ocr_image(_image())
    second = engine.ocr_image(_image())                     # cùng ảnh -> cache, không gọi lại
    assert len(transport.bodies) == 1
    body = transport.bodies[0]
    assert body["model"] == "google/gemini-3.5-flash-lite" and body["temperature"] == 0
    assert body["reasoning"] == {"effort": "minimal"}
    assert body["messages"][0]["content"][0]["text"] == PROMPT
    assert body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert first.text == second.text == "Điều 1. Nội dung" and second.meta["cached"] is True
    assert engine.spent_usd() == pytest.approx(0.0016)


def test_cost_cap_stops_before_calling_api(tmp_path):
    transport = _Transport(_resp("a", cost=0.6), _resp("b", cost=0.6))
    engine = GeminiOCREngine(api_key="k", cache_dir=tmp_path, cost_cap_usd=0.5, quality=None, transport=transport)
    engine.ocr_image(_image("trang 1"))
    with pytest.raises(OCRBudgetExceeded):
        engine.ocr_image(_image("trang 2"))
    assert len(transport.bodies) == 1


@pytest.mark.parametrize("resp, expected", [
    (_resp("Điều 1. Rõ ràng"), ()),
    (_resp("Điều 1. [không đọc được] đồng"), ("ocr.low_confidence",)),
    (_resp("Một phần trang", finish="stop", native="RECITATION"), ("ocr.truncated",)),
    (_resp("Dài quá", finish="length"), ("ocr.truncated",)),
    (_resp(""), ("ocr.empty",)),
])
def test_quality_issues_from_gemini_output(resp, expected):
    engine = GeminiOCREngine(api_key="k", quality=None, transport=_Transport(resp))
    assert engine.ocr_image(_image()).issues == expected


def test_expired_key_fails_fast_without_retry():
    import urllib.error

    calls = []

    def expired(url, body, headers):
        calls.append(1)
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {},
                                     io.BytesIO(b'{"error":{"message":"API key expired.","code":401}}'))

    from rag.ingest.ocr import OCRFatalError

    engine = GeminiOCREngine(api_key="k", quality=None, transport=expired, sleep=lambda s: None)
    with pytest.raises(OCRFatalError, match="401.*expired"):
        engine.ocr_image(_image())
    assert len(calls) == 1


def test_transient_error_is_retried_then_succeeds():
    transport = _Transport({"error": {"code": 429}}, _resp("ok"))
    engine = GeminiOCREngine(api_key="k", quality=None, transport=transport, sleep=lambda s: None)
    assert engine.ocr_image(_image()).text == "ok" and len(transport.bodies) == 2


# --- Tesseract confidence (ngưỡng chọn trên dev: w02-23 kém, w02-24 rõ) ----------------------

tesseract = TesseractConfidence()


@pytest.mark.skipif(not tesseract.available(), reason="máy không có Tesseract")
@pytest.mark.parametrize("name, low", [("23_legal_flow_medium.png", True), ("24_legal_fee_table_clear.png", False)])
def test_tesseract_threshold_on_dev_fixtures(name, low):
    mean, words = tesseract.measure(Image.open(SCANS / name))
    assert tesseract.is_low(mean, words) is low


# --- loader -----------------------------------------------------------------------------------

def _mixed_pdf(path: Path) -> Path:
    """Trang 1 có text layer, trang 2 chỉ là ảnh (scan)."""
    import fitz

    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Dieu 1. Trang co text layer that su day du.")
    page = doc.new_page()
    buf = io.BytesIO()
    _image("scan").save(buf, "PNG")
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(path)
    return path


def test_pdf_ocr_only_pages_without_text_layer(tmp_path):
    ocr = _FakeOCR()
    pages = load_pdf(_mixed_pdf(tmp_path / "mix.pdf"), ocr=ocr)
    assert ocr.calls == 1
    assert type(pages[0]).__name__ == "Page" and pages[0].page == 1
    ocr_pages = [p for p in pages if isinstance(p, OCRPage)]
    tables = [p for p in pages if isinstance(p, TablePage)]
    assert [p.page for p in ocr_pages] == [2] and ocr_pages[0].ocr_engine == "fake"
    assert len(tables) == 1 and tables[0].page == 2 and tables[0].table.page == 2


def test_pdf_without_ocr_keeps_baseline_behaviour(tmp_path):
    pages = load_pdf(_mixed_pdf(tmp_path / "mix.pdf"))
    assert [p.is_empty for p in pages] == [False, True] and not any(isinstance(p, OCRPage) for p in pages)


def test_image_requires_ocr_engine():
    with pytest.raises(UnsupportedSourceError, match="OCR_ENGINE=gemini"):
        load_image(SCANS / "25_legal_text_clear.png")
    pages = load_source(SCANS / "25_legal_text_clear.png", ocr=_FakeOCR())
    assert isinstance(pages[0], OCRPage) and pages[0].page == 1


# --- pipeline -----------------------------------------------------------------------------------

class _NoLLM:
    model_id = "none"

    def complete(self, system, user):
        raise AssertionError("ingest không gọi LLM")


def _pipeline(ocr):
    from rag.index.bm25_index import BM25Index
    from rag.index.embedder import HashEmbedder
    from rag.index.store import ChunkStore
    from rag.index.vector_index import VectorIndex
    from rag.retrieve.hybrid import HybridRetriever

    return RAGPipeline(ChunkStore(), HybridRetriever(BM25Index(), VectorIndex(HashEmbedder(dim=64))), _NoLLM(), ocr=ocr)


def test_pipeline_ingests_scan_pdf_with_page_citation_masking_and_review_issue():
    pipeline = _pipeline(_FakeOCR(issues=("ocr.low_confidence",)))
    report = pipeline.ingest(SCANS / "29_legal_text_blurred_scan.pdf")
    chunks = pipeline.store.by_doc(report.doc_id)
    assert report.ocr_pages == [1] and report.n_tables == 1 and report.n_chunks == len(chunks) >= 2
    assert all(c.page_start == 1 for c in chunks)                       # citation trỏ đúng trang
    assert any(c.section == "table:0" and "| Thủ tục | Mức phí / Trực tiếp |" in c.text for c in chunks)
    assert any((c.section or "").startswith("Điều 1") for c in chunks)
    assert "0912 345 678" not in "\n".join(c.text for c in chunks) and report.pii_counts == {"phone": 1}
    assert report.needs_review
    assert report.quality_issues[0]["type"] == "ocr.low_confidence" and report.quality_issues[0]["location"] == "page:1"


def test_pipeline_without_ocr_still_rejects_scan_pdf():
    with pytest.raises(ValueError, match="OCR"):
        _pipeline(None).ingest(SCANS / "29_legal_text_blurred_scan.pdf")


# --- cấu hình --------------------------------------------------------------------------------

def test_settings_ocr_and_legacy_openrouter_key():
    s = Settings.from_env({"OCR_ENGINE": "gemini", "openrouter ": "sk-test"})
    assert s.ocr_engine == "gemini" and s.openrouter_api_key == "sk-test"
    assert s.ocr_model == "google/gemini-3.5-flash-lite"
    engine = make_ocr_engine(s)
    assert isinstance(engine, GeminiOCREngine) and engine.cache_dir == s.cache_dir / "ocr"
    assert make_ocr_engine(Settings.from_env({})) is None
    with pytest.raises(ValueError):
        Settings.from_env({"OCR_ENGINE": "tesseract"})
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        make_ocr_engine(Settings.from_env({"OCR_ENGINE": "gemini"}))


def test_pipeline_saves_full_extracted_text_masked(tmp_path):
    import json

    pipeline = _pipeline(_FakeOCR())
    pipeline.extracted_dir = tmp_path / "extracted"
    report = pipeline.ingest(SCANS / "29_legal_text_blurred_scan.pdf")
    data = json.loads((tmp_path / "extracted" / f"{report.doc_id}.json").read_text(encoding="utf-8"))
    assert data["source"] == "29_legal_text_blurred_scan.pdf"
    kinds = [p["kind"] for p in data["pages"]]
    assert kinds == [d["kind"] for d in report.pages_detail] and "ocr" in kinds and "table" in kinds
    full = chr(10).join(p["text"] for p in data["pages"])
    assert "Phạm vi điều chỉnh" in full and "0912 345 678" not in full and "[PHONE_1]" in full


def test_reingest_of_old_document_backfills_extracted_text_without_reindexing(tmp_path):
    pipeline = _pipeline(_FakeOCR())
    first = pipeline.ingest(SCANS / "29_legal_text_blurred_scan.pdf")      # extracted_dir chưa bật
    n_chunks = len(pipeline.store)
    pipeline.extracted_dir = tmp_path / "extracted"
    again = pipeline.ingest(SCANS / "29_legal_text_blurred_scan.pdf")
    assert again.skipped and len(pipeline.store) == n_chunks
    assert (tmp_path / "extracted" / f"{first.doc_id}.json").is_file()
