"""End-to-end agent evaluation, with references kept outside model inputs.

Run at repository root with PYTHONPATH=app/team-4.2/src. Defaults to three
questions; --out must be new to preserve previous results. Semantic/legal answer
quality requires human review: this runner does not manufacture an accuracy score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from rag.agent import AgentConfig, AgentPipeline
from rag.config import Settings
from rag.pipeline import RAGPipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("evals/team-4.2/datasets/benchmark_multihop_hard25.jsonl"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    raw = args.dataset.read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()][:args.limit]
    if not rows or any(not isinstance(row.get("question"), str) for row in rows):
        parser.error("Dataset needs nonempty rows with question strings")
    args.out.mkdir(parents=True, exist_ok=False)
    settings = Settings.load()
    config = AgentConfig.from_settings(settings)
    baseline = RAGPipeline.from_settings(settings)
    agent = AgentPipeline(baseline, config)
    manifest = {
        "dataset_sha256": hashlib.sha256(raw).hexdigest(), "n": len(rows),
        "agent": asdict(config), "model": settings.llm_model, "embed_model": settings.embed_model,
        "rerank_backend": settings.rerank_backend, "semantic_quality": "human_review_required",
    }
    (args.out / "config.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    outcomes = []
    with (args.out / "responses.jsonl").open("x", encoding="utf-8") as output:
        for row in rows:
            # Deliberately pass only question, never gold/reference/reasoning_steps.
            trace = agent.ask_debug(row["question"])
            response = trace.to_response(row["question"])
            expected = {(g["source"], g["section"]) for g in row.get("gold", [])}
            retrieved = {(baseline.retriever.chunks[cid].source, baseline.retriever.chunks[cid].section)
                         for evidence in trace.agent["evidence"] for cid in evidence["chunk_ids"]}
            supplied = {(block.chunk.source, block.chunk.section) for block in trace.context.blocks}
            metric = {
                "id": row["id"], "status": trace.status, "stop_reason": trace.agent["stop_reason"],
                "candidate_recall": len(expected & retrieved) / len(expected) if expected else None,
                "all_gold_candidate": expected <= retrieved if expected else None,
                "all_gold_final_context": expected <= supplied if expected else None,
                "rounds": trace.agent["budget"]["rounds"],
                "model_calls": trace.agent["budget"]["model_calls"],
                "elapsed_s": trace.agent["budget"]["elapsed_s"],
            }
            outcomes.append(metric)
            output.write(json.dumps({"id": row["id"], "metrics": metric, "response": response}, ensure_ascii=False) + "\n")
            output.flush()
            print(json.dumps(metric, ensure_ascii=False), flush=True)
    summary = {"n": len(outcomes), "outcomes": outcomes,
               "semantic_quality": "human_review_required; agent verification is not ground truth"}
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
