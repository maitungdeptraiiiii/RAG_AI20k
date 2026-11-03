"""Ingest tài liệu vào index (chạy tại gốc repo).

    python scripts/team-4.2/ingest.py data/team-4.2/raw/luat_lao_dong.pdf https://example.vn/bai-viet
    python scripts/team-4.2/ingest.py data/team-4.2/raw/          # mọi PDF/TXT/MD trong thư mục

Cùng tài liệu ingest lại thì bỏ qua (theo doc_id = hash nội dung).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from rag.config import Settings
from rag.ingest.loaders import PDF_SUFFIXES, TEXT_SUFFIXES, is_url
from rag.pipeline import RAGPipeline


def expand(inputs: list[str]) -> list[str]:
    out: list[str] = []
    for item in inputs:
        p = Path(item)
        if not is_url(item) and p.is_dir():
            out += sorted(str(f) for f in p.rglob("*") if f.suffix.lower() in PDF_SUFFIXES | TEXT_SUFFIXES)
        else:
            out.append(item)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="file PDF/TXT/MD, thư mục, hoặc URL")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    pipeline = RAGPipeline.from_settings(Settings.load())
    failed = 0
    for item in expand(args.inputs):
        try:
            r = pipeline.ingest(item)
        except Exception as e:  # noqa: BLE001 — báo lỗi từng tài liệu, ingest tiếp tài liệu khác
            failed += 1
            print(f"LỖI  {item}: {e}", file=sys.stderr)
            continue
        status = "BỎ QUA (đã có)" if r.skipped else "OK"
        empty = f", trang rỗng: {r.empty_pages}" if r.empty_pages else ""
        print(f"{status:15} {r.source}: {r.n_pages} trang, {r.n_chunks} chunk{empty}")
    print(f"Tổng: {len(pipeline.store)} chunk, {len(pipeline.store.docs())} tài liệu")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
