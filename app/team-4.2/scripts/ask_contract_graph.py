"""Hỏi một câu về hợp đồng; agent trả lời bằng cách đi trên đồ thị hợp đồng (spec 2026-11-16-contract-graph-agent).

Chạy từ app/team-4.2:  uv run python scripts/ask_contract_graph.py <file hợp đồng> "<câu hỏi>" [--trace]
                          [--max-steps 8] [--fact tên=giá_trị ...] [--out <thư mục>]
Trước khi hỏi, hợp đồng được soát (dữ kiện, gán khái niệm) để đồ thị có ContractFact / ConceptInstance; đồ thị công bố
lên Neo4j khi CONTRACT_GRAPH=1 và Neo4j chạy, không thì agent đọc bản dựng trong bộ nhớ. Model agent: CONTRACT_AGENT_MODEL
(mặc định "app" = LLM của app); gán khái niệm: CONCEPT_TAG_MODEL. Đồ thị luật dùng khi LEGAL_GRAPH=1.
In JSON {answer, confidence, path, law, warnings, stats}; --trace in thêm từng bước; --out ghi answer.json, report.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

APP = Path.cwd()
sys.path[:0] = [str(APP), str(APP / "ui"), str(APP / "src"), str(APP / "scripts")]

import server  # noqa: E402  — cấu hình contracts_api.CONFIG như khi chạy app
import contracts_api as api  # noqa: E402
from check_contract_concepts import _legal_graph, _parse_fact, _tag_llm  # noqa: E402
from rag.bridge.catalog import load_catalog  # noqa: E402
from rag.bridge.check import report_markdown  # noqa: E402
from rag.contracts.graph.agent import ask_contract_graph  # noqa: E402


def _agent_llm():
    from rag.bridge.llm import contract_agent_llm
    from rag.config import Settings
    from rag.generate.llm import LLMCache
    s = Settings.load()
    return contract_agent_llm(s, cache=LLMCache(s.cache_dir / "contract_agent_llm.sqlite"))


def main(src: Path, question: str, *, trace: bool = False, max_steps: int = 8, user_facts: dict | None = None,
         out: Path | None = None) -> dict:
    store_root = (out or APP / ".cache") / "ask_contract_graph_store"
    api.CONFIG.root = lambda: store_root
    llm = server.get_pipeline()[0].llm
    api.CONFIG.llm_factory = lambda: llm
    card = api.create(src.read_bytes(), src.name, persist=False)
    contract = api.get(card["contract_id"])
    catalog = load_catalog()
    now = datetime.now(timezone.utc)
    tag_llm, agent_llm = _tag_llm(None, None), _agent_llm()
    answer, report = ask_contract_graph(llm, contract, question, at=now, catalog=catalog, graph=api._graph(),
                                        legal=_legal_graph(), agent_llm=agent_llm, tag_llm=tag_llm,
                                        model=getattr(llm, "model_id", None), max_steps=max_steps,
                                        user_facts=user_facts)
    result = {"question": question, "answer": answer.answer, "confidence": answer.confidence, "path": answer.path,
              "law": answer.law, "warnings": answer.warnings,
              "stats": {**answer.stats, "agent_model": getattr(agent_llm or llm, "model_id", None),
                        "check": {k: report.stats.get(k) for k in ("llm_calls", "seconds", "graph_backend",
                                                                   "build_id")}}}
    if trace:
        result["trace"] = answer.trace
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "answer.json").write_text(json.dumps({**result, "trace": answer.trace}, ensure_ascii=False, indent=2,
                                                    default=str), encoding="utf-8")
        (out / "report.md").write_text(report_markdown(report, catalog), encoding="utf-8")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("question")
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--fact", action="append", default=[], type=_parse_fact)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    print(json.dumps(main(a.src, a.question, trace=a.trace, max_steps=a.max_steps, user_facts=dict(a.fact),
                          out=a.out), ensure_ascii=False, indent=2, default=str))
