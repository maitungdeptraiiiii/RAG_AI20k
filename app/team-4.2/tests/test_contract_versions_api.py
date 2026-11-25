"""API bổ sung văn bản: phiên bản, đối chiếu, an toàn khi lỗi (LLM giả, endpoint thật)."""
import json

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from tests.test_contract_studio import events  # thêm ui/ vào sys.path
import contract_studio as studio
import contract_versions as versions_api
import contracts_api as api
from rag.contracts.store import _dump
from tests.test_bridge_check import PAGES
from tests.test_contracts_api import client, runtime, verify_all  # noqa: F401
from tests.versions_helpers import APPENDIX_TEXT, AppendixLLM


class VersionLLM(AppendixLLM):
    """Thêm bước nhận diện loại: văn bản mở đầu bằng "PHỤ LỤC" là phụ lục, còn lại là hợp đồng lao động."""

    def complete(self, system, user):
        if system.startswith("Bạn đọc PHẦN ĐẦU"):
            unit = json.loads(user)["units"][0]
            kind = "amendment" if unit["text"].startswith("PHỤ LỤC") else "labor_contract"
            return json.dumps({"kind": kind, "confidence": 0.95, "unit": unit["uid"], "quote": unit["text"][:20]},
                              ensure_ascii=False)
        return super().complete(system, user)


@pytest.fixture
def vclient(client, monkeypatch):
    monkeypatch.setattr(api.CONFIG, "llm_factory", VersionLLM)
    monkeypatch.setattr(api.CONFIG, "tag_llm", lambda *args: None)
    monkeypatch.setattr(api.CONFIG, "legal_graph", lambda: None)
    return TestClient(Starlette(routes=[*studio.routes, *versions_api.routes, *api.routes]))


def analyzed(c, persist=False):
    done = events(c.post("/api/contract-studio/upload/stream", data={"persist": "1" if persist else "0"},
                         files={"file": ("hd.txt", PAGES[0].text.encode("utf-8"), "text/plain")}))[-1]
    cid = done["card"]["contract_id"]
    verify_all(c, cid)
    assert events(c.post(f"/api/contracts/{cid}/studio/analyze/stream", json={}))[-1]["type"] == "done"
    return cid


def add(c, cid, text=APPENDIX_TEXT, name="pl01.txt"):
    return c.post(f"/api/contracts/{cid}/additions", files={"file": (name, text.encode("utf-8"), "text/plain")})


def prepare(c, cid, aid, kind):
    return events(c.post(f"/api/contracts/{cid}/additions/{aid}/prepare/stream", json={"kind": kind}))[-1]


def verify(c, cid):
    if not c.get(f"/api/contracts/{cid}").json()["verification"]["complete"]:
        verify_all(c, cid)


def analyze(c, draft, **body):
    verify(c, draft)
    return events(c.post(f"/api/contracts/{draft}/additions/analyze/stream", json=body))[-1]


def versions(c, cid):
    return c.get(f"/api/contracts/{cid}/versions").json()["versions"]


def appendix_v2(c, persist=False):
    cid = analyzed(c, persist)
    got = add(c, cid).json()
    done = prepare(c, cid, got["addition_id"], "appendix")
    assert done["type"] == "done", done
    out = analyze(c, done["draft"]["card"]["contract_id"], review_date="2025-07-01")
    assert out["type"] == "done", out
    return cid, out


def test_appendix_flow_creates_v2_and_keeps_v1(vclient):
    cid = analyzed(vclient)
    frozen = _dump(api.get(cid))
    got = add(vclient, cid).json()
    assert got["suggested_kind"] == "appendix" and got["excerpt"].startswith("PHỤ LỤC")
    done = prepare(vclient, cid, got["addition_id"], "appendix")
    assert done["review_date"] == "2025-06-01" and done["other"] is None
    draft = done["draft"]["card"]["contract_id"]
    assert [v["version"] for v in versions(vclient, cid)] == [1]
    out = analyze(vclient, draft, review_date="2025-07-01")
    assert out["type"] == "done", out
    assert [(v["version"], v["latest"]) for v in versions(vclient, cid)] == [(1, False), (2, True)]
    assert _dump(api.get(cid)) == frozen
    compare = vclient.get(f"/api/contracts/{draft}/studio/compare").json()
    assert compare == out["compare"] and compare["day"] == "2025-07-01" and compare["against"] == cid
    changed = {x["key"] for x in compare["contract"]["changed"]}
    assert changed and "leave.annual/r1@" not in changed and compare["cross"] is None
    assert all(x["after"]["view"]["title"] for x in compare["contract"]["changed"])
    assert vclient.get(f"/api/contracts/{cid}/studio/compare").status_code == 404


