"""Lỗi tìm thấy khi rà lại phiên bản hợp đồng."""
from pathlib import Path

from tests.test_contract_studio import events  # thêm ui/ vào sys.path
import contracts_api as api
from rag.contracts.store import _dump
from tests.test_contract_versions_api import (OTHER, VersionLLM, add, analyze, analyzed, appendix_v2,  # noqa: F401
                                              prepare, vclient, verify, versions)
from tests.test_contracts_api import client, runtime  # noqa: F401
from tests.versions_helpers import APPENDIX_TEXT


def test_old_version_cannot_be_changed(vclient):
    cid, out = appendix_v2(vclient)
    frozen = _dump(api.get(cid))
    stream = events(vclient.post(f"/api/contracts/{cid}/studio/analyze/stream", json={}))
    assert stream[-1]["type"] == "error" and stream[-1]["status"] == 409
    refused = [
        vclient.post(f"/api/contracts/{cid}/facts", json={"answers": {"sign_date": {"action": "set", "value": "2020-01-01"}}}),
        vclient.post(f"/api/contracts/{cid}/concept-check", json={}),
        vclient.post(f"/api/contracts/{cid}/concept-check/answer", json={"answers": {"wage_region": "I"}}),
        vclient.post(f"/api/contracts/{cid}/sign-date", json={"date": "2020-01-01"}),
        vclient.post(f"/api/contracts/{cid}/layout", json={"parts": []}),
    ]
    assert [r.status_code for r in refused] == [409] * 5
    assert _dump(api.get(cid)) == frozen
    latest = out["card"]["contract_id"]
    assert events(vclient.post(f"/api/contracts/{latest}/studio/analyze/stream", json={}))[-1]["type"] == "done"


class Reverting(VersionLLM):
    """Phụ lục 02 (phần p2) đưa lương về mức gốc."""

    back = "mức lương chính là 15.000.000 đồng/tháng"

    def complete(self, system, user):
        import json
        from rag.bridge.tagger import TAG_PROMPT
        from rag.contracts.facts import FACTS_PROMPT
        units = json.loads(user).get("units") or []
        if units and all(u.get("uid", "").startswith("p2.") for u in units):
            if system.startswith(FACTS_PROMPT[:40]):
                home = next((u["uid"] for u in units if self.back in u["text"]), units[0]["uid"])
                return json.dumps({"parties": [], "fields": {
                    "salary": {"value": "15.000.000 đồng/tháng", "unit": home, "quote": self.back}}}, ensure_ascii=False)
            if system.startswith(TAG_PROMPT[:40]):
                return json.dumps({"items": []})
        return super().complete(system, user)


REVERT = (APPENDIX_TEXT.replace("SỐ 01", "SỐ 02").replace("17.000.000", "15.000.000")
          .replace("01/06/2025", "01/01/2026"))


def test_second_appendix_can_set_a_value_back(vclient, monkeypatch):
    _, out = appendix_v2(vclient)
    v2 = out["card"]["contract_id"]
    monkeypatch.setattr(api.CONFIG, "llm_factory", Reverting)
    done = prepare(vclient, v2, add(vclient, v2, REVERT, "pl02.txt").json()["addition_id"], "appendix")
    assert done["type"] == "done", done
    third = analyze(vclient, done["draft"]["card"]["contract_id"], review_date="2026-02-01")
    assert third["type"] == "done", third
    salary = [x for x in third["compare"]["contract"]["changed"] if "base_salary_vnd" in x["after"]["facts_used"]]
    assert salary
    assert salary[0]["before"]["facts_used"]["base_salary_vnd"]["value"] == 17000000
    assert salary[0]["after"]["facts_used"]["base_salary_vnd"]["value"] == 15000000


def test_saved_list_follows_an_old_id_to_the_latest_version(vclient):
    cid, out = appendix_v2(vclient, persist=True)
    v2 = out["card"]["contract_id"]
    listed = vclient.get(f"/api/contracts?ids={cid}").json()["contracts"]
    assert [(x["contract_id"], x["replaces"]) for x in listed] == [(v2, [cid])]
    both = vclient.get(f"/api/contracts?ids={cid},{v2}").json()["contracts"]
    assert [x["contract_id"] for x in both] == [v2]
    script = (Path(__file__).resolve().parents[1] / "ui" / "contract_ask.js").read_text(encoding="utf-8")
    assert "replaces" in script                  # trang hỏi đáp đổi id đã lưu sang bản mới, không xóa mất


def test_chat_on_a_version_uses_the_version_day(vclient):
    _, out = appendix_v2(vclient)
    c = api.get(out["card"]["contract_id"])
    _, day, _ = api._open_agent(c, api._catalog_or_labor(c), None, {})
    assert day.isoformat() == "2025-07-01"


def test_next_addition_never_defaults_before_the_previous_day(vclient):
    cid = analyzed(vclient)
    done = prepare(vclient, cid, add(vclient, cid).json()["addition_id"], "appendix")
    v2 = analyze(vclient, done["draft"]["card"]["contract_id"], review_date="2027-03-01")["card"]["contract_id"]
    other = prepare(vclient, v2, add(vclient, v2, OTHER, "hd2.txt").json()["addition_id"], "contract")
    assert other["review_date"] == "2027-03-01"


def test_choosing_unknown_continuity_is_kept(vclient):
    cid = analyzed(vclient)
    done = prepare(vclient, cid, add(vclient, cid, OTHER, "hd2.txt").json()["addition_id"], "contract")
    verify(vclient, done["other"]["card"]["contract_id"])
    v2 = analyze(vclient, done["draft"]["card"]["contract_id"], same_party=True,
                 continuous_employment=True)["card"]["contract_id"]
    more = prepare(vclient, v2, add(vclient, v2, OTHER + "\nĐiều 4. Bản ba.", "hd3.txt").json()["addition_id"], "contract")
    verify(vclient, more["other"]["card"]["contract_id"])
    out = analyze(vclient, more["draft"]["card"]["contract_id"], same_party=True, continuous_employment=None)
    assert out["type"] == "done", out
    assert api.get(out["card"]["contract_id"]).lineage["addition"]["continuous_employment"] is None
