"""Synthetic near-duplicate comparison -> durable review queue; no real OCR/PII."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from rag.ingest.near_duplicate import ComparisonDocument, DEFAULT_CONFIG, NearDuplicateDetector
from rag.models.content import Locator, SafeBlock
from rag.quality.review_queue import SQLiteReviewService
from rag.versioning.repository import VersionRepository


def run_demo(database: Path, threshold: float = .85) -> dict:
    common = ("Điều 3. Mức phí dịch vụ áp dụng cho khách hàng cá nhân là 100.000 đồng mỗi tháng. "
              "Mức phí đã bao gồm thuế và được thanh toán vào ngày đầu tiên của tháng tiếp theo.")
    texts = {"a": common, "b": common.replace("100.000", "120.000"),
             "c": "Cây xanh hấp thụ ánh sáng để quang hợp và tạo ra oxy."}
    documents = []
    for name, text in texts.items():
        # Fixture is known not to contain PII. This is not a real masker.
        block = SafeBlock(block_id=f"block-{name}", processing_id=f"processing-{name}",
                          version_id=f"version-{name}", order=0, kind="paragraph", text=text, origin="native",
                          locator=Locator(source_id=f"source-{name}", page=1), masking_config_id="fixture-no-pii-v1")
        documents.append(ComparisonDocument(document_id=f"document-{name}", version_id=block.version_id,
                         processing_id=block.processing_id, blocks=(block,), masking_config_id=block.masking_config_id,
                         coverage="complete"))
    config = replace(DEFAULT_CONFIG, threshold=threshold)
    results = NearDuplicateDetector().scan(documents, config=config)
    queue = SQLiteReviewService(VersionRepository(database))
    reviews = queue.enqueue(tuple(result.issue for result in results if result.issue is not None))
    return {
        "mode": "synthetic masked text; lexical comparison only; no source deletion or version approval",
        "threshold": threshold,
        "comparisons": [{"left": result.left[1], "right": result.right[1], "similarity": result.similarity,
                         "classification": result.classification} for result in results],
        "review_candidates": len(reviews), "open_review_count": len(queue.list_items()),
        "evidence": [detail.issues[0].safe_evidence for item in reviews for detail in (queue.get(item.review_id),)],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--threshold", type=float, default=.85)
    args = parser.parse_args()
    if args.database:
        report = run_demo(args.database, args.threshold)
    else:
        with TemporaryDirectory(prefix="near-duplicate-") as folder:
            report = run_demo(Path(folder) / "reviews.sqlite", args.threshold)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
