"""Đo độ ổn định của agent trên đồ thị hợp đồng: cùng hợp đồng, cùng model, nhiều lần mỗi câu, hai cấu hình.

  before: công cụ trả kết quả "mỏng", không chặn kết luận khi còn dẫn chiếu chưa đọc, không Text2Cypher
  after : cấu hình hiện tại (ngữ cảnh kèm theo, chặn một lần, Text2Cypher khi có Neo4j)

Chạy từ app/team-4.2:  uv run python scripts/bench_contract_agent.py <file hợp đồng> <thư mục ra> [--runs 5]
Hợp đồng được soát MỘT lần (dùng chung); agent gọi LLM của app KHÔNG cache để mỗi lần là một lần gọi model thật.
Ghi runs.jsonl (mỗi lần một dòng) và summary.md.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

APP = Path.cwd()
sys.path[:0] = [str(APP), str(APP / "ui"), str(APP / "src"), str(APP / "scripts")]

import server  # noqa: E402,F401  — nạp .env, cấu hình contracts_api
import contracts_api as api  # noqa: E402
from check_contract_concepts import _legal_graph, _tag_llm  # noqa: E402
from rag.bridge.basis import AnchorLawBasis  # noqa: E402
from rag.bridge.catalog import load_catalog  # noqa: E402
from rag.bridge.check import check_contract, contract_view  # noqa: E402
from rag.contracts.graph.agent import GraphAgent, agent_context  # noqa: E402
from rag.contracts.graph.build import graph_mask_state  # noqa: E402
from rag.contracts.graph.tools import make_tools  # noqa: E402


def _has(text: str, *patterns: str) -> bool:
    return all(re.search(p, text, re.I) for p in patterns)


AMOUNT = r"12[.,]?750[.,]?000|12,75 triệu"
QUESTIONS = [
    ("Q1", "Lúc thử việc tôi được trả bao nhiêu?", lambda a, tools: _has(a, AMOUNT)),
    ("Q2", "Lúc thử việc tôi được trả bao nhiêu? Mức đó có đúng luật không?",
     lambda a, tools: _has(a, AMOUNT) and "check_concept" in tools),
    ("Q3", "Phụ lục có sửa điều khoản nào của hợp đồng không, từ ngày nào?",
     lambda a, tools: _has(a, r"Điều 2", r"01/0?7/2025|2025-07-01|1/7/2025|01 tháng 0?7")),
    ("Q4", "Lương căn bản của tôi là bao nhiêu?",
     lambda a, tools: _has(a, r"15[.,]?000[.,]?000|15 triệu", r"17[.,]?000[.,]?000|17 triệu")),
]
CONFIGS = {"before": dict(expand_context=False, text2cypher=False, check_references=False),
           "after": dict(expand_context=True, text2cypher=True, check_references=True)}


def _nocache_llm():
    from rag.config import Settings
    from rag.generate.llm import OpenAIChatLLM
    s = Settings.load()
    return OpenAIChatLLM(s.llm_model, temperature=s.llm_temperature, base_url=s.llm_base_url, api_key=s.llm_api_key,
                         cache=None)


def main(src: Path, out: Path, runs: int) -> None:
    out.mkdir(parents=True, exist_ok=True)
    api.CONFIG.root = lambda: out / "contracts_store"
    llm = server.get_pipeline()[0].llm
    api.CONFIG.llm_factory = lambda: llm
    contract = api.get(api.create(src.read_bytes(), src.name, persist=False)["contract_id"])
    catalog, legal, now = load_catalog(), _legal_graph(), datetime.now(timezone.utc)
    report = check_contract(llm, contract, catalog=catalog, basis=AnchorLawBasis(catalog, legal), at=now,
                            tag_llm=_tag_llm(None, None), graph=api._graph())
    view, build_id, _, doc = contract_view(contract, api._graph(), now)
    agent_llm = _nocache_llm()
    print(json.dumps({"backend": view.backend, "build_id": build_id, "day": report.day.isoformat(),
                      "model": agent_llm.model_id}, ensure_ascii=False), flush=True)
    rows = []
    with (out / "runs.jsonl").open("w", encoding="utf-8") as f:
        for cfg_name, cfg in CONFIGS.items():
            tools = make_tools(view, catalog=catalog, day=report.day, sign_date=contract.sign_date, legal=legal,
                               expand_context=cfg["expand_context"], text2cypher=cfg["text2cypher"])
            for qid, question, ok in QUESTIONS:
                for i in range(runs):
                    agent = GraphAgent(agent_llm, tools, view, mask=graph_mask_state(doc),
                                       context=agent_context(view, catalog, sign_date=contract.sign_date))
                    agent.check_references = cfg["check_references"]
                    try:
                        a = agent.ask(question)
                        used = [s["tool"] for s in a.trace]
                        row = {"config": cfg_name, "q": qid, "run": i, "correct": bool(ok(a.answer, used)),
                               "confidence": a.confidence, "steps": a.stats["steps"], "llm_calls": a.stats["llm_calls"],
                               "seconds": a.stats["seconds"], "tools": used, "warnings": a.warnings,
                               "answer": a.answer}
                    except Exception as exc:  # noqa: BLE001 — một lần lỗi không làm dừng cả phép đo
                        row = {"config": cfg_name, "q": qid, "run": i, "correct": False, "error": repr(exc)[:300]}
                    rows.append(row)
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    f.flush()
                    print(f"{cfg_name} {qid} #{i}: {'OK ' if row['correct'] else 'BAD'} "
                          f"{row.get('confidence')} steps={row.get('steps')}", flush=True)
    (out / "summary.md").write_text(_summary(rows, runs), encoding="utf-8")


def _summary(rows: list[dict], runs: int) -> str:
    lines = [f"# Đo agent: {runs} lần mỗi câu", "",
             "| Câu | before đúng | after đúng | before bước TB | after bước TB | before `answer` | after `answer` |",
             "|---|---|---|---|---|---|---|"]
    for qid, *_ in QUESTIONS:
        cell = {}
        for cfg in CONFIGS:
            rs = [r for r in rows if r["config"] == cfg and r["q"] == qid]
            steps = [r["steps"] for r in rs if "steps" in r]
            cell[cfg] = (sum(r["correct"] for r in rs), len(rs), sum(steps) / len(steps) if steps else 0,
                         sum(r.get("confidence") == "answer" for r in rs))
        b, a = cell["before"], cell["after"]
        lines.append(f"| {qid} | {b[0]}/{b[1]} | {a[0]}/{a[1]} | {b[2]:.1f} | {a[2]:.1f} | {b[3]}/{b[1]} | {a[3]}/{a[1]} |")
    for cfg in CONFIGS:
        rs = [r for r in rows if r["config"] == cfg]
        lines.append(f"\n**{cfg}**: đúng {sum(r['correct'] for r in rs)}/{len(rs)}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--runs", type=int, default=5)
    a = ap.parse_args()
    main(a.src, a.out, a.runs)
