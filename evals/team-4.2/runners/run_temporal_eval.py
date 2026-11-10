"""Đánh giá hỏi đáp theo mốc thời gian trên kho luật có phiên bản (phần 2).

Với mỗi câu trong dataset: dựng mốc bằng quy tắc (``build_timeline`` không LLM), rồi với từng mốc tìm top-k trong
``VersionedIndex`` (lọc theo hiệu lực trước khi xếp hạng). Đo:

- độ đúng mốc: tập (role, start, end) dựng được == ``expected_anchors``;
- độ đúng phiên bản: với mỗi vai trò trong ``expected_documents``, mọi văn bản kỳ vọng có trong top-k của mốc vai trò
  đó, và không văn bản nào trong ``forbidden_documents`` xuất hiện.

``--llm`` chạy thêm ``TemporalQA`` thật (LLM theo cấu hình .env + kho cũ) và đếm số câu trả lời ``firm`` nhưng dựa trên
căn cứ chưa xác minh (phải bằng 0), ghi câu trả lời ra ``--answers``.

Chạy tại gốc repo:

    python evals/team-4.2/runners/run_temporal_eval.py --fixture                 # kho mẫu bất động sản, không mạng
    python evals/team-4.2/runners/run_temporal_eval.py --legal-dir <DATA_DIR>/legal --llm \\
        --out evals/team-4.2/results/w02-temporal-qa/report.json \\
        --answers evals/team-4.2/results/w02-temporal-qa/answers.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "app" / "team-4.2"
for p in (APP / "src", APP):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from rag.temporal.timeline import build_timeline  # noqa: E402

DEFAULT_DATASET = ROOT / "evals" / "team-4.2" / "datasets" / "temporal_qa_realestate.jsonl"


def load_dataset(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def version_check(expected: dict[str, list[str]], forbidden: dict[str, list[str]],
                  found: dict[str, set[str]]) -> bool:
    for role, keys in expected.items():
        if role not in found or not set(keys) <= found[role]:
            return False
    return all(not (set(keys) & found.get(role, set())) for role, keys in forbidden.items())


def evaluate(rows: list[dict], index, *, k: int = 10) -> dict:
    out = []
    for row in rows:
        asked_at = datetime.fromisoformat(row["asked_at"])
        as_of = date.fromisoformat(row["as_of"]) if row.get("as_of") else None
        tl = build_timeline(row["question"], asked_at=asked_at, calendar_date=as_of, llm=None)
        got = sorted((a.role, _iso(a.start), _iso(a.end)) for a in tl.anchors)
        want = sorted((a["role"], a["start"], a["end"]) for a in row["expected_anchors"])
        found: dict[str, set[str]] = {}
        for a in tl.anchors:
            if a.start is None:
                continue
            hits = index.search(row["question"], a.start, a.end or a.start, k)
            found.setdefault(a.role, set()).update(c.document_key for c, _ in hits)
        ok_v = version_check(row["expected_documents"], row["forbidden_documents"], found)
        out.append({"id": row["id"], "anchor_ok": got == want, "version_ok": ok_v,
                    "anchors": [list(x) for x in got], "expected_anchors": [list(x) for x in want],
                    "found": {r: sorted(v) for r, v in found.items()}, "warnings": list(tl.warnings)})
    n = len(out) or 1
    return {"n": len(out), "k": k,
            "anchor_accuracy": sum(r["anchor_ok"] for r in out) / n,
            "version_accuracy": sum(r["version_ok"] for r in out) / n,
            "rows": out}


def run_llm(rows: list[dict], legal_dir: Path, answers_path: Path | None) -> dict:
    """TemporalQA thật: LLM + kho cũ. Đếm `firm` trên căn cứ chưa xác minh (enforce phải chặn)."""
    from rag.config import Settings
    from rag.legal.service import LegalService
    from rag.legal.store import LegalStore
    from rag.pipeline import RAGPipeline
    from rag.temporal.index import VersionedIndex
    from rag.temporal.qa import TemporalQA
    from rag.temporal.status import load_legacy_map

    settings = Settings.load()
    pipeline = RAGPipeline.from_settings(settings)
    service = LegalService(LegalStore(legal_dir / "catalog.sqlite"))
    index = VersionedIndex(service.store)
    index.build()

    def legacy_search(query: str, k: int):
        result = pipeline.retriever.retrieve(query, k)
        chunks = pipeline.retriever.chunks
        return [chunks[h.chunk_id] for h in result.hits[:k] if h.chunk_id in chunks]

    legacy_map = load_legacy_map(ROOT / "data" / "team-4.2" / "legal" / "legacy_map.yaml")
    stats = {"n": 0, "firm": 0, "qualified": 0, "cannot_conclude": 0, "firm_on_unverified": 0, "errors": 0}
    answers = []
    for row in rows:
        asked_at = datetime.fromisoformat(row["asked_at"])
        qa = TemporalQA(service, index, pipeline.llm, legacy_search=legacy_search, legacy_map=legacy_map,
                        now=lambda asked_at=asked_at: asked_at)
        as_of = date.fromisoformat(row["as_of"]) if row.get("as_of") else None
        stats["n"] += 1
        try:
            r = qa.ask(row["question"], calendar_date=as_of)
        except Exception as exc:  # noqa: BLE001 — ghi lỗi, không dừng cả lượt chạy
            stats["errors"] += 1
            answers.append({"id": row["id"], "error": repr(exc)})
            continue
        cert = r.answer.certainty
        stats[cert] = stats.get(cert, 0) + 1
        if cert == "firm" and any(i.document_status != "verified" for i in r.items):
            stats["firm_on_unverified"] += 1
        answers.append({"id": row["id"], "question": row["question"], "certainty": cert,
                        "downgrade_reasons": r.answer.downgrade_reasons, "answer": r.answer.answer_markdown,
                        "sources": [{"n": i.n, "store": i.store, "document": i.document_key or i.title,
                                     "article": i.article_id or i.section, "status": i.document_status,
                                     "valid_from": _iso(i.valid_from), "valid_to": _iso(i.valid_to)} for i in r.items],
                        "transition_rules": [t.rule_id for t in r.rules]})
    if answers_path:
        answers_path.parent.mkdir(parents=True, exist_ok=True)
        answers_path.write_text("\n".join(json.dumps(a, ensure_ascii=False) for a in answers) + "\n", encoding="utf-8")
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--fixture", action="store_true", help="dựng kho mẫu bất động sản trong thư mục tạm")
    src.add_argument("--legal-dir", type=Path, help="thư mục chứa catalog.sqlite (DATA_DIR/legal)")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--llm", action="store_true", help="chạy TemporalQA thật (cần --legal-dir)")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--answers", type=Path)
    args = ap.parse_args(argv)

    from rag.temporal.index import VersionedIndex

    rows = load_dataset(args.dataset)
    if args.fixture:
        from tests.test_temporal_index import realestate_service
        service = realestate_service(Path(tempfile.mkdtemp(prefix="temporal-eval-")))
        store = service.store
    else:
        from rag.legal.store import LegalStore
        store = LegalStore(args.legal_dir / "catalog.sqlite")
    index = VersionedIndex(store)
    index.build()
    report = evaluate(rows, index, k=args.k)
    if args.llm:
        if not args.legal_dir:
            ap.error("--llm cần --legal-dir")
        report["llm"] = run_llm(rows, args.legal_dir, args.answers)
    for r in report["rows"]:
        if not (r["anchor_ok"] and r["version_ok"]):
            print(f"  FAIL {r['id']}: anchor_ok={r['anchor_ok']} version_ok={r['version_ok']} "
                  f"anchors={r['anchors']} found={r['found']}")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
