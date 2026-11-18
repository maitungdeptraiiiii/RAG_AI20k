import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from rag.bridge.catalog import load_catalog
from rag.bridge.facts_map import fact_ops
from rag.contracts.doc import PageText
from rag.contracts.graph.build import build_graph
from rag.contracts.graph.oplog import OperationLog, machine_op
from rag.contracts.graph.tools import call_tool, make_tools
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
PAY = machine_op("c1", "ASSERT", "concept:probation.pay",
                 {"kind": "concept", "concept_id": "probation.pay", "slots": {}},
                 "llm", "auto_accepted", source_uid="p0.d6", quote=("hưởng 85% mức lương căn bản",), at=T)


def demo_view():
    log = OperationLog("c1")
    for o in [*fact_ops(FACTS, "c1", at=T), PAY]:
        log.add(o)
    b, _ = build_graph("c1", [PageText(1, DEMO.read_text(encoding="utf-8"))], log, file_checksum="x", built_at=T)
    return MemoryGraphView(b)


class FakeLegal:
    def __init__(self):
        self.calls = []

    def text_at(self, pid, day):
        self.calls.append(("text_at", pid, day))
        return {"in_force": True, "text": "Tiền lương của người lao động trong thời gian thử việc ... ít nhất bằng 85%",
                "citation": {"provision_id": pid}}


@pytest.fixture
def tools():
    return make_tools(demo_view(), catalog=CAT, day=SIGN, sign_date=SIGN, legal=None)


def test_tool_names_and_specs(tools):
    assert set(tools) == {"find_units", "find_concept", "expand", "find_path", "subgraph", "contract_facts",
                          "law_text_at", "law_changes", "law_guidance", "law_references", "concept_basis",
                          "check_concept"}
    assert tools["expand"].params["node_id"]["required"] is True and tools["expand"].doc


def test_tools_reject_bad_args(tools):
    assert "error" in call_tool(tools, "expand", {"node_id": "c1", "rel_types": ["DELETE"]})
    assert "error" in call_tool(tools, "find_path", {"src": "c1"})
    assert "error" in call_tool(tools, "find_path", {"src": "c1", "dst": "c1:p0.d2@1", "max_hops": 9})
    assert "error" in call_tool(tools, "expand", {"node_id": "c1", "direction": "up"})
    assert "error" in call_tool(tools, "expand", {"node_id": 5})
    assert "error" in call_tool(tools, "nope", {})
    assert "error" in call_tool(tools, "expand", {"node_id": "c1", "evil": 1})
    assert call_tool(tools, "expand", {"node_id": "c2:p0.d1@1"}) == {"hops": []}


def test_find_units_by_text_and_label(tools):
    by_text = call_tool(tools, "find_units", {"text": "thử việc"})["units"]
    assert by_text[0]["node_id"] == "c1:p0.d6@1"
    by_label = call_tool(tools, "find_units", {"label": "Điều 2"})["units"]
    assert [u["node_id"] for u in by_label] == ["c1:p0.d2@1"]
    assert "error" in call_tool(tools, "find_units", {})


def test_find_concept_and_path(tools):
    got = call_tool(tools, "find_concept", {"concept_id": "probation.pay"})
    assert got["label"] == CAT.concepts["probation.pay"].label
    assert [i["about"] for i in got["instances"]] == ["c1:p0.d6@1"]
    p = call_tool(tools, "find_path", {"src": "c1:p0.d6@1", "dst": "c1:p0.d2@1"})
    assert [(h["rel"], h["node"]["node_id"]) for h in p["path"]] == [("REFERS_TO", "c1:p0.d2@1")]
    assert "error" in call_tool(tools, "find_concept", {"concept_id": "khong.co"})


def test_contract_facts_shows_later_amendment(tools):
    f = call_tool(tools, "contract_facts", {"name": "base_salary_vnd"})["facts"][0]
    assert (f["name"], f["value"], f["uid"]) == ("base_salary_vnd", 15000000, "p0.d2")
    assert f["later_amendments"][0]["valid_from"] == "2025-07-01"
    names = {x["name"] for x in call_tool(tools, "contract_facts", {})["facts"]}
    assert {"base_salary_vnd", "probation_pay_pct", "sign_date"} <= names


def test_check_concept_runs_engine_without_llm(tools):
    out = call_tool(tools, "check_concept", {"concept_id": "probation.pay"})
    assert out["concept_id"] == "probation.pay" and out["results"]
    r = out["results"][0]
    assert {"rule_id", "finding", "status", "law_values", "facts_used", "missing_facts", "evidence"} <= set(r)
    assert any(x["finding"] == "ok" for x in out["results"])           # 85% >= 85%


def test_law_tools_without_legal_graph(tools):
    assert call_tool(tools, "law_text_at", {"pid": "bllđ-2019#d26"}) == {"error": "legal_graph_unavailable"}
    basis = call_tool(tools, "concept_basis", {"concept_id": "probation.pay"})
    assert "basis_unavailable" in basis["problems"]


def test_law_text_at_uses_sign_date_by_default():
    legal = FakeLegal()
    tl = make_tools(demo_view(), catalog=CAT, day=SIGN, sign_date=SIGN, legal=legal)
    out = call_tool(tl, "law_text_at", {"pid": "x#d26"})
    assert out["in_force"] and legal.calls == [("text_at", "x#d26", SIGN)]
    call_tool(tl, "law_text_at", {"pid": "x#d26", "day": "2025-08-01"})
    assert legal.calls[-1][2] == date(2025, 8, 1)
    assert "error" in call_tool(tl, "law_text_at", {"pid": "x#d26", "day": "hôm qua"})


def test_output_is_capped(tools):
    out = call_tool(tools, "subgraph", {"node_id": "c1", "hops": 2})
    assert len(json.dumps(out, ensure_ascii=False)) <= 3200 and out.get("more", 0) > 0


def test_find_concept_carries_referenced_clause_text(tools):
    inst = call_tool(tools, "find_concept", {"concept_id": "probation.pay"})["instances"][0]
    refs = {r["node_id"]: r for r in inst["context"]["refers_to"]}
    assert "c1:p0.d2@1" in refs and "15.000.000" in refs["c1:p0.d2@1"]["text"]
    assert refs["c1:p0.d2@1"]["label"] == "Điều 2"


def test_find_units_carries_amendments_with_date(tools):
    unit = call_tool(tools, "find_units", {"label": "Điều 2"})["units"][0]
    amended = unit["context"]["amended_by"]
    assert [(a["node_id"], a["valid_from"]) for a in amended] == [("c1:p2.d1@1", "2025-07-01")]
    assert "17.000.000" in amended[0]["raw"]


def test_context_can_be_switched_off_for_ablation():
    tl = make_tools(demo_view(), catalog=CAT, day=SIGN, sign_date=SIGN, legal=None, expand_context=False)
    inst = call_tool(tl, "find_concept", {"concept_id": "probation.pay"})["instances"][0]
    assert "context" not in inst
    assert "context" not in call_tool(tl, "find_units", {"label": "Điều 2"})["units"][0]
