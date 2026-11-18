import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from rag.bridge.catalog import load_catalog
from rag.bridge.facts_map import fact_ops
from rag.contracts.doc import PageText
from rag.contracts.graph.agent import AGENT_PROMPT, GraphAgent, agent_context
from rag.contracts.graph.build import build_graph, graph_mask_state
from rag.contracts.graph.oplog import OperationLog, machine_op
from rag.contracts.graph.tools import make_tools
from rag.contracts.graph.view import MemoryGraphView

CAT = load_catalog()
T = datetime(2026, 11, 16, tzinfo=timezone.utc)
SIGN = date(2025, 1, 2)
DEMO = Path(__file__).resolve().parents[3] / "data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.txt"
FACTS = {"candidates": {
    "salary": [{"value": "15.000.000 đồng/tháng", "unit": "p0.d2", "quote": "15.000.000 đồng/tháng"},
               {"value": "17.000.000 đồng/tháng", "unit": "p2.d1",
                "quote": "được điều chỉnh từ 15.000.000 đồng/tháng lên 17.000.000 đồng/tháng"}],
    "probation_salary": [{"value": "85%", "unit": "p0.d6", "quote": "hưởng 85% mức lương căn bản"}],
    "probation_period": [{"value": "02 tháng", "unit": "p0.d6", "quote": "Thời gian thử việc: 02 tháng"}]}}
PAY = machine_op("c1", "ASSERT", "concept:probation.pay", {"kind": "concept", "concept_id": "probation.pay", "slots": {}},
                 "llm", "auto_accepted", source_uid="p0.d6", quote=("hưởng 85% mức lương căn bản",), at=T)
A6, A2 = "c1:p0.d6@1", "c1:p0.d2@1"


def make_agent(llm, max_steps=8):
    log = OperationLog("c1")
    for o in [*fact_ops(FACTS, "c1", at=T), PAY]:
        log.add(o)
    b, doc = build_graph("c1", [PageText(1, DEMO.read_text(encoding="utf-8"))], log, file_checksum="x", built_at=T)
    view = MemoryGraphView(b)
    tools = make_tools(view, catalog=CAT, day=SIGN, sign_date=SIGN, legal=None)
    return GraphAgent(llm, tools, view, mask=graph_mask_state(doc),
                      context=agent_context(view, CAT, sign_date=SIGN), max_steps=max_steps)


class ScriptAgentLLM:
    """Trả lần lượt các bước đã soạn; ghi lại payload nhận được."""

    def __init__(self, steps):
        self.steps, self.seen = list(steps), []

    def complete(self, system, user):
        assert system.startswith(AGENT_PROMPT[:40])
        payload = json.loads(user)
        self.seen.append(payload)
        step = self.steps.pop(0)
        return step(payload) if callable(step) else (step if isinstance(step, str) else json.dumps(step, ensure_ascii=False))


def call(tool, **args):
    return {"thought": f"gọi {tool}", "tool": tool, "args": args}


def final(answer, path, confidence="answer", law=()):
    return {"final": {"answer": answer, "path": path, "law": list(law), "confidence": confidence}}


DEMO_STEPS = [call("find_concept", concept_id="probation.pay"),
              call("find_path", src=A6, dst=A2),
              call("contract_facts", name="base_salary_vnd"),
              call("check_concept", concept_id="probation.pay"),
              final("Lương thử việc 85% × 15.000.000 = 12.750.000 đồng/tháng, đúng luật (tối thiểu 85%). "
                    "Phụ lục 2 nâng lương từ 01/07/2025, sau khi thử việc kết thúc.", [A6, A2],
                    law=["bo-luat:45/2019/QH14#d26"])]


def test_demo_question_answers_with_path():
    llm = ScriptAgentLLM(DEMO_STEPS)
    a = make_agent(llm).ask("Lúc thử việc tôi được trả bao nhiêu?")
    assert a.confidence == "answer" and "12.750.000" in a.answer and a.warnings == []
    assert [p["node_id"] for p in a.path] == [A6, A2] and a.path[0]["label"].startswith("Điều 6")
    assert [s["tool"] for s in a.trace] == ["find_concept", "find_path", "contract_facts", "check_concept"]
    assert a.law == ["bo-luat:45/2019/QH14#d26"]
    assert a.stats["steps"] == 4 and a.stats["llm_calls"] == 5 and a.stats["backend"] == "memory"
    first = llm.seen[0]
    assert first["context"]["sign_date"] == "2025-01-02"
    assert any(c["concept_id"] == "probation.pay" and c["about"] == A6 for c in first["context"]["concepts"])
    assert {t["name"] for t in first["tools"]} >= {"expand", "find_path", "check_concept"}
    assert llm.seen[-1]["steps"][-1]["tool"] == "check_concept" and llm.seen[-1]["steps"][-1]["result"]["results"]


