"""Run baseline RAG and/or the Think agent on the W04 benchmark, same questions, same index.

Run at repo root (PYTHONPATH=app/team-4.2/src):
    python evals/team-4.2/runners/run_agent_vs_baseline.py --system baseline --out evals/team-4.2/results/w04-agent-vs-baseline/RUN
    python evals/team-4.2/runners/run_agent_vs_baseline.py --system agent    --out evals/team-4.2/results/w04-agent-vs-baseline/RUN

Each system writes <out>/<system>.jsonl (one line per question, appended and
flushed, so a crashed run resumes with --resume). Only `question` reaches the
system; gold/key_points/reference never do. LLM usage is measured by wrapping the
OpenAI SDK call for this process (provider requests, prompt/completion tokens);
cache hits make no provider request. Embedding/rerank service calls are not
counted as LLM cost. Semantic correctness is scored later by
judge_agent_vs_baseline.py; this runner only records deterministic facts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import threading
import time
import traceback
from dataclasses import asdict
from pathlib import Path

from rag.config import Settings

_TLS = threading.local()


def usage_counters() -> dict:
    """Per-thread LLM usage counters (questions may run in parallel threads)."""
    if not hasattr(_TLS, "usage"):
        _TLS.usage = {"requests": 0, "input_tokens": 0, "output_tokens": 0}
    return _TLS.usage


def instrument_openai():
    from openai.resources.chat.completions import Completions

    original = Completions.create

    def create(self, *args, **kwargs):
        response = original(self, *args, **kwargs)
        usage = getattr(response, "usage", None)
        counters = usage_counters()
        counters["requests"] += 1
        counters["input_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
        counters["output_tokens"] += getattr(usage, "completion_tokens", 0) or 0
        return response

    Completions.create = create


_ARTICLE = re.compile(r"Điều\s+(\d+[a-zđ]?)\.")


def article_of(source: str, section: str | None) -> str | None:
    last = (section or "").rsplit(" > ", 1)[-1]
    match = _ARTICLE.match(last.strip())
    return f"{source}::Điều {match[1]}" if match else None


def gold_articles(row) -> set[str]:
    return {a for a in (article_of(g["source"], g["section"]) for g in row.get("gold", [])) if a}


def run_baseline(pipeline, row):
    trace = pipeline.ask_debug(row["question"])
    chunks = pipeline.retriever.chunks
    cited = []
    for c in trace.answer.citations:
        chunk = chunks.get(c.chunk_id)
        cited.append({"chunk_id": c.chunk_id, "source": c.source,
                      "section": chunk.section if chunk else None, "quote": c.quote[:300]})
    context = [{"source": b.chunk.source, "section": b.chunk.section} for b in trace.context.blocks]
    return {
        "answer": trace.answer.text, "refused": trace.answer.refused,
        "status": "refused" if trace.answer.refused else "answer",
        "stop_reason": None, "citations": cited, "context": context,
        "steps": {"retrievals": 1, "model_calls_logical": int(trace.llm_called)},
        "errors": dict(trace.retrieval.errors or {}),
    }


def run_agent(agent, row):
    trace = agent.ask_debug(row["question"])
    meta = trace.agent
    blocks = {b.chunk.chunk_id: b.chunk for b in trace.context.blocks}
    cited = []
    for c in trace.answer.citations:
        chunk = blocks.get(c.chunk_id) or agent.retriever.chunks.get(c.chunk_id)
        cited.append({"chunk_id": c.chunk_id, "source": c.source,
                      "section": chunk.section if chunk else None, "quote": c.quote[:300]})
    chunks = agent.retriever.chunks
    evidence = []
    for e in meta.get("evidence", []):
        first = chunks.get(e["chunk_ids"][0]) if e["chunk_ids"] else None
        evidence.append({
            "id": e["id"], "article": article_of(first.source, first.section) if first else None,
            "round": e["round"], "xref_depth": e["xref_depth"],
            "origins": sorted({o.get("type") for o in e["origins"]}),
        })
    budget = meta.get("budget", {})
    return {
        "answer": trace.answer.text, "refused": trace.answer.refused,
        "status": trace.status, "stop_reason": meta.get("stop_reason"), "citations": cited,
        "context": [{"source": b.chunk.source, "section": b.chunk.section} for b in trace.context.blocks],
        "steps": {k: budget.get(k) for k in ("rounds", "searches", "xref_targets", "model_calls")},
        "agent_tokens": {k: budget.get(k) for k in ("input_tokens", "output_tokens", "cache_hits", "provider_requests")},
        "evidence": evidence,
        "requirements": [r.get("question") for r in meta.get("requirements", [])],
        "unresolved_requirements": meta.get("unresolved_requirements", []),
        "verified": meta.get("verified"),
        "tool_calls": meta.get("tool_calls"),
        "errors": dict(trace.retrieval.errors or {}),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--system", choices=("baseline", "agent"), required=True)
    parser.add_argument("--dataset", type=Path, default=Path("evals/team-4.2/datasets/agent_vs_baseline_w04.jsonl"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--split", choices=("dev", "test", "all"), default="all")
    parser.add_argument("--ids", default="")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--shard", default="", help="k/n: run every n-th question starting at k (0-based); "
                        "writes <system>.shard<k>.jsonl, merge with --merge")
    parser.add_argument("--agent-impl", choices=("loop", "tools"), default="loop",
                        help="loop = fixed plan/assess/verify workflow; tools = model picks the next tool each step")
    parser.add_argument("--workers", type=int, default=1, help="parallel questions (threads, one shared index)")
    parser.add_argument("--merge", action="store_true", help="merge <system>.shard*.jsonl into <system>.jsonl and exit")
    args = parser.parse_args()
    if args.merge:
        parts = sorted(args.out.glob(f"{args.system}.shard*.jsonl"))
        seen, lines = set(), []
        for part in parts:
            for line in part.read_text(encoding="utf-8").splitlines():
                if line.strip() and json.loads(line)["id"] not in seen:
                    seen.add(json.loads(line)["id"])
                    lines.append(line)
        (args.out / f"{args.system}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"merged {len(lines)} rows from {len(parts)} shards")
        return 0

    raw = args.dataset.read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if args.split != "all":
        rows = [r for r in rows if r["split"] == args.split]
    if args.ids:
        wanted = [x.strip() for x in args.ids.split(",") if x.strip()]
        rows = [r for r in rows if r["id"] in wanted]
    suffix = ""
    if args.shard:
        k, n = (int(x) for x in args.shard.split("/"))
        rows = rows[k::n]
        suffix = f".shard{k}"
    args.out.mkdir(parents=True, exist_ok=True)
    out_file = args.out / f"{args.system}{suffix}.jsonl"
    done = set()
    if out_file.exists():
        if not args.resume:
            parser.error(f"{out_file} exists; pass --resume to continue it")
        done = {json.loads(l)["id"] for l in out_file.read_text(encoding="utf-8").splitlines() if l.strip()}

    instrument_openai()
    from rag.agent import AgentConfig, AgentPipeline
    from rag.pipeline import RAGPipeline

    settings = Settings.load()
    baseline = RAGPipeline.from_settings(settings)
    config = AgentConfig.from_settings(settings)
    if args.system == "agent" and args.agent_impl == "tools":
        from rag.agent.tool_agent import ToolAgentPipeline
        system = ToolAgentPipeline(baseline, config)
    else:
        system = AgentPipeline(baseline, config) if args.system == "agent" else baseline
    manifest = {
        "system": args.system, "dataset": str(args.dataset),
        "dataset_sha256": hashlib.sha256(raw).hexdigest(), "split": args.split, "n": len(rows),
        "llm_model": settings.llm_model, "embed_model": settings.embed_model,
        "advanced": settings.advanced, "rerank_backend": settings.rerank_backend, "top_k": settings.top_k,
        "agent_config": asdict(config) if args.system == "agent" else None,
        "agent_impl": args.agent_impl if args.system == "agent" else None,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "workers": args.workers,
    }
    (args.out / f"config.{args.system}{suffix}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    write_lock = threading.Lock()

    def one(row, handle):
        counters = usage_counters()
        before = dict(counters)
        started = time.perf_counter()
        try:
            result = run_agent(system, row) if args.system == "agent" else run_baseline(system, row)
            crash = None
        except Exception as exc:  # recorded as a failed task, never silently dropped
            result = {"answer": "", "refused": False, "status": "crash", "citations": [], "context": []}
            crash = f"{type(exc).__name__}: {exc}"[:500]
            traceback.print_exc()
        elapsed = time.perf_counter() - started
        gold = gold_articles(row)
        cited = {a for a in (article_of(c["source"], c["section"]) for c in result["citations"]) if a}
        context = {a for a in (article_of(c["source"], c["section"]) for c in result["context"]) if a}
        record = {
            "id": row["id"], "system": args.system, "category": row["category"], "split": row["split"],
            **result, "crash": crash,
            "latency_s": round(elapsed, 2), "workers": args.workers,
            "llm_requests": counters["requests"] - before["requests"],
            "input_tokens": counters["input_tokens"] - before["input_tokens"],
            "output_tokens": counters["output_tokens"] - before["output_tokens"],
            "gold_articles": sorted(gold), "cited_articles": sorted(cited),
            "gold_cited_recall": len(gold & cited) / len(gold) if gold else None,
            "gold_context_recall": len(gold & context) / len(gold) if gold else None,
            "cited_precision": len(gold & cited) / len(cited) if gold and cited else None,
        }
        with write_lock:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
        print(f"{row['id']} {args.system} status={record['status']} gold_cited={record['gold_cited_recall']} "
              f"lat={record['latency_s']}s req={record['llm_requests']}", flush=True)

    todo = [row for row in rows if row["id"] not in done]
    with out_file.open("a", encoding="utf-8") as handle:
        if args.workers <= 1:
            for row in todo:
                one(row, handle)
        else:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                for future in [pool.submit(one, row, handle) for row in todo]:
                    future.result()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
