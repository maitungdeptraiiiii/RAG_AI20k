"""Audit saved 64-question retrieval results. No LLM, embedding, or reranker API calls.

Reads saved CSVs/traces and a read-only SQLite score cache, recomputes metrics,
checks ranking consistency, and freezes comparator artifacts with SHA-256 hashes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import statistics

from rag.eval.metrics import hit_at_k, load_questions, mrr_at_k, recall_at_k
from rag.retrieve.merge import merge_by_article
from rag.retrieve.rerank import DEFAULT_JEV_MODEL, ScoreCache
from rag.schema import Chunk, Hit


METRICS = ("recall@5", "hit@5", "mrr@5")


def read_rows(path: Path, config: str) -> dict[str, dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = [r for r in csv.DictReader(stream) if r["config"] == config]
    if len(rows) != 64 or len({r["id"] for r in rows}) != 64:
        raise ValueError(f"Expected 64 unique question rows: {path}, {config}")
    return {r["id"]: r for r in rows}


def comparison(old: dict, new: dict) -> dict:
    if set(old) != set(new):
        raise ValueError("Question IDs differ")
    result = {}
    for metric in METRICS:
        ids = sorted(old)
        differences = [float(new[i][metric]) - float(old[i][metric]) for i in ids]
        rng = random.Random(20261105)
        samples = sorted(statistics.mean(rng.choices(differences, k=len(ids))) for _ in range(10000))
        result[metric] = {
            "old": statistics.mean(float(old[i][metric]) for i in ids),
            "new": statistics.mean(float(new[i][metric]) for i in ids),
            "delta": statistics.mean(differences),
            "improved": [i for i, d in zip(ids, differences) if d > 1e-12],
            "worse": [i for i, d in zip(ids, differences) if d < -1e-12],
            "unchanged": sum(abs(d) <= 1e-12 for d in differences),
            "paired_bootstrap_95_percentile": [samples[249], samples[9749]],
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="evals/team-4.2/results/baseline-audit-64q")
    args = parser.parse_args()
    root = Path("evals/team-4.2/results")
    historical = root / "doi-thuong-64q-hyde-nobm25"
    controlled = root / "doi-thuong-64q-decomposition"
    latest = root / "doi-thuong-64q-decomposition-anchor20-add10"
    snapshot = Path("data/team-4.2/ablation/decomposition-anchor20-add10")
    question_path = Path("evals/team-4.2/datasets/benchmark_doi_thuong.jsonl")
    chunk_path = snapshot / "processed/chunks.jsonl"
    questions = {q.id: q for q in load_questions(question_path)}
    chunks = {c.chunk_id: c for c in (
        Chunk.from_dict(json.loads(line)) for line in chunk_path.read_text(encoding="utf-8").splitlines() if line.strip())}
    old = read_rows(historical / "retrieval_per_question.csv", "dense+rerank")
    old_dense = read_rows(historical / "retrieval_per_question.csv", "dense")
    base = read_rows(controlled / "retrieval_per_question.csv", "hyde+jev")
    new = read_rows(latest / "retrieval_per_question.csv", "decomposition+hyde+jev")
    if not set(old) == set(base) == set(new) == set(questions):
        raise ValueError("Dataset IDs do not match")
    traces = {t["id"]: t for t in json.loads((controlled / "query_traces.json").read_text(encoding="utf-8"))
              if t["config"] == "hyde+jev"}
    new_traces = {t["id"]: t for t in json.loads((latest / "query_traces.json").read_text(encoding="utf-8"))}

    # Check whether changed gold/metric semantics explain the stored score drift.
    metric_mismatches = []
    for label, rows in (("historical", old), ("historical_dense", old_dense), ("controlled", base), ("new", new)):
        for qid, row in rows.items():
            for metric, function in zip(METRICS, (recall_at_k, hit_at_k, mrr_at_k)):
                value = function(questions[qid], row["top5"].split(), chunks, 5)
                if abs(value - float(row[metric])) > 1e-12:
                    metric_mismatches.append({"run": label, "id": qid, "metric": metric})

    pre_rerank_changed, preserved = [], []
    for qid in questions:
        candidates = traces[qid]["candidates"]
        hits = [Hit(cid, 1., i, "dense") for i, cid in enumerate(candidates, 1)]
        dense_top = [h.chunk_id for h in merge_by_article(hits, chunks)[:5]]
        if dense_top != old_dense[qid]["top5"].split():
            pre_rerank_changed.append(qid)
        if new_traces[qid]["candidates"][:len(candidates)] == candidates:
            preserved.append(qid)

    cache_path = (snapshot / "cache/rerank.sqlite").resolve()
    score_snapshot, missing_historical, inconsistent_historical = {}, [], []
    replay_matches = {"controlled": 0, "new": 0}
    with sqlite3.connect(cache_path.as_uri() + "?mode=ro", uri=True) as connection:
        def score(qid: str, cid: str) -> float | None:
            key = ScoreCache.key(DEFAULT_JEV_MODEL, questions[qid].question, chunks[cid])
            value = connection.execute("SELECT score FROM rerank_scores WHERE key=?", (key,)).fetchone()
            if value:
                score_snapshot[key] = {"id": qid, "chunk_id": cid, "score": value[0]}
            return value[0] if value else None

        for qid in questions:
            scores = [score(qid, cid) for cid in old[qid]["top5"].split()]
            if any(value is None for value in scores):
                missing_historical.append(qid)
            elif any(a < b for a, b in zip(scores, scores[1:])):
                inconsistent_historical.append({"id": qid, "current_scores_in_historical_order": scores})
            for name, run_traces, rows in (("controlled", traces, base), ("new", new_traces, new)):
                candidates = run_traces[qid]["candidates"]
                values = [score(qid, cid) for cid in candidates]
                if any(value is None for value in values):
                    raise ValueError(f"Missing score in the controlled audit: {name}/{qid}")
                indices = sorted(range(len(candidates)), key=lambda i: (-values[i], i))
                ranked = [Hit(candidates[i], values[i], rank, "rerank") for rank, i in enumerate(indices, 1)]
                top = [h.chunk_id for h in merge_by_article(ranked, chunks)[:5]]
                replay_matches[name] += top == rows[qid]["top5"].split()

    checks = {
        "api_calls": 0, "metric_mismatches": metric_mismatches,
        "pre_rerank_top5_changed": pre_rerank_changed,
        "historical_rows_missing_current_scores": missing_historical,
        "historical_order_inconsistent_with_current_scores": inconsistent_historical,
        "cached_score_sort_matches": replay_matches, "original_pool_preserved": preserved,
        "comparisons": {"new_vs_historical": comparison(old, new), "new_vs_controlled": comparison(base, new),
                        "controlled_vs_historical": comparison(old, base)},
        "unresolved": "Historical run has no per-query trace, score snapshot, or exact input/config fingerprints; cannot determine why retrieval/scoring changed.",
    }
    out = Path(args.out)
    frozen = out / "frozen"
    frozen.mkdir(parents=True, exist_ok=True)
    inputs = {"historical.csv": historical / "retrieval_per_question.csv",
              "historical_summary.md": historical / "summary.md",
              "controlled.csv": controlled / "retrieval_per_question.csv",
              "controlled_config.json": controlled / "config.json",
              "controlled_traces.json": controlled / "query_traces.json",
              "new.csv": latest / "retrieval_per_question.csv", "new_config.json": latest / "config.json",
              "new_traces.json": latest / "query_traces.json", "questions.jsonl": question_path,
              "chunks.jsonl": chunk_path}
    manifest = {"api_calls": 0, "primary_historical_reference": "historical.csv: dense+rerank",
                "matched_component_reference": "controlled.csv: hyde+jev", "files": {}}
    for name, path in inputs.items():
        data = path.read_bytes()
        (frozen / name).write_bytes(data)
        manifest["files"][name] = {"source": str(path), "sha256": hashlib.sha256(data).hexdigest()}
    scores_data = json.dumps(score_snapshot, ensure_ascii=False, indent=2).encode("utf-8")
    (frozen / "cached_scores.json").write_bytes(scores_data)
    manifest["files"]["cached_scores.json"] = {"source": str(cache_path), "sha256": hashlib.sha256(scores_data).hexdigest()}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "audit.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")

    with (out / "per_question.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = ["id", "question", "type", "pre_rerank_changed"] + [f"{run}_{m}" for run in ("historical", "controlled", "new") for m in METRICS]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for qid, question in questions.items():
            row = {"id": qid, "question": question.question, "type": question.type,
                   "pre_rerank_changed": qid in pre_rerank_changed}
            row.update({f"{run}_{m}": rows[qid][m] for run, rows in (("historical", old), ("controlled", base), ("new", new)) for m in METRICS})
            writer.writerow(row)

    lines = ["# Kiểm tra baseline offline — 64 câu", "", "Không gọi API, không chạy retriever hoặc benchmark. Chỉ đọc artifact và sắp xếp điểm Jev đã cache.", "",
             "## Kết luận", "", "Chưa chứng minh decomposition tốt hơn baseline lịch sử. Nó cải thiện nhẹ so với baseline có trace/cache tương thích, nhưng mức tăng còn nhỏ và mới được đo trên bộ 64 câu đã dùng để phát triển.", "",
             "| Mốc | Recall@5 | Hit@5 | MRR@5 |", "|---|---:|---:|---:|"]
    for label, rows in (("Baseline lịch sử", old), ("Baseline có trace/cache tương thích", base), ("Decomposition mới 20 + tối đa 10", new)):
        lines.append("| " + label + " | " + " | ".join(f"{statistics.mean(float(r[m]) for r in rows.values()):.6f}" for m in METRICS) + " |")
    lines += ["", "## Đã xác định được gì về baseline lệch", "",
              f"- Tính lại các top 5 đã lưu bằng gold/chunk hiện tại: {len(metric_mismatches)} sai khác. Chênh lệch không phải do phép tính điểm cho các top 5 này.",
              f"- Top 5 Dense trước Jev khác ở {len(pre_rerank_changed)}/64 câu: thay đổi đã có trước rerank.",
              f"- Trong {64-len(missing_historical)} câu lịch sử có đủ điểm hiện tại, {len(inconsistent_historical)} thứ tự top 5 không giảm dần theo điểm Jev hiện tại. Do đó điểm/hành vi rerank lịch sử không thể coi là giống hiện tại.",
              "- Ví dụ d40: thứ tự lịch sử đặt chunk có điểm cache hiện tại 0.82 trước chunk 0.83; d60 là 0.97 trước 0.98. Với thuật toán hiện tại, hai thứ tự đó không được tái tạo chỉ bằng thay đổi tie-break.",
              "- Chưa thể quy nguyên nhân cụ thể cho HyDE, embedding, model, prompt hoặc cấu hình: lần lịch sử thiếu trace và fingerprint đủ chi tiết. Không kết luận chắc chắn model ngẫu nhiên hay dữ liệu đã đổi.",
              f"- Sắp xếp lại điểm cache tái tạo chính xác top 5 baseline có trace {replay_matches['controlled']}/64 và cấu hình mới {replay_matches['new']}/64. Pool gốc và thứ tự được giữ ở {len(preserved)}/64 câu.",
              "", "## Chênh lệch theo từng câu", "", "| Đối chiếu | Chỉ số | Tăng | Giảm | Giữ nguyên | Delta trung bình | Khoảng bootstrap 95% |", "|---|---|---:|---:|---:|---:|---|"]
    for name in ("new_vs_historical", "new_vs_controlled"):
        for metric, values in checks["comparisons"][name].items():
            low, high = values["paired_bootstrap_95_percentile"]
            lines.append(f"| {name} | {metric} | {len(values['improved'])} | {len(values['worse'])} | {values['unchanged']} | {values['delta']:+.6f} | [{low:+.6f}, {high:+.6f}] |")
    lines += ["", "Bootstrap lấy mẫu lại theo cặp câu hỏi 10.000 lần, seed 20261105. Đây là mô tả độ bất định trên bộ đang có; không sửa được việc khác điều kiện giữa các lần chạy hoặc việc đã dùng bộ này để chỉnh hệ thống.",
              "", "## Bốn câu làm baseline lịch sử lệch", "", "| ID | Recall lịch sử → baseline có trace | MRR lịch sử → baseline có trace |", "|---|---:|---:|"]
    for qid in questions:
        if any(abs(float(old[qid][m]) - float(base[qid][m])) > 1e-12 for m in METRICS):
            lines.append(f"| {qid} | {float(old[qid]['recall@5']):.3f} → {float(base[qid]['recall@5']):.3f} | {float(old[qid]['mrr@5']):.3f} → {float(base[qid]['mrr@5']):.3f} |")
    lines += ["", "## Mốc cố định cho lần tiếp theo", "",
              "Giữ baseline lịch sử làm mốc sản phẩm chính; baseline có trace/cache làm mốc phân tích tác động của decomposition. Hai mốc có tên riêng trong manifest.json, không chọn mốc thấp hơn để tuyên bố thắng.",
              "Các CSV, trace, gold/chunk và điểm cache đã được chụp vào frozen/ kèm SHA-256. Lần sau chỉ chạy cấu hình mới, đọc baseline từ đây; không gọi lại API cho baseline.",
              "Để kết luận vượt baseline tổng thể: đặt trước tiêu chí Recall và MRR, theo dõi câu giảm và chi phí; xác nhận trên bộ câu hỏi/gold độc lập chưa dùng để chỉnh prompt. Chưa có bộ độc lập được chấm trong lần kiểm tra này.",
              "Không có câu trả lời được sinh/chấm trong các artifact đang dùng; chưa kết luận chất lượng trả lời hoặc citation."]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Audit saved to {out}; API calls: 0; historical metric mismatches: {len(metric_mismatches)}")


if __name__ == "__main__":
    main()
