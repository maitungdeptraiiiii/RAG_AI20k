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
