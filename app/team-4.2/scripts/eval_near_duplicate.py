"""Compare fixed-threshold baseline/v2; labels are used only AFTER prediction."""

from __future__ import annotations

import argparse
from dataclasses import replace
import inspect
import json
from pathlib import Path

from rag.ingest.checksum import canonical_checksum, file_checksum
from rag.ingest.near_duplicate import (
    BASELINE_CONFIG, DEFAULT_CONFIG, ComparisonDocument, ComparisonMetadata, NearDuplicateDetector,
)
from rag.models import Locator, SafeBlock, require, to_json_value

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = ROOT / "evals/team-4.2/datasets/near_duplicate/pairs.json"
DEFAULT_OUTPUT = ROOT / "evals/team-4.2/results/w02-near-duplicate/evaluation.json"


def comparison_document(value: dict) -> ComparisonDocument:
    identity = value["document_id"]
    data = value.get("metadata", {})
    metadata = ComparisonMetadata(external_key=data.get("external_key"), issuer=data.get("issuer"),
                                  scope=tuple(sorted(data.get("scope", {}).items())), confirmed=data.get("confirmed", False))
    block = SafeBlock(block_id=identity + ":block", processing_id=identity + ":processing", version_id=identity + ":version",
                       order=0, kind="paragraph", text=value["text"], origin="ocr" if value.get("ocr_confidence") is not None else "native",
                       locator=Locator(source_id=identity + ":source", page=1), masking_config_id="synthetic-no-pii-v1",
                       ocr_confidence=value.get("ocr_confidence"))
    return ComparisonDocument(document_id=identity, version_id=block.version_id, processing_id=block.processing_id,
                              blocks=(block,), masking_config_id=block.masking_config_id, coverage="complete", metadata=metadata)


def _metrics(rows):
    tp = sum(row["label_review"] and row["predicted_review"] for row in rows)
    fp = sum(not row["label_review"] and row["predicted_review"] for row in rows)
    fn = sum(row["label_review"] and not row["predicted_review"] for row in rows)
    tn = sum(not row["label_review"] and not row["predicted_review"] for row in rows)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    return {"pairs": len(rows), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": precision, "recall": recall,
            "review_count": tp + fp, "false_positive_ids": [row["id"] for row in rows if not row["label_review"] and row["predicted_review"]],
            "false_negative_ids": [row["id"] for row in rows if row["label_review"] and not row["predicted_review"]]}


def evaluate(dataset: Path, *, threshold: float = .85) -> dict:
    data = json.loads(dataset.read_text(encoding="utf-8"))
    require(data.get("schema_version") == "near-duplicate-eval.v1", "Unsupported evaluation fixture")
    pairs = data["pairs"]
    ids = set()
    documents_by_split = {"dev": set(), "test": set()}
    for pair in pairs:
        require(pair["id"] not in ids and pair["split"] in documents_by_split and type(pair["label_review"]) is bool,
                "Invalid pair ID/split/label")
        ids.add(pair["id"])
        documents_by_split[pair["split"]].update((pair["left"]["document_id"], pair["right"]["document_id"]))
    require(not documents_by_split["dev"] & documents_by_split["test"], "Source identity leaks between dev and test")
    report = {"synthetic": data.get("synthetic", False), "dataset_sha256": file_checksum(dataset),
              "detector_source_sha256": file_checksum(Path(inspect.getfile(NearDuplicateDetector))),
              "evaluator_source_sha256": file_checksum(Path(__file__)),
              "label_definition": data["label_definition"], "limitations": data.get("limitations", []),
              "selection": "Same fixed threshold, no automated threshold search. Synthetic fixture was visible during implementation; test is not a blind independent benchmark.", "policies": {}}
    detector = NearDuplicateDetector()
    for name, base in (("baseline", BASELINE_CONFIG), ("improved", DEFAULT_CONFIG)):
        config = replace(base, threshold=threshold)
        rows = []
        for pair in pairs:
            # Detector sees only source documents; never pair label/reason/split.
            result = detector.compare(comparison_document(pair["left"]), comparison_document(pair["right"]), config=config)
            rows.append({"id": pair["id"], "split": pair["split"], "label_review": pair["label_review"],
                         "predicted_review": result.issue is not None, "similarity": result.similarity,
                         "body_similarity": result.body_similarity, "classification": result.classification,
                         "priority": result.review_priority, "routing": result.routing_category,
                         "differences": list(result.difference_types), "reasons": list(result.decision_reasons)})
        report["policies"][name] = {"config": to_json_value(config), "config_sha256": canonical_checksum(config),
            "metrics": {split: _metrics([row for row in rows if row["split"] == split]) for split in ("dev", "test")},
            "pairs": rows}
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--threshold", type=float, default=.85, help="Use one declared threshold for both policies; do not tune against test")
    args = parser.parse_args()
    report = evaluate(args.dataset, threshold=args.threshold)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: value["metrics"] for name, value in report["policies"].items()}, ensure_ascii=False, indent=2))
    print(args.output)


if __name__ == "__main__":
    main()