def test_rechecking_a_version_does_not_reread_old_parts(vclient, monkeypatch):
    _, out = appendix_v2(vclient)
    draft = out["card"]["contract_id"]
    llm = VersionLLM()
    monkeypatch.setattr(api.CONFIG, "llm_factory", lambda: llm)
    stream = events(vclient.post(f"/api/contracts/{draft}/studio/analyze/stream", json={}))
    assert stream[-1]["type"] == "done" and llm.calls == []
    assert stream[-1]["result"]["report"]["day"] == "2025-07-01"


def test_missing_review_date_is_400(vclient):
    cid = analyzed(vclient)
    done = prepare(vclient, cid, add(vclient, cid).json()["addition_id"], "appendix")
    out = analyze(vclient, done["draft"]["card"]["contract_id"])
    assert out["type"] == "error" and out["status"] == 400 and len(versions(vclient, cid)) == 1


@pytest.mark.parametrize("stage", ["prepare", "analyze"])
def test_llm_failure_leaves_no_version(vclient, monkeypatch, stage):
    cid = analyzed(vclient)
    frozen = _dump(api.get(cid))
    aid = add(vclient, cid).json()["addition_id"]

    class Down(VersionLLM):
        def complete(self, system, user):
            return "không phải JSON"

    if stage == "prepare":
        monkeypatch.setattr(api.CONFIG, "llm_factory", Down)
        out = prepare(vclient, cid, aid, "appendix")
    else:
        done = prepare(vclient, cid, aid, "appendix")
        verify(vclient, done["draft"]["card"]["contract_id"])
        monkeypatch.setattr(api.CONFIG, "llm_factory", Down)
        out = analyze(vclient, done["draft"]["card"]["contract_id"], review_date="2025-07-01")
    assert out["type"] == "error", out
    assert len(versions(vclient, cid)) == 1 and _dump(api.get(cid)) == frozen


def test_not_latest_or_not_analyzed_is_409(vclient):
    cid, _ = appendix_v2(vclient)
    assert add(vclient, cid).status_code == 409
    raw = events(vclient.post("/api/contract-studio/upload/stream",
                              files={"file": ("b.txt", PAGES[0].text.encode("utf-8"), "text/plain")}))[-1]
    assert add(vclient, raw["card"]["contract_id"]).status_code == 409


OTHER = PAGES[0].text + "\nĐiều 3. Bản thứ hai."


def test_other_contract_flow_has_cross_section_and_same_party_is_required(vclient):
    cid = analyzed(vclient)
    got = add(vclient, cid, OTHER, "hd2.txt").json()
    assert got["suggested_kind"] == "contract"
    done = prepare(vclient, cid, got["addition_id"], "contract")
    assert done["type"] == "done", done
    draft, other = done["draft"]["card"]["contract_id"], done["other"]["card"]["contract_id"]
    assert done["review_date"] == "2026-11-11"
    verify(vclient, other)
    refused = analyze(vclient, draft, same_party=False)
    assert refused["type"] == "error" and refused["status"] == 400 and len(versions(vclient, cid)) == 1
    out = analyze(vclient, draft, same_party=True, continuous_employment=True, review_date="2025-07-01")
    assert out["type"] == "done", out
    assert out["compare"]["contract"] is None
    assert out["compare"]["cross"]["supported"] and out["compare"]["cross"]["total"] > 0
    listed = vclient.get(f"/api/contracts?ids={cid},{draft},{other}").json()["contracts"]
    assert [x["contract_id"] for x in listed] == [draft]


def test_delete_latest_restores_previous(vclient):
    cid, out = appendix_v2(vclient, persist=True)
    v2 = out["card"]["contract_id"]
    assert api.store().get(v2).persist and vclient.get(f"/api/contracts/{v2}").json()["lineage"]["version"] == 2
    assert vclient.delete(f"/api/contracts/{v2}").status_code == 200
    assert [(v["contract_id"], v["latest"]) for v in versions(vclient, cid)] == [(cid, True)]
    assert add(vclient, cid).status_code == 200


def test_delete_root_removes_the_family(vclient):
    cid, out = appendix_v2(vclient, persist=True)
    assert vclient.delete(f"/api/contracts/{cid}").status_code == 200
    assert vclient.get(f"/api/contracts/{out['card']['contract_id']}").status_code == 404
