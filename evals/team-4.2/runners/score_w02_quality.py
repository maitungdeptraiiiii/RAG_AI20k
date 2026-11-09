"""Tính TP/FN/FP của detector tuần 2 từ labels đóng băng và findings đã xuất.

Input findings JSONL là adapter mỏng từ pipeline, mỗi dòng có:
``{"fixture_id": "w02-20", "issue_codes": ["numeric.sum_mismatch"]}``.
Labels không được import vào detector; runner này chỉ được dùng sau khi detector
đã chạy để đánh giá offline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LABELS = ROOT / "data/team-4.2/fixtures/labels.jsonl"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def expected_pairs(labels: list[dict]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for label in labels:
        for code in label.get("expected", {}).get("issue_codes", []):
            pairs.add((label["fixture_id"], code))
    return pairs


def observed_pairs(findings: list[dict]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for finding in findings:
        fixture_id = finding.get("fixture_id")
        if not fixture_id:
            raise ValueError("Mỗi finding phải có fixture_id do eval adapter cung cấp")
        codes = finding.get("issue_codes")
        if codes is None and finding.get("code"):
            codes = [finding["code"]]
        if not isinstance(codes, list) or not all(isinstance(code, str) for code in codes):
            raise ValueError(f"{fixture_id}: issue_codes phải là list[str]")
        pairs.update((fixture_id, code) for code in codes)
    return pairs


def report(expected: set[tuple[str, str]], observed: set[tuple[str, str]]) -> dict:
    tp, fn, fp = expected & observed, expected - observed, observed - expected
    precision = len(tp) / (len(tp) + len(fp)) if tp or fp else None
    recall = len(tp) / (len(tp) + len(fn)) if tp or fn else None
    return {
        "expected_count": len(expected),
        "observed_count": len(observed),
        "tp": len(tp), "fn": len(fn), "fp": len(fp),
        "precision": precision, "recall": recall,
        "true_positive": [{"fixture_id": fixture_id, "issue_code": code} for fixture_id, code in sorted(tp)],
        "false_negative": [{"fixture_id": fixture_id, "issue_code": code} for fixture_id, code in sorted(fn)],
        "false_positive": [{"fixture_id": fixture_id, "issue_code": code} for fixture_id, code in sorted(fp)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observed", type=Path, required=True, help="findings JSONL từ pipeline/eval adapter")
    parser.add_argument("--labels", type=Path, default=LABELS)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = report(expected_pairs(load_jsonl(args.labels)), observed_pairs(load_jsonl(args.observed)))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"TP={result['tp']} FN={result['fn']} FP={result['fp']}; wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
