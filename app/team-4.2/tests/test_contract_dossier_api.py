"""Contract Studio: hồ sơ nhiều văn bản tải lên (ui/contract_dossier.py). Bước LLM (nhận diện loại, trích dữ kiện) giả:
loại lấy theo dossier.yaml của hồ sơ mẫu, dữ kiện lấy từ extracted.yaml (như tests/test_dossier_objects.py)."""
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from starlette.applications import Starlette
from starlette.testclient import TestClient

UI = Path(__file__).resolve().parents[1] / "ui"
sys.path.insert(0, str(UI))
import contract_dossier as dossier_api
import contracts_api as api
from tests.test_contracts_api import client, runtime  # noqa: F401 — fixture
from tests.test_dossier_objects import fake_facts

HERE = Path(__file__).parent / "fixtures" / "rete"


def events(response):
    assert response.status_code == 200, response.text
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


@pytest.fixture
def dclient(client, monkeypatch):
    monkeypatch.setattr(api.CONFIG, "llm_factory", lambda: None)
    return TestClient(Starlette(routes=dossier_api.routes))


def _fixture(did):
    spec = yaml.safe_load((HERE / did / "dossier.yaml").read_text(encoding="utf-8"))
    return spec, {x["file"]: x for x in spec["documents"]}


def _fake_llm(monkeypatch, did):
    spec, by_file = _fixture(did)
    monkeypatch.setattr(dossier_api, "classify_contract",
                        lambda llm, c, kinds: {"kind": by_file[c.filename]["kind"], "confidence": 0.9,
                                               "evidence": [{"uid": "p1", "quote": "x"}]})
    calls = []

    def extract(llm, d, extra_fields=()):
        calls.append(1)
        renamed = {x.doc_id: by_file[x.file]["doc_id"] for x in d.documents}
        real = replace(d, documents=tuple(replace(x, doc_id=renamed[x.doc_id],
                                                  refs={k: renamed.get(v, v) for k, v in x.refs.items()})
                                          for x in d.documents), root=HERE / did)
        back = {v: k for k, v in renamed.items()}
        return {back[k]: v for k, v in fake_facts(real).items()}
    monkeypatch.setattr(dossier_api, "extract_dossier_facts", extract)
    return spec, calls


def _upload(dclient, did):
    spec, _ = _fixture(did)
    files = [("files", (x["file"], (HERE / did / x["file"]).read_bytes(), "text/plain")) for x in spec["documents"]]
    stream = events(dclient.post("/api/contract-studio/dossier/upload/stream", files=files))
    assert stream[-1]["type"] == "done"
    return stream[-1]


def _body(draft, spec, **extra):
    by_file = {x["file"]: x for x in spec["documents"]}
    ids = {by_file[d["filename"]]["doc_id"]: d["doc_id"] for d in draft["documents"]}
    docs = [{"doc_id": d["doc_id"], "kind": d["kind"],
             "refs": {k: ids.get(v, v) for k, v in (by_file[d["filename"]].get("refs") or {}).items()}}
            for d in draft["documents"]]
    return {"review_date": str(spec["review_date"]), "parties": spec["parties"], "documents": docs,
            "user_facts": spec.get("user_facts") or {}, **extra}


def test_draft_suggests_kinds_refs_and_form(dclient, monkeypatch):
    _fake_llm(monkeypatch, "a1")
    draft = _upload(dclient, "a1")
    assert [d["kind"] for d in draft["documents"]] == ["labor_contract", "amendment", "amendment", "amendment"]
    assert all(d["refs"] == {"contract": "d1"} for d in draft["documents"][1:])   # một hợp đồng chính: phụ lục trỏ về nó
    assert "text" not in draft["documents"][0] and draft["documents"][0]["excerpt"]
    assert draft["packs"] == ["labor"] and draft["supports_dossier"]
    assert {r["id"] for r in draft["roles"]} >= {"NLD", "NSDLD"}
    assert next(k for k in draft["kinds"] if k["id"] == "labor_contract")["refs"] == ["employee"]


def test_b1_third_fixed_term_contract_fails_and_answers_do_not_reextract(dclient, monkeypatch):
    spec, calls = _fake_llm(monkeypatch, "b1")
    draft = _upload(dclient, "b1")
    url = f"/api/contract-studio/dossier/{draft['dossier_id']}/analyze/stream"
    done = events(dclient.post(url, json=_body(draft, spec)))[-1]
    assert done["type"] == "done", done
    got = {(r["concept_id"], r["rule_id"], r["object"]): r["status"] for r in done["results"]}
    assert got[("content.term", "r5", "employee=e1")] == "FAIL"
    r5 = next(r for r in done["results"] if r["rule_id"] == "r5")
    assert r5["object_label"] == "employee: Lê Thị Bình" and r5["explain"]["children"] is not None
    assert {o["type"] for o in done["objects"]} == {"Contract"} and len(done["objects"]) == 3
    again = events(dclient.post(url, json=_body(draft, spec, answers={"is_elderly_employee": False})))[-1]
    assert again["type"] == "done" and len(calls) == 1          # cùng cách ghép: không trích lại


def test_amendment_without_contract_is_rejected(dclient, monkeypatch):
    spec, _ = _fake_llm(monkeypatch, "a1")
    draft = _upload(dclient, "a1")
    body = _body(draft, spec)
    body["documents"][1]["refs"] = {}
    stream = events(dclient.post(f"/api/contract-studio/dossier/{draft['dossier_id']}/analyze/stream", json=body))
    assert stream[-1]["type"] == "error" and "Phụ lục" in stream[-1]["error"]


def test_unknown_draft_is_404(dclient):
    r = dclient.post("/api/contract-studio/dossier/nope/analyze/stream", json={})
    assert r.status_code == 404


def test_extract_reads_uploaded_text_not_disk(monkeypatch):
    """Văn bản tải lên nằm trong bộ nhớ (`DossierDoc.text`): bước trích thật không được đọc `root / file`."""
    from rag.contracts import dossier as core
    import rag.contracts.facts as facts_mod
    seen = []
    monkeypatch.setattr(facts_mod, "extract_facts", lambda llm, c, extra_fields=(): seen.append(c.text) or {})
    docs = (core.DossierDoc("d1", "khong-co-tren-dia.docx", "labor_contract", {}, "Điều 1. Thời hạn\n1. Mười hai tháng."),
            core.DossierDoc("d2", "pl.docx", core.AMENDMENT, {"contract": "d1"}, "PHỤ LỤC\nĐiều 1. Sửa đổi"))
    d = core.Dossier("x", None, ("labor",), (), docs, {}, Path("khong-ton-tai"))
    assert core.extract_dossier_facts(None, d) == {"d1": {}}
    assert "Mười hai tháng" in seen[0] and "PHỤ LỤC" in seen[0]