def test_path_carries_real_edges_origin_full_text_and_unused_nodes():
    a = make_agent(ScriptAgentLLM(DEMO_STEPS)).ask("Lúc thử việc tôi được trả bao nhiêu?")
    first, second = a.path
    assert "edge" not in first and first["found_at"] == {"step": 1, "tool": "find_concept"}
    assert second["edge"]["verified"] is True and second["edge"]["rel"] and second["edge"]["dir"] in ("out", "in")
    assert first["text_full"].startswith(first["text"]) and len(first["text"]) <= 160
    on_path = {A6, A2}
    assert a.seen_unused and not on_path & {n["node_id"] for n in a.seen_unused}
    assert a.stats["seen"] >= len(a.seen_unused) + 2
    t = a.trace[0]
    assert t["error"] is None and t["n_nodes"] == len(t["nodes"]) and A6 in t["nodes"]


def test_concept_node_on_path_keeps_concept_id_and_about_edge():
    def conclude(payload):
        ci = payload["steps"][-1]["result"]["instances"][0]["node_id"]
        return json.dumps(final("x", [ci, A6], confidence="partial"))
    a = make_agent(ScriptAgentLLM([call("find_concept", concept_id="probation.pay"), conclude])).ask("q")
    ci, unit = a.path
    assert ci["concept_id"] == "probation.pay" and ci["node_type"] == "ConceptInstance"
    assert unit["edge"] == {"verified": True, "rel": "ABOUT", "dir": "out", "props": {}}


def test_tool_error_is_recorded_on_trace_step():
    steps = [call("expand", node_id=A6, rel_types=["DELETE"]), final("không rõ", [], confidence="cannot")]
    a = make_agent(ScriptAgentLLM(steps)).ask("q")
    assert a.trace[0]["error"] and a.trace[0]["n_nodes"] == 0


def test_invented_path_downgrades():
    steps = DEMO_STEPS[:4] + [final("12.750.000 đồng/tháng, đúng luật", [A6, "c1:p0.d99@1"])]
    a = make_agent(ScriptAgentLLM(steps)).ask("Lúc thử việc tôi được trả bao nhiêu?")
    assert a.confidence == "partial" and any("đường đi" in w for w in a.warnings)
    assert a.path[1]["edge"] == {"verified": False}


def test_path_with_unseen_but_real_node_downgrades():
    steps = [call("find_concept", concept_id="probation.pay"), final("x", [A6, "c1:p0.d7@1"])]
    a = make_agent(ScriptAgentLLM(steps)).ask("q")
    assert a.confidence == "partial"


def test_legal_claim_without_check_downgrades():
    steps = [call("find_path", src=A6, dst=A2), final("12.750.000 đồng/tháng, đúng luật", [A6, A2])]
    a = make_agent(ScriptAgentLLM(steps)).ask("q")
    assert a.confidence == "partial" and any("bộ kiểm luật" in w for w in a.warnings)


def test_tool_error_is_shown_to_llm_and_run_continues():
    steps = [call("expand", node_id=A6, rel_types=["DELETE"]), final("không rõ", [], confidence="cannot")]
    llm = ScriptAgentLLM(steps)
    a = make_agent(llm).ask("q")
    assert "error" in llm.seen[1]["steps"][0]["result"] and a.confidence == "cannot"


def test_bad_json_retries_once_then_cannot():
    a = make_agent(ScriptAgentLLM(["không phải json", "vẫn không"])).ask("q")
    assert a.confidence == "cannot" and a.stats["llm_calls"] == 2


def test_bad_json_once_then_recovers():
    llm = ScriptAgentLLM(["{hỏng", final("không rõ", [], confidence="cannot")])
    a = make_agent(llm).ask("q")
    assert a.stats["llm_calls"] == 2 and "error" in llm.seen[1]["steps"][-1]


def test_step_limit_forces_final_partial():
    steps = [call("expand", node_id=A6), call("expand", node_id=A2),
             lambda p: json.dumps(final("Lương căn bản 15.000.000 đồng/tháng" if p.get("force_final") else "?", [A6, A2]))]
    a = make_agent(ScriptAgentLLM(steps), max_steps=2).ask("q")
    assert a.confidence == "partial" and "15.000.000" in a.answer and any("giới hạn" in w for w in a.warnings)


