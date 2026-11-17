"""Đọc dữ kiện từ đồ thị cho cùng kết quả rule như đường cũ (contract.facts + oplog), trừ khác biệt cố ý spec
2026-11-16 §7: dữ kiện có sửa đổi hiệu lực sau ngày soát giữ giá trị gốc."""
from datetime import date, datetime, timezone
from pathlib import Path

from rag.bridge.catalog import load_catalog
from rag.bridge.engine import evaluate
from rag.bridge.facts_map import build_factset, contract_facts, fact_ops
from rag.bridge.graph_facts import factset_from_graph
from rag.contracts.doc import PageText
from rag.contracts.graph.build import build_graph
from rag.contracts.graph.oplog import OperationLog, machine_op
from rag.contracts.graph.view import MemoryGraphView

CAT = load_catalog()
T = datetime(2026, 11, 16, tzinfo=timezone.utc)
SIGN = date(2025, 1, 2)
DEMO = Path(__file__).resolve().parents[3] / "data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.txt"


def c(value, uid, quote=None):
    return {"value": value, "unit": uid, "quote": quote or value}


def both(text, candidates, ops=()):
    facts = {"candidates": candidates}
    log = OperationLog("c1")
    for o in [*fact_ops(facts, "c1", at=T), *ops]:
        log.add(o)
    old_fs = build_factset(contract_facts(facts, sign_date=SIGN), log.all())
    b, _ = build_graph("c1", [PageText(1, text)], log, file_checksum="x", built_at=T)
    new_fs, _ = factset_from_graph(MemoryGraphView(b), day=SIGN, sign_date=SIGN)
    run = lambda fs: {(r.concept_id, r.rule_id): r for r in evaluate(CAT, fs.facts, set(fs.present), fs.evidence, SIGN)}
    return run(old_fs), run(new_fs)


LEAVE = machine_op("c1", "ASSERT", "concept:leave.annual",
                   {"kind": "concept", "concept_id": "leave.annual", "slots": {"annual_leave": {"value": 8, "unit": "day"}}},
                   "llm", "auto_accepted", source_uid="p0.d2", quote=("được nghỉ phép 08 ngày/năm",), at=T)
SMALL = ("Điều 1. Loại hợp đồng: Không xác định thời hạn. Mức lương chính: 15.000.000 đồng/tháng.\n"
         "Điều 2. Người lao động được nghỉ phép 08 ngày/năm.")


def test_same_findings_without_amendments():
    old, new = both(SMALL, {"labor_kind": [c("Không xác định thời hạn", "p0.d1")],
                            "salary": [c("15.000.000 đồng/tháng", "p0.d1")]}, [LEAVE])
    assert old.keys() == new.keys()
    for k in old:
        assert (old[k].finding, old[k].status, old[k].facts_used) == (new[k].finding, new[k].status, new[k].facts_used), k


def test_demo_differs_only_where_salary_is_amended_later():
    """Khác biệt cố ý spec §7: đường cũ lấy 17 triệu (phụ lục, hiệu lực 01/07/2025), đồ thị lấy 15 triệu tại ngày ký."""
    old, new = both(DEMO.read_text(encoding="utf-8"), {
        "salary": [c("15.000.000 đồng/tháng", "p0.d2"),
                   c("17.000.000 đồng/tháng", "p2.d1", "được điều chỉnh từ 15.000.000 đồng/tháng lên 17.000.000 đồng/tháng")],
        "probation_salary": [c("85%", "p0.d6")], "probation_period": [c("02 tháng", "p0.d6")]})
    assert old.keys() == new.keys()
    differ = [k for k in old if (old[k].finding, old[k].facts_used) != (new[k].finding, new[k].facts_used)]
    assert differ, "phải có ít nhất một rule dùng lương căn bản"
    for k in differ:
        assert old[k].facts_used["base_salary_vnd"]["value"] == 17000000
        assert new[k].facts_used["base_salary_vnd"]["value"] == 15000000
        assert new[k].facts_used["base_salary_vnd"]["later_amendments"][0]["valid_from"] == "2025-07-01"
