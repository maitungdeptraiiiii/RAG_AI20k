"""D40: gói luật được chọn đi suốt luồng (đồ thị, check_contract) — kế hoạch 2026-11-23-w04-remaining, Task 2."""
from datetime import datetime, timezone

import pytest

from rag.bridge.check import check_contract
from rag.contracts.doc import PageText
from rag.contracts.graph.build import build_graph
from rag.contracts.graph.oplog import OperationLog, machine_op
from rag.rules.loader import load_packs

T = datetime(2026, 11, 12, tzinfo=timezone.utc)
PAGES = [PageText(1, "Điều 1. Bên A có quyền lấy lại nhà bất cứ lúc nào.\n")]


def _legacy_ops(concept_id: str):
    """Thao tác ASSERT cũ (trước khi ghi `holder`): đồ thị phải tra vai trò trong danh mục."""
    log = OperationLog("c1")
    log.add(machine_op("c1", "ASSERT", "party", {"kind": "party", "role": "BEN_THUE", "label": "Bên thuê"}, "rule",
                       "auto_accepted", at=T))
    op = machine_op("c1", "ASSERT", concept_id, {"kind": "concept", "concept_id": concept_id, "slots_raw": {}, "slots": {},
                                                  "catalog_version": "t", "found_by": "tagger"},
                    "llm", "auto_accepted", source_uid="p0.d1", quote=("Bên A có quyền lấy lại nhà",), at=T)
    log.add(op)
    return log, op


def test_build_graph_legacy_op_uses_given_catalog():
    cat = load_packs(["civil_lease"])
    concept_id = next(c.id for c in cat.concepts.values() if c.holder == "BEN_THUE")
    log, op = _legacy_ops(concept_id)
    build, _ = build_graph("c1", PAGES, log, file_checksum="x", built_at=T, catalog=cat)
    edges = {(e.type, e.src, e.dst) for e in build.edges}
    assert ("HOLDER", f"c1:ci:{op.op_id}", "c1:party:BEN_THUE") in edges


def test_build_graph_legacy_op_without_catalog_keeps_labor_default():
    cat = load_packs(["civil_lease"])
    concept_id = next(c.id for c in cat.concepts.values() if c.holder == "BEN_THUE")
    log, op = _legacy_ops(concept_id)
    build, _ = build_graph("c1", PAGES, log, file_checksum="x", built_at=T)       # tương thích: labor, không có khái niệm thuê nhà
    assert not any(e.type == "HOLDER" for e in build.edges)


def test_auto_kind_still_extracts_facts_when_contract_has_none(monkeypatch):
    """`document_kind="auto"` ghi `facts["document_kind"]` trước bước trích: không được coi như đã có dữ kiện."""
    import importlib.util
    import pathlib
    import rag.bridge.check as check
    spec = importlib.util.spec_from_file_location("pack_cases_mod", pathlib.Path(__file__).with_name("pack_cases.py"))
    cases = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cases)
    calls = []
    real = check.extract_facts
    monkeypatch.setattr(check, "extract_facts", lambda *a, **k: calls.append(1) or real(*a, **k))
    contract = cases.loan_contract()
    assert not contract.facts
    check_contract(cases.ScriptedLoanLLM(), contract, at=cases.AT, document_kind="auto",
                   user_facts={"special_law_applies": False})
    assert calls


def _pack_cases():
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location("pack_cases_mod", pathlib.Path(__file__).with_name("pack_cases.py"))
    cases = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cases)
    return cases


def _loan_catalog_with_extra():
    """Gói vay + một trường trích riêng của gói KHÔNG có trong danh mục chung fact_catalog.json (như gói mới cắm vào)."""
    import dataclasses
    cat = load_packs(["civil_loan"])
    extra = {"key": "zz_pack_only", "label": "Trường riêng của gói", "kind": "text"}
    return dataclasses.replace(cat, context=dataclasses.replace(
        cat.context, extract_fields=(*cat.context.extract_fields, extra)))


def test_pack_fields_extracted_after_kind_is_known():
    """Hạn chế R.6: UI trích dữ kiện lúc tải lên theo danh mục chung (chưa biết gói); khi soát bằng gói, trường riêng của
    gói chưa hỏi được trích bổ sung đúng một lần."""
    import json
    from rag.contracts.facts import extract_facts
    cases = _pack_cases()

    class LoanLLM(cases.ScriptedLoanLLM):
        def __init__(self):
            super().__init__()
            self.more = 0

        def complete(self, system, user):
            payload = json.loads(user)
            if [f["key"] for f in payload.get("fields_wanted") or []] == ["zz_pack_only"]:
                self.more += 1
                return json.dumps({"fields": {"zz_pack_only": {"value": "30%/năm", "unit": "p0.d2",
                                                               "quote": "Lãi suất vay là 30%/năm"}}}, ensure_ascii=False)
            return super().complete(system, user)

    llm, contract, cat = LoanLLM(), cases.loan_contract(), _loan_catalog_with_extra()
    extract_facts(llm, contract)                                  # lúc tải lên: danh mục chung
    assert "zz_pack_only" not in contract.facts["fields_tried"] and "loan_interest" in contract.facts["fields_tried"]
    check_contract(llm, contract, at=cases.AT, catalog=cat, user_facts={"special_law_applies": False})
    assert llm.more >= 1 and contract.facts["candidates"]["zz_pack_only"][0]["value"] == "30%/năm"
    calls = llm.more
    check_contract(llm, contract, at=cases.AT, catalog=cat, user_facts={"special_law_applies": False})
    assert llm.more == calls                                      # đã thử: không trích lại


def test_pack_fields_extraction_error_warns_and_review_continues(monkeypatch):
    import rag.bridge.check as check
    from rag.contracts.facts import extract_facts
    from rag.contracts.llm_json import ContractAIError
    cases = _pack_cases()
    llm, contract = cases.ScriptedLoanLLM(), cases.loan_contract()
    extract_facts(llm, contract)

    def boom(*a, **k):
        raise ContractAIError()
    monkeypatch.setattr(check, "extract_more_fields", boom)
    report = check_contract(llm, contract, at=cases.AT, catalog=_loan_catalog_with_extra(),
                            user_facts={"special_law_applies": False})
    assert report.results and any("zz_pack_only" in w for w in report.warnings)
    assert "zz_pack_only" not in contract.facts["fields_tried"]
