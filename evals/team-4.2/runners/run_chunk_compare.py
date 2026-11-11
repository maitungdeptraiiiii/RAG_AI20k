"""W02-04 — so sánh chunk cố định (fixed) và chunk theo cấu trúc (structural) trên 6 bộ luật gốc (chạy tại gốc repo).

    python evals/team-4.2/runners/run_chunk_compare.py
    python evals/team-4.2/runners/run_chunk_compare.py --configs bm25 dense hybrid hybrid+rerank

Mỗi chiến lược: DATA_DIR riêng (data/team-4.2/w02/chunk-<strategy>), CÙNG nguồn (data/team-4.2/raw/*.txt), CÙNG mọi
cấu hình khác lấy từ .env (embedding, HyDE, rerank, TOP_K, MAX_SYLLABLES). Chỉ khác CHUNK_STRATEGY.

Chấm "trúng Điều" theo vị trí văn bản (rag.eval.span_match) cho CẢ HAI chiến lược — chunk cố định không có `section`
nên cách chấm cũ theo `section` sẽ luôn trượt. Với structural, script kiểm tra cách chấm mới khớp cách chấm cũ.

Đầu ra (--out, mặc định evals/team-4.2/results/w02-chunk-compare/):
    summary.md, config.json, per_question.csv, examples.md
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

from rag.config import Settings
from rag.eval.metrics import recall_at_k
from rag.schema import Question
from rag.eval.runner import RETRIEVAL_CONFIGS
from rag.eval.span_match import ArticleIndex, gold_article
from rag.pipeline import RAGPipeline

RAW_DIR = Path("data/team-4.2/raw")
PREVIOUS_CONFIG = "evals/team-4.2/results/w02-chunk-compare/config.json"
K = 5


def _hits(retriever, question: str, config: str, k: int) -> list[str]:
    arms, rerank = RETRIEVAL_CONFIGS[config]
    return [h.chunk_id for h in retriever.retrieve(question, k, arms=arms, rerank=rerank).hits][:k]


def _score(q, top: list[str], chunks, indexes) -> tuple[float, float, float]:
    """(recall@k, hit@k, mrr@k) theo vị trí: gold i trúng nếu một chunk trong top chồng lên Điều gold."""
    found, first = set(), None
    for rank, cid in enumerate(top, 1):
        c = chunks.get(cid)
        if c is None:
            continue
        for gi, g in enumerate(q.gold):
            idx = indexes.get(g.source)
            if c.source == g.source and idx is not None and idx.covers(cid, gold_article(g.section)):
                found.add(gi)
                first = first or rank
    n = len(q.gold)
    return len(found) / n, 1.0 if found else 0.0, (1.0 / first) if first else 0.0


def run_strategy(base: Settings, strategy: str, questions, configs, out_rows, stats, examples_src):
    data_dir = Path(f"data/team-4.2/w02/chunk-{strategy}")
    settings = dataclasses.replace(base, data_dir=data_dir, chunk_strategy=strategy)
    pipeline = RAGPipeline.from_settings(settings)
    files = sorted(p for p in RAW_DIR.glob("*.txt"))
    t0 = time.time()
    reports = [pipeline.ingest(f, source=f.name) for f in files]
    ingest_s = time.time() - t0
    if all(r.skipped for r in reports):          # index đã dựng ở lần chạy trước: giữ thời gian ingest thật lần đó
        prev = Path(PREVIOUS_CONFIG)
        if prev.is_file():
            ingest_s = json.loads(prev.read_text(encoding="utf-8"))["strategies"].get(strategy, {}).get(
                "ingest_seconds", ingest_s)
    all_chunks = pipeline.store.all()
    chunks = {c.chunk_id: c for c in all_chunks}
    by_source = defaultdict(list)
    for c in all_chunks:
        by_source[c.source].append(c)
    indexes = {src: ArticleIndex((RAW_DIR / src).read_text(encoding="utf-8"), sorted(cs, key=lambda c: c.chunk_id))
               for src, cs in by_source.items() if (RAW_DIR / src).is_file()}
    located = sum(len(i.chunks) for i in indexes.values())
    sizes = [len(c.text.split()) for c in all_chunks]
    multi = [c for c in all_chunks
             if sum(indexes[c.source].covers(c.chunk_id, a) for a in indexes[c.source].articles) >= 2]
    stats[strategy] = {"data_dir": str(data_dir), "n_chunks": len(all_chunks), "located": located,
                       "avg_syllables": round(statistics.mean(sizes), 1), "median_syllables": statistics.median(sizes),
                       "chunks_spanning_2plus_articles": len(multi), "ingest_seconds": round(ingest_s, 1)}
    examples_src[strategy] = (multi, indexes, chunks)

    agree = total = 0
    for q in questions:
        if not q.in_scope:
            continue
        for config in configs:
            top = _hits(pipeline.retriever, q.question, config, K)
            r, h, m = _score(q, top, chunks, indexes)
            out_rows.append({"strategy": strategy, "config": config, "id": q.id, "type": q.type,
                             "split": getattr(q, "split", None) or "", "recall@5": r, "hit@5": h, "mrr@5": m,
                             "top": " | ".join(top)})
            if strategy == "structural":
                old = recall_at_k(q, top, chunks, K)
                total += 1
                agree += int(old is not None and abs(old - r) < 1e-9)
    if strategy == "structural":
        stats[strategy]["span_vs_section_agreement"] = f"{agree}/{total}"


def _table(rows, keys, title):
    groups = defaultdict(list)
    for r in rows:
        groups[tuple(r[k] for k in keys)].append(r)
    lines = [f"### {title}", "", "| " + " | ".join(keys) + " | n | R@5 | Hit@5 | MRR@5 |",
             "|" + "---|" * (len(keys) + 4)]
    for key in sorted(groups):
        g = groups[key]
        mean = lambda m: statistics.mean(x[m] for x in g)
        lines.append("| " + " | ".join(str(v) for v in key) + f" | {len(g)} | {mean('recall@5'):.3f} | "
                     f"{mean('hit@5'):.3f} | {mean('mrr@5'):.3f} |")
    return lines + [""]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--questions", default="evals/team-4.2/datasets/benchmark_doi_thuong_w02.jsonl")
    ap.add_argument("--configs", nargs="+", default=["bm25", "dense", "hybrid", "hybrid+rerank"],
                    choices=list(RETRIEVAL_CONFIGS))
    ap.add_argument("--strategies", nargs="+", default=["structural", "fixed"], choices=["structural", "fixed"])
    ap.add_argument("--out", default="evals/team-4.2/results/w02-chunk-compare")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    base = Settings.load()
    if any(RETRIEVAL_CONFIGS[c][1] for c in args.configs) and base.rerank_backend == "none":
        print("Cấu hình có rerank cần RERANK_BACKEND=jev trong .env", file=sys.stderr)
        return 2
    # chỉ câu trong phạm vi (câu out_of_scope không có gold; bản w02 còn kèm `reference` mà schema không nhận)
    questions = [Question.from_dict(d) for d in (json.loads(line) for line in
                 Path(args.questions).read_text(encoding="utf-8").splitlines() if line.strip())
                 if d.get("type") != "out_of_scope"]
    splits = {json.loads(line)["id"]: json.loads(line).get("split", "")
              for line in Path(args.questions).read_text(encoding="utf-8").splitlines() if line.strip()}
    rows, stats, examples_src = [], {}, {}
    for s in args.strategies:
        print(f"== {s}", flush=True)
        run_strategy(base, s, questions, args.configs, rows, stats, examples_src)
    for r in rows:
        r["split"] = splits.get(r["id"], "")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "per_question.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    config = {"questions": args.questions, "configs": args.configs, "k": K, "max_syllables": base.max_syllables,
              "fixed_overlap": base.chunk_overlap, "embed_model": base.embed_model, "advanced": base.advanced,
              "rerank_backend": base.rerank_backend, "rerank_n": base.rerank_n, "top_k": base.top_k,
              "matching": "span overlap with gold article (rag.eval.span_match)", "strategies": stats}
    (out / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    md = ["# W02-04 — Chunk cố định vs chunk theo cấu trúc", "",
          f"Bộ câu: `{args.questions}` ({sum(q.in_scope for q in questions)} câu trong phạm vi). "
          f"Cùng nguồn, cùng embedding `{base.embed_model}`, ADVANCED=`{base.advanced}`, rerank `{base.rerank_backend}`, "
          f"MAX_SYLLABLES={base.max_syllables}; fixed overlap={base.chunk_overlap}. Chấm theo vị trí văn bản.", "",
          "## Chỉ mục", "", "| strategy | chunks | âm tiết TB | trung vị | chunk vắt ≥2 Điều | ingest (s) | định vị được |",
          "|---|---|---|---|---|---|---|"]
    for s, st in stats.items():
        md.append(f"| {s} | {st['n_chunks']} | {st['avg_syllables']} | {st['median_syllables']} | "
                  f"{st['chunks_spanning_2plus_articles']} | {st['ingest_seconds']} | {st['located']} |")
    if "structural" in stats:
        md += ["", f"Kiểm tra cách chấm: với structural, chấm theo vị trí khớp chấm theo `section` ở "
                   f"{stats['structural']['span_vs_section_agreement']} lượt (câu × cấu hình)."]
    md += ["", "## Kết quả", ""]
    md += _table(rows, ["config", "strategy"], "Tất cả câu")
    md += _table([r for r in rows if r["split"] == "test"], ["config", "strategy"], "Tập test")
    md += _table(rows, ["config", "type", "strategy"], "Theo loại câu")
    (out / "summary.md").write_text("\n".join(md), encoding="utf-8")

    ex = ["# Ví dụ: chunk cố định cắt ngang Điều", ""]
    if "fixed" in examples_src:
        multi, indexes, _ = examples_src["fixed"]
        for c in multi[:3]:
            arts = [a for a in indexes[c.source].articles if indexes[c.source].covers(c.chunk_id, a)]
            ex += [f"## {c.source} — {c.chunk_id} — vắt qua Điều {', '.join(arts)}", "", "```", c.text[:900], "```", ""]
    (out / "examples.md").write_text("\n".join(ex), encoding="utf-8")
    print((out / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
