"""D36 (spec bản 3, G7/G9/G10): ba miền lao động, vay, thuê nhà chạy được cùng engine; chọn gói theo loại hợp đồng;
hợp đồng thuê nhà đi hết check_contract mà không có khái niệm hay chữ "lao động" nào."""
import json
from datetime import datetime, timezone

from rag.bridge.check import check_contract, contract_view
from rag.contracts.doc import PageText
from rag.contracts.models import Contract
from rag.contracts.structure import parse_contract, to_contract_units
from rag.rules.loader import load_packs, packs_for_kind

AT = datetime(2026, 11, 14, 9, 0)
LEASE_TEXT = ("Bên A: ông Trần Văn B, là Bên cho thuê. Bên B: bà Lê Thị C, là Bên thuê. Ký ngày 02 tháng 01 năm 2025.\n"
              "Điều 1. Bên A cho Bên B thuê căn nhà số 1 phố Giả Định, diện tích 50 m2.\n"
              "Điều 2. Bên A có quyền lấy lại nhà bất cứ lúc nào trong thời hạn thuê.")


class ScriptedLeaseLLM:
    """Trả lời theo payload (không theo câu chữ prompt), ghi lại mọi system prompt."""

    def __init__(self):
        self.systems: list[str] = []

    def complete(self, system, user):
        payload = json.loads(user)
        self.systems.append(system)
        if "fields_wanted" in payload:
            return json.dumps({"type": "Hợp đồng thuê nhà ở",
                               "parties": [{"name": "Trần Văn B", "role": "Bên cho thuê", "unit": "p0.pre",
                                            "quote": "là Bên cho thuê"},
                                           {"name": "Lê Thị C", "role": "Bên thuê", "unit": "p0.pre",
                                            "quote": "là Bên thuê"}],
                               "sign_date": {"value": "2025-01-02", "unit": "p0.pre",
                                             "quote": "Ký ngày 02 tháng 01 năm 2025"},
                               "fields": {}}, ensure_ascii=False)
        uids = [u["uid"] for u in payload.get("units") or []]
        items = [{"concept": "lease.landlord_termination", "uid": "p0.d2",
                  "quote": "Bên A có quyền lấy lại nhà bất cứ lúc nào trong thời hạn thuê",
                  "slots": {"landlord_may_terminate_at_will": True}}] if "p0.d2" in uids else []
        return json.dumps({"items": items}, ensure_ascii=False)


def lease_contract() -> Contract:
    pages = [PageText(1, LEASE_TEXT)]
    doc = parse_contract(pages)
    units = to_contract_units(doc)
    return Contract("c1", "thue.txt", False, datetime(2026, 11, 14, tzinfo=timezone.utc),
                    "\n".join(u.text for u in units), list(units), len(units), doc=doc, page_texts=list(pages),
                    file_checksum="x")


def test_each_contract_kind_picks_exactly_its_own_pack():
    picked = {k: packs_for_kind(k) for k in ("labor_contract", "loan_contract", "lease_contract")}
    assert picked == {"labor_contract": ["labor"], "loan_contract": ["civil_loan"], "lease_contract": ["civil_lease"]}


def test_three_packs_load_together_without_conflict():
    both = load_packs(["labor", "civil_loan", "civil_lease"])
    assert {"NLD", "BEN_VAY", "BEN_THUE"} <= set(both.roles)
    prefixes = {cid.split(".")[0] for cid in both.concepts}
    assert {"loan", "lease", "civil", "content"} <= prefixes
    assert both.context.document_label == "hợp đồng"                     # nhiều miền: nhãn chung


def test_prompts_for_lease_have_no_labor_wording():
    from rag.bridge.recheck import recheck_prompt
    from rag.bridge.tagger import tag_prompt
    from rag.contracts.graph.agent import agent_prompt
    ctx = load_packs(["civil_lease"]).context
    for render in (tag_prompt, recheck_prompt, agent_prompt):
        text = render(ctx)
        assert "lao động" not in text and "hợp đồng thuê nhà ở" in text


def test_lease_contract_runs_end_to_end_by_kind():
    llm, c = ScriptedLeaseLLM(), lease_contract()
    report = check_contract(llm, c, at=AT, document_kind="lease_contract")
    assert llm.systems and not any("lao động" in s for s in llm.systems)
    concepts = {r.concept_id for r in report.results}
    assert "lease.landlord_termination" in concepts
    assert all(x.startswith(("lease.", "civil.")) for x in concepts)       # không có khái niệm gói labor / loan
    r = next(x for x in report.results if (x.concept_id, x.rule_id) == ("lease.landlord_termination", "r1"))
    assert (r.status, r.finding) == ("FAIL", "violation")
    view, _, _, _ = contract_view(c, None, AT)
    assert {p["role"] for p in view.find("Party")} == {"BEN_CHO_THUE", "BEN_THUE"}
    ci = next(n for n in view.find("ConceptInstance") if n["concept_id"] == "lease.landlord_termination")
    holders = [h["node"]["role"] for h in view.neighbors(ci["node_id"], rel_types=["HOLDER"], direction="out")]
    assert holders == ["BEN_THUE"]
