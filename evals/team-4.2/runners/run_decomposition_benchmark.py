"""Benchmark only the new decomposition configuration on the main 64-question dataset.

Run from the repository root. Uses the configured existing index; Dense only, HyDE required.
Writes a checkpoint CSV and query traces after every question; never changes .env or the index.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import time

from rag.advanced.decomposition import DECOMPOSITION_SYSTEM
from rag.config import Settings
from rag.eval.metrics import load_questions, recall_at_k, hit_at_k, mrr_at_k, unmatched_gold
from rag.eval.runner import summary_markdown, write_csv
from rag.pipeline import RAGPipeline


def load_saved_baseline(path: str | None, config: str, questions: list) -> list[dict]:
    """Read a saved comparator without retrieving, reranking, or calling any API."""
    if path is None:
        return []
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = [r for r in csv.DictReader(stream) if r.get("config") == config]
    expected = {q.id: q for q in questions}
    if len(rows) != len(expected) or {r["id"] for r in rows} != set(expected):
        raise ValueError("Saved baseline must contain exactly one row per benchmark question")
    for row in rows:
        if row.get("type") != expected[row["id"]].type:
            raise ValueError(f"Saved baseline question type differs: {row['id']}")
        for metric in ("recall@5", "hit@5", "mrr@5", "recall@20"):
            value = float(row[metric])
            if not 0 <= value <= 1:
                raise ValueError(f"Invalid saved metric: {metric}")
            row[metric] = value
        row["config"] = f"saved:{config}"
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--questions", default="evals/team-4.2/datasets/benchmark_doi_thuong.jsonl")
    ap.add_argument("--out", default=None)
    ap.add_argument("--baseline-csv", help="optional saved baseline CSV; never runs baseline")
    ap.add_argument("--baseline-config", default="hyde+jev", help="config name in the saved CSV")
    args = ap.parse_args()
    settings = replace(Settings.load(), decomp_enabled=True)
    if "hyde" not in settings.advanced_methods or settings.rerank_backend != "jev":
        raise ValueError("This comparison requires ADVANCED=hyde (optionally contextual_header) and Jev")
    questions = load_questions(args.questions)
    if len(questions) != 64:
        raise ValueError(f"Expected the main 64-question benchmark; got {len(questions)}")
    baseline_rows = load_saved_baseline(args.baseline_csv, args.baseline_config, questions)
    # Use a fresh directory so a new run cannot overwrite the previous experiment.
    out = Path(args.out or f"evals/team-4.2/results/doi-thuong-64q-decomposition-{time.strftime('%Y%m%d-%H%M%S')}")
    if any((out / name).exists() for name in ("config.json", "retrieval_per_question.csv", "query_traces.json")):
        raise ValueError("Output already contains a benchmark; choose a new --out directory")
    p = RAGPipeline.from_settings(settings)
    p.retriever.arms["dense"].fallback = False  # HyDE errors must not masquerade as this configuration.
    if unmatched_gold(questions, p.store.all()):
        raise ValueError("Some gold references do not match the current index")
    decomposer = p.retriever.decomposer
    out.mkdir(parents=True, exist_ok=True)
    metadata = {"questions_sha256": hashlib.sha256(Path(args.questions).read_bytes()).hexdigest(),
                "prompt_sha256": hashlib.sha256(DECOMPOSITION_SYSTEM.encode()).hexdigest(),
                "index_signature": json.loads(settings.index_config_path.read_text(encoding="utf-8")),
                "data_dir": str(settings.data_dir), "advanced": settings.advanced,
                "index_snapshot": (json.loads((settings.data_dir / "snapshot_manifest.json").read_text(encoding="utf-8"))
                                   if (settings.data_dir / "snapshot_manifest.json").exists() else None),
                "llm": settings.llm_model, "rerank": settings.rerank_backend,
                "arm_k": settings.arm_k, "rerank_n": settings.rerank_n,
                "article_pool_factor": settings.article_pool_factor, "merge_articles": settings.merge_articles,
                "top_k": settings.top_k, "rrf_k": settings.rrf_k,
                "baseline_execution": False, "saved_baseline_csv": args.baseline_csv,
                "pool_strategy": "preserve_original_then_add_novel_articles",
                "saved_baseline_config": args.baseline_config if args.baseline_csv else None,
                "decomposition": {"max_subqueries": decomposer.max_subqueries,
                                  "include_original": decomposer.include_original,
                                  "per_query_k": decomposer.per_query_k, "pool_size": decomposer.pool_size,
                                  "max_new_articles": decomposer.max_new_articles},
                "note": "Retrieval benchmark only; elapsed times include cache effects. No answer generation."}
    (out / "config.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    rows, traces = [], []
    for index, question in enumerate(questions, 1):
        name = "decomposition+hyde+jev"
        start = time.perf_counter()
        res = p.retriever.retrieve(question.question, settings.top_k, mode="dense")
        elapsed = time.perf_counter() - start
        # Do not silently publish a fallback ranking as a Jev benchmark.
        if not res.reranked or res.errors:
            raise RuntimeError(f"Jev failed for {question.id}; benchmark stopped, checkpoints preserved")
        # Match the existing main benchmark's representative-chunk metric exactly.
        chunks = p.retriever.chunks
        top = [h.chunk_id for h in res.hits]
        pool = [h.chunk_id for h in res.ranked]
        rows.append({"id": question.id, "type": question.type, "author": question.author,
                     "config": name, "recall@5": recall_at_k(question, top, chunks, 5),
                     "hit@5": hit_at_k(question, top, chunks, 5),
                     "mrr@5": mrr_at_k(question, top, chunks, 5),
                     "recall@20": recall_at_k(question, pool, chunks, 20),
                     "candidate_recall": recall_at_k(question, pool, chunks, len(pool) or 1),
                     "reranked": res.reranked, "elapsed_s": round(elapsed, 3),
                     "query_count": len(res.queries) or 1, "candidate_chunks": len(res.candidates),
                     "top5": " ".join(top), "errors": json.dumps(res.errors, ensure_ascii=False)})
        traces.append({"id": question.id, "config": name, "question": question.question,
                       "queries": res.queries or [question.question], "errors": res.errors,
                       "candidates": [h.chunk_id for h in res.candidates], "top5": top})
        write_csv(rows, out / "retrieval_per_question.csv")
        (out / "query_traces.json").write_text(json.dumps(traces, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{index}/64] {question.id}: decomp={rows[-1]['recall@5']:.3f}, "
              f"queries={rows[-1]['query_count']}", flush=True)
    header = ("# Query decomposition — benchmark chính 64 câu\n\n"
              "Chỉ chạy cấu hình mới; không chạy lại baseline, không dùng BM25.\n"
              "Metric giữ nguyên cách chấm chunk đại diện của benchmark chính; thời gian có ảnh hưởng cache.\n"
              "Đây là đánh giá retrieval, chưa đánh giá chất lượng câu trả lời cuối.\n\n")
    summary = header + summary_markdown(rows)
    if baseline_rows:
        summary += ("\n## Đối chiếu baseline đã lưu (không gọi API)\n\n"
                    "Đây là kết quả từ lần chạy khác. Cần đối chiếu dữ liệu, index và cấu hình "
                    "trước khi diễn giải chênh lệch.\n\n" + summary_markdown(baseline_rows + rows))
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary, flush=True)


if __name__ == "__main__":
    main()
