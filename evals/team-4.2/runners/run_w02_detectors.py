"""Chạy pipeline ingest thật trên fixtures tuần 2 và xuất findings (KHÔNG đọc labels).

Đây là eval adapter mỏng: ingest từng fixture theo thứ tự trong ``manifest.jsonl`` vào một
pipeline mới (ChunkStore trong RAM, HashEmbedder, không gọi mạng), rồi ghi mỗi fixture một dòng:

    {"fixture_id": "w02-20", "issue_codes": ["numeric.sum_mismatch"], "ingest_status": "...", ...}

Detector đang nối vào ``RAGPipeline.ingest``: PII (``pii.detected``), kiểm tra bảng/số liệu
(``numeric.*``, ``table.*``), exact dedup theo doc_id (``skipped``) và — với ``--ocr gemini`` — OCR
(``ocr.*``: Gemini 3.5 Flash-Lite đọc chữ, Tesseract local cho confidence). Near-dup, version,
flow chưa có trong pipeline nên các mã đó sẽ là bỏ sót (FN) — được báo riêng, không giấu.

``--ocr gemini`` gửi 5 ảnh fixture scan (public / giả lập) lên OpenRouter; cache tại
``data/team-4.2/w02/cache/ocr`` nên chạy lại không tốn thêm; trần chi phí ``--ocr-cap`` (mặc định 0.10 USD).

Chạy tại gốc repo:

    python evals/team-4.2/runners/run_w02_detectors.py --ocr gemini --out evals/team-4.2/results/w02-quality/findings.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "app/team-4.2/src"))

from rag.index.bm25_index import BM25Index  # noqa: E402
from rag.index.embedder import HashEmbedder  # noqa: E402
from rag.index.store import ChunkStore  # noqa: E402
from rag.index.vector_index import VectorIndex  # noqa: E402
from rag.ingest.loaders import UnsupportedSourceError  # noqa: E402
from rag.ingest.ocr import OCRError, OCRFatalError  # noqa: E402
from rag.pipeline import RAGPipeline  # noqa: E402
from rag.retrieve.hybrid import HybridRetriever  # noqa: E402

FIXTURES = ROOT / "data/team-4.2/fixtures"
# Tham số bảng là quyết định cấu hình parser cho từng nguồn, không lấy từ labels
HEADER_ROWS = {"w02-19": 2}


class _NoLLM:
    model_id = "none"

    def complete(self, system: str, user: str) -> str:   # ingest không gọi LLM
        raise RuntimeError("không dùng LLM khi chạy detector")


def _loader_for(fixture_id: str):
    from rag.ingest.loaders import load_source, load_table
    from rag.ingest.tables import TABLE_SUFFIXES

    def load(value, source=None, ocr=None):
        if Path(value).suffix.lower() in TABLE_SUFFIXES and fixture_id in HEADER_ROWS:
            return load_table(value, source=source, header_rows=HEADER_ROWS[fixture_id])
        return load_source(value, source=source, ocr=ocr)

    return load


def make_ocr(kind: str, cap: float):
    if kind == "none":
        return None
    from rag.config import Settings
    from rag.ingest.ocr import GeminiOCREngine, TesseractConfidence

    s = Settings.load()
    if not s.openrouter_api_key:
        raise SystemExit("--ocr gemini cần OPENROUTER_API_KEY (hoặc openrouter=) trong app/team-4.2/.env")
    return GeminiOCREngine(api_key=s.openrouter_api_key, model=s.ocr_model, cost_cap_usd=cap,
                           cache_dir=ROOT / "data/team-4.2/w02/cache/ocr",
                           quality=TesseractConfidence(cmd=s.tesseract_cmd, min_confidence=s.ocr_min_confidence))


def run(manifest: list[dict], ocr=None) -> list[dict]:
    pipeline = RAGPipeline(ChunkStore(), HybridRetriever(BM25Index(), VectorIndex(HashEmbedder(dim=64))), _NoLLM(),
                           ocr=ocr)
    rows: list[dict] = []
    for item in manifest:
        fixture_id = item["fixture_id"]
        path = FIXTURES / item["source_path"]
        pipeline._loader = _loader_for(fixture_id)
        row: dict = {"fixture_id": fixture_id, "issue_codes": []}
        try:
            report = pipeline.ingest(path)
        except OCRFatalError as error:      # key hết hạn / hết credit: mọi trang OCR sau cũng hỏng
            raise SystemExit(f"Dừng: {error}. Cập nhật OPENROUTER_API_KEY trong app/team-4.2/.env.") from error
        except (UnsupportedSourceError, ValueError, OCRError) as error:
            # PNG/PDF scan chưa có OCR trong pipeline: ghi lý do, không giả là phát hiện được
            row.update(ingest_status="failed", error=type(error).__name__, detail=str(error)[:200])
            rows.append(row)
            continue
        codes = sorted({issue["type"] for issue in report.quality_issues})
        if report.pii_counts:
            codes.append("pii.detected")
        row.update(
            issue_codes=sorted(set(codes)),
            ingest_status="duplicate" if report.skipped else ("needs_review" if report.needs_review else "activated"),
            dedup_action="link_existing" if report.skipped else "continue",
            new_chunk_count=0 if report.skipped else report.n_chunks,
            n_tables=report.n_tables,
            ocr_pages=report.ocr_pages,
            ocr_cost_usd=report.ocr_cost_usd,
            pii_counts=report.pii_counts,
            issues=report.quality_issues,
        )
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=FIXTURES / "manifest.jsonl")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ocr", choices=["none", "gemini"], default="none")
    parser.add_argument("--ocr-cap", type=float, default=0.10, help="trần chi phí OCR (USD) cho lần chạy này")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    manifest = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = run(manifest, make_ocr(args.ocr, args.ocr_cap))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    cost = sum(r.get("ocr_cost_usd") or 0 for r in rows)
    print(f"{len(rows)} fixtures; status {dict(Counter(r['ingest_status'] for r in rows))}; "
          f"OCR {args.ocr} cost {cost:.4f} USD; wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
