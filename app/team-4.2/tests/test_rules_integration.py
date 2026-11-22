"""check_contract và công cụ check_concept chạy được với cả hai evaluator và cho kết quả giống hệt (spec §11 mục 2)."""
import json

import pytest

from rag.bridge.check import check_contract, report_json
from rag.contracts.graph.tools import call_tool, make_tools
from test_bridge_check import AT, CAT, ScriptLLM, contract      # dựng hợp đồng và LLM giả của test_bridge_check
from test_contract_graph_tools import SIGN, demo_view


def _report(kind):
    r = check_contract(ScriptLLM(), contract(), catalog=CAT, at=AT, model="m", evaluator=kind)
    js = report_json(r)
    js["stats"].pop("seconds")
    return js


def test_check_contract_same_report_for_both_evaluators():
    assert json.dumps(_report("network"), sort_keys=True, ensure_ascii=False) == \
        json.dumps(_report("reference"), sort_keys=True, ensure_ascii=False)


def test_check_contract_recheck_path_uses_update_and_matches():
    net, ref = _report("network"), _report("reference")
    assert net["stats"]["recheck_concepts"] > 0                       # hợp đồng có khái niệm "im lặng": đi đường recheck
    assert net["results"] == ref["results"]
    assert any(r["finding"] == "missing_content" for r in net["results"])


@pytest.mark.parametrize("concept", ["probation.pay", "leave.annual", "wage.minimum_regional"])
def test_check_concept_tool_equal_for_both_kinds(monkeypatch, concept):
    out = {}
    for kind in ("reference", "network"):
        monkeypatch.setenv("RAG_RULE_EVALUATOR", kind)
        tools = make_tools(demo_view(), catalog=CAT, day=SIGN, sign_date=SIGN, legal=None)
        out[kind] = call_tool(tools, "check_concept", {"concept_id": concept})
    assert out["network"] == out["reference"] and out["network"]["results"]


def test_unknown_evaluator_name_rejected():
    with pytest.raises(ValueError, match="khong_co"):
        check_contract(ScriptLLM(), contract(), catalog=CAT, at=AT, evaluator="khong_co")


def test_network_evaluator_is_actually_used_and_recheck_goes_through_update(monkeypatch):
    from rag.rules.network.session import NetworkSession
    calls = []
    orig = NetworkSession.update
    monkeypatch.setattr(NetworkSession, "update", lambda self, *a, **k: calls.append(sorted(a[0])) or orig(self, *a, **k))
    check_contract(ScriptLLM(), contract(), catalog=CAT, at=AT, model="m", evaluator="network")
    assert calls and all(isinstance(names, list) for names in calls)


def test_default_evaluator_is_network(monkeypatch):
    from rag.rules.evaluator import default_kind
    monkeypatch.delenv("RAG_RULE_EVALUATOR", raising=False)
    assert default_kind() == "network"
    monkeypatch.setenv("RAG_RULE_EVALUATOR", "reference")
    assert default_kind() == "reference"
    monkeypatch.setenv("RAG_RULE_EVALUATOR", "khong_co")
    with pytest.raises(ValueError, match="khong_co"):
        default_kind()