def test_pii_masked_in_payload_and_unmasked_in_answer():
    def echo(p):
        token = re.search(r"\[HD_[A-Z_]+\d+\]", p["question"]).group(0)
        return json.dumps(final(f"Số {token} không có trong hợp đồng", [], confidence="cannot"))
    llm = ScriptAgentLLM([echo])
    a = make_agent(llm).ask("CCCD của tôi là 036196001234, đúng không?")
    assert "036196001234" not in json.dumps(llm.seen, ensure_ascii=False)
    assert "036196001234" in a.answer


def test_on_step_reports_each_tool_call():
    events = []
    make_agent(ScriptAgentLLM(DEMO_STEPS)).ask("Lúc thử việc tôi được trả bao nhiêu?", on_step=events.append)
    assert [e["tool"] for e in events] == ["find_concept", "find_path", "contract_facts", "check_concept"]
    assert [e["n"] for e in events] == [1, 2, 3, 4] and all(e["type"] == "step" for e in events)
    assert events[0]["args"] == {"concept_id": "probation.pay"} and isinstance(events[0]["result"], str)


def test_history_is_masked_and_capped():
    llm = ScriptAgentLLM([final("ok", [], confidence="cannot")])
    history = [{"query": f"q{i}", "answer": f"a{i}"} for i in range(4)]
    history.append({"query": "CCCD 036196001234 của tôi?", "answer": "x" * 900})
    make_agent(llm).ask("còn gì nữa?", history=history)
    h = llm.seen[0]["history"]
    assert len(h) == 3 and h[0]["query"] == "q2" and len(h[-1]["answer"]) == 500
    assert "036196001234" not in json.dumps(llm.seen, ensure_ascii=False)
    llm2 = ScriptAgentLLM([final("ok", [], confidence="cannot")])
    make_agent(llm2).ask("q", history=["rác", None])
    assert "history" not in llm2.seen[0]


def test_final_without_reading_referenced_clause_is_sent_back_once():
    steps = [call("expand", node_id=A6, rel_types=["HAS_VALUE"]),
             final("85% lương căn bản", [A6]),
             call("expand", node_id=A6, rel_types=["REFERS_TO"], direction="out"),
             final("85% × 15.000.000 = 12.750.000 đồng/tháng", [A6, A2])]
    llm = ScriptAgentLLM(steps)
    a = make_agent(llm).ask("Lúc thử việc tôi được trả bao nhiêu?")
    nudge = llm.seen[2]["steps"][-1]
    assert "error" in nudge and A2 in nudge["unread_references"]
    assert a.confidence == "answer" and a.warnings == [] and a.stats["llm_calls"] == 4


def test_ignoring_the_nudge_downgrades():
    steps = [call("expand", node_id=A6, rel_types=["HAS_VALUE"]),
             final("85% lương căn bản", [A6]), final("85% lương căn bản", [A6])]
    a = make_agent(ScriptAgentLLM(steps)).ask("q")
    assert a.confidence == "partial" and any("dẫn chiếu" in w for w in a.warnings)


def test_node_ids_in_cypher_rows_count_as_seen():
    from rag.contracts.graph.tools import Tool
    agent = make_agent(ScriptAgentLLM([call("cypher_query", query="..."), final("Điều 6 dẫn chiếu Điều 2", [A6, A2])]))
    agent.tools["cypher_query"] = Tool("cypher_query", "giả", {"query": {"type": "str", "required": True}},
                                       lambda a: {"rows": [{"src_id": A6, "dst_id": A2, "c": "c1"}], "truncated": False})
    a = agent.ask("q")
    assert a.confidence == "answer" and a.warnings == []


def test_contract_node_id_in_cypher_rows_counts_as_seen():
    from rag.contracts.graph.tools import Tool
    agent = make_agent(ScriptAgentLLM([call("cypher_query", query="..."), final("x", ["c1"])]))
    agent.tools["cypher_query"] = Tool("cypher_query", "giả", {"query": {"type": "str", "required": True}},
                                       lambda a: {"rows": [{"c": "c1"}], "truncated": False})
    assert agent.ask("q").confidence == "answer"


def test_reference_check_can_be_switched_off_for_ablation():
    steps = [call("expand", node_id=A6, rel_types=["HAS_VALUE"]), final("85% lương căn bản", [A6])]
    agent = make_agent(ScriptAgentLLM(steps))
    agent.check_references = False
    a = agent.ask("q")
    assert a.confidence == "answer" and a.warnings == [] and a.stats["llm_calls"] == 2
