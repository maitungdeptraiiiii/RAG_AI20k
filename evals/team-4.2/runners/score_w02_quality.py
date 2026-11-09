"""Tính TP/FN/FP của detector tuần 2 từ labels đóng băng và findings đã xuất — W02-03.

Input findings JSONL (từ ``run_w02_detectors.py`` hoặc adapter khác), mỗi dòng có:
``{"fixture_id": "w02-20", "issue_codes": ["numeric.sum_mismatch"]}``.
Labels không được import vào detector; runner này chỉ chấm offline sau khi detector đã chạy.

Khớp nhãn <-> phát hiện: cùng ``fixture_id`` + cùng mã issue. Báo:
- theo từng mã issue (TP/FN/FP, precision, recall),
- riêng ``dev`` và ``test`` (số chính dùng ``test``),
- "trong phạm vi" = các mã có detector đã nối vào pipeline; ngoài phạm vi = chưa có detector (FN).

    python evals/team-4.2/runners/score_w02_quality.py \\
        --observed evals/team-4.2/results/w02-quality/findings.jsonl \\
        --out-dir evals/team-4.2/results/w02-quality
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LABELS = ROOT / "data/team-4.2/fixtures/labels.jsonl"
# Mã có detector trong RAGPipeline.ingest. Các mã khác (dedup.near, version.*, flow.*) thuộc Nhóm 1.
IN_SCOPE_PREFIXES = ("pii.", "numeric.", "table.", "date.", "ocr.")


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


def _ratio(a: int, b: int) -> float | None:
    return a / b if b else None


def report(expected: set[tuple[str, str]], observed: set[tuple[str, str]]) -> dict:
    tp, fn, fp = expected & observed, expected - observed, observed - expected
    return {
        "expected_count": len(expected),
        "observed_count": len(observed),
        "tp": len(tp), "fn": len(fn), "fp": len(fp),
        "precision": _ratio(len(tp), len(tp) + len(fp)),
        "recall": _ratio(len(tp), len(tp) + len(fn)),
        "true_positive": [{"fixture_id": f, "issue_code": c} for f, c in sorted(tp)],
        "false_negative": [{"fixture_id": f, "issue_code": c} for f, c in sorted(fn)],
        "false_positive": [{"fixture_id": f, "issue_code": c} for f, c in sorted(fp)],
    }


def by_code(expected: set[tuple[str, str]], observed: set[tuple[str, str]]) -> dict[str, dict]:
    codes = sorted({c for _, c in expected | observed})
    out: dict[str, dict] = {}
    for code in codes:
        e = {p for p in expected if p[1] == code}
        o = {p for p in observed if p[1] == code}
        r = report(e, o)
        out[code] = {k: r[k] for k in ("tp", "fn", "fp", "precision", "recall")}
        out[code]["in_scope"] = code.startswith(IN_SCOPE_PREFIXES)
    return out


def scored(labels: list[dict], findings: list[dict]) -> dict:
    split_of = {label["fixture_id"]: label.get("split", "unsplit") for label in labels}
    expected, observed = expected_pairs(labels), observed_pairs(findings)
    unknown = sorted({f for f, _ in observed} - set(split_of))
    if unknown:
        raise ValueError(f"Findings có fixture_id không có trong labels: {unknown}")
    result: dict = {"all": report(expected, observed), "by_code": by_code(expected, observed), "splits": {}}
    in_scope = lambda pairs: {p for p in pairs if p[1].startswith(IN_SCOPE_PREFIXES)}  # noqa: E731
    result["in_scope"] = report(in_scope(expected), in_scope(observed))
    for split in sorted(set(split_of.values())):
        keep = lambda pairs: {p for p in pairs if split_of[p[0]] == split}  # noqa: E731
        result["splits"][split] = {
            "all": report(keep(expected), keep(observed)),
            "in_scope": report(in_scope(keep(expected)), in_scope(keep(observed))),
            "by_code": by_code(keep(expected), keep(observed)),
        }
    return result


def _fmt(x: float | None) -> str:
    return "—" if x is None else f"{x:.2f}"


def _commit() -> str:
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "app/team-4.2/src", "data/team-4.2/fixtures"],
                               cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        return f"{head}-dirty" if dirty else head
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def summary_markdown(result: dict, labels: list[dict], findings: list[dict], config: dict) -> str:
    split_of = {label["fixture_id"]: label.get("split") for label in labels}
    findings_by_id = {f["fixture_id"]: f for f in findings}
    lines = [
        "# W02-03 — Data quality: phát hiện / bỏ sót / báo nhầm",
        "",
        f"Commit `{config['commit']}` · labels `{config['labels']}` · findings `{config['observed']}`.",
        "Khớp = cùng `fixture_id` + cùng mã issue. **Số chính dùng split `test`.**",
        "",
        "## Tổng hợp",
        "",
        "| Phạm vi | Split | TP | FN | FP | Precision | Recall |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for split in ("test", "dev"):
        for scope in ("in_scope", "all"):
            r = result["splits"].get(split, {}).get(scope)
            if r:
                name = "Detector trong pipeline (pii/numeric/table/ocr)" if scope == "in_scope" else "Toàn bộ mã trong labels"
                lines.append(f"| {name} | {split} | {r['tp']} | {r['fn']} | {r['fp']} | "
                             f"{_fmt(r['precision'])} | {_fmt(r['recall'])} |")
    lines += ["", "## Theo mã issue (dev + test)", "",
              "| Mã | Có detector | TP | FN | FP | Precision | Recall |", "|---|---|---:|---:|---:|---:|---:|"]
    for code, r in result["by_code"].items():
        lines.append(f"| `{code}` | {'có' if r['in_scope'] else 'chưa (Nhóm 1)'} | {r['tp']} | {r['fn']} | "
                     f"{r['fp']} | {_fmt(r['precision'])} | {_fmt(r['recall'])} |")
    lines += ["", "## Từng bỏ sót / báo nhầm", "", "| Loại | Fixture | Split | Mã | Lý do |", "|---|---|---|---|---|"]
    for kind, key in (("FN", "false_negative"), ("FP", "false_positive")):
        for item in result["all"][key]:
            fid, code = item["fixture_id"], item["issue_code"]
            f = findings_by_id.get(fid, {})
            if f.get("ingest_status") == "failed":
                reason = f"Pipeline chưa đọc được nguồn ({f.get('error')}): cần OCR"
            elif not code.startswith(IN_SCOPE_PREFIXES):
                reason = "Chưa có detector cho mã này trong pipeline"
            else:
                reason = "Detector có nhưng không bắt được — xem per_item.csv"
            if kind == "FP":
                reason = "Detector báo nhưng labels không có — xem issues trong findings.jsonl"
            lines.append(f"| {kind} | `{fid}` | {split_of.get(fid)} | `{code}` | {reason} |")
    lines += ["", "Nhất quán số học (tổng khớp) không chứng minh nguồn đúng; conflict chỉ là tín hiệu review.", ""]
    return "\n".join(lines)


def write_per_item(path: Path, labels: list[dict], findings: list[dict]) -> None:
    obs = {f["fixture_id"]: f for f in findings}
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["fixture_id", "split", "expected_codes", "observed_codes", "tp", "fn", "fp",
                         "expected_status", "observed_status"])
        for label in labels:
            fid = label["fixture_id"]
            exp = set(label.get("expected", {}).get("issue_codes", []))
            got = set(obs.get(fid, {}).get("issue_codes", []))
            writer.writerow([fid, label.get("split"), ";".join(sorted(exp)), ";".join(sorted(got)),
                             len(exp & got), len(exp - got), len(got - exp),
                             label.get("expected", {}).get("ingest_status"), obs.get(fid, {}).get("ingest_status")])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--observed", type=Path, required=True, help="findings JSONL từ pipeline/eval adapter")
    parser.add_argument("--labels", type=Path, default=LABELS)
    parser.add_argument("--out", type=Path, help="(cũ) chỉ ghi result.json tại đường dẫn này")
    parser.add_argument("--out-dir", type=Path, help="ghi result.json, summary.md, per_item.csv, config.json")
    args = parser.parse_args()
    if not args.out and not args.out_dir:
        parser.error("cần --out hoặc --out-dir")
    labels, findings = load_jsonl(args.labels), load_jsonl(args.observed)
    result = scored(labels, findings)
    rel = lambda p: p.resolve().relative_to(ROOT).as_posix() if p.resolve().is_relative_to(ROOT) else str(p)  # noqa: E731
    config = {"commit": _commit(), "labels": rel(args.labels), "observed": rel(args.observed),
              "match_rule": "fixture_id + issue_code", "in_scope_prefixes": list(IN_SCOPE_PREFIXES),
              "numeric_config": "csv-machine (decimal '.', no grouping)", "header_rows_override": {"w02-19": 2}}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result["all"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                                  encoding="utf-8")
        (args.out_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n",
                                                  encoding="utf-8")
        (args.out_dir / "summary.md").write_text(summary_markdown(result, labels, findings, config), encoding="utf-8")
        write_per_item(args.out_dir / "per_item.csv", labels, findings)
    test = result["splits"].get("test", {}).get("in_scope", result["in_scope"])
    print(f"[test, detector trong pipeline] TP={test['tp']} FN={test['fn']} FP={test['fp']}; "
          f"[toàn bộ] TP={result['all']['tp']} FN={result['all']['fn']} FP={result['all']['fp']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
